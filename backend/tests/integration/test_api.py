from pathlib import Path
import asyncio
import sqlite3

import httpx
import pytest
import yaml
from alembic import command
from alembic.config import Config

from backend.app.config import get_settings
from backend.app.database.session import get_engine
from backend.app.main import create_app


def _reset_caches() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _migrate() -> None:
    root = Path(__file__).resolve().parents[3]
    command.upgrade(Config(str(root / "alembic.ini")), "head")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health_and_redacted_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("AUTOANIME_BANGUMI__ACCESS_TOKEN", "must-not-leak")
    _reset_caches()
    _migrate()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/api/health")
            settings = await client.get("/api/settings")
            scheduler = await client.get("/api/scheduler")

    assert health.status_code == 200
    assert health.json()["database"]["status"] == "ok"
    assert settings.status_code == 200
    assert settings.json()["bangumi"]["access_token"] == "***"
    assert "must-not-leak" not in settings.text
    assert scheduler.status_code == 200
    assert {task["name"] for task in scheduler.json()["tasks"]} == {
        "BangumiSync", "LibraryScan", "DemandRefresh", "ReleaseSearch", "DownloadMonitor",
        "Cleanup", "Backup",
    }
    with sqlite3.connect(tmp_path / "test.db") as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    _reset_caches()


@pytest.mark.anyio
async def test_backup_and_diagnostics_are_verified_and_redacted(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "test.db"
    config = tmp_path / "config.yaml"
    config.write_text(
        "bangumi:\n  access_token: never-export-this\n"
        "qbittorrent:\n  password: also-secret\n"
        "maintenance:\n"
        f"  backup_path: {tmp_path / 'backups'}\n"
        f"  diagnostics_path: {tmp_path / 'diagnostics'}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_CONFIG", str(config))
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{database}")
    monkeypatch.setenv("AUTOANIME_SCHEDULER__ENABLED", "false")
    _reset_caches()
    _migrate()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            backup = await asyncio.wait_for(
                client.post("/api/maintenance/backup"), timeout=10
            )
            diagnostics = await asyncio.wait_for(
                client.post("/api/maintenance/diagnostics"), timeout=10
            )

    assert backup.status_code == 200
    assert backup.json()["verified"] is True
    backup_path = Path(backup.json()["path"])
    assert backup_path.is_file()
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    assert diagnostics.status_code == 200
    diagnostic_path = Path(diagnostics.json()["path"])
    assert diagnostic_path.is_file()
    import zipfile
    with zipfile.ZipFile(diagnostic_path) as archive:
        settings_text = archive.read("settings.redacted.json").decode("utf-8")
        assert "never-export-this" not in settings_text
        assert "also-secret" not in settings_text
        assert '"access_token": "***"' in settings_text
        assert '"password": "***"' in settings_text
        assert archive.read("summary.json")
        assert archive.read("task-runs.json")
        assert archive.read("download-import-audit.json")
        assert archive.read("cleanup-audit.json")
    _reset_caches()


@pytest.mark.anyio
async def test_connection_placeholders_are_explicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'test.db'}")
    _reset_caches()
    _migrate()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            bangumi = await client.post("/api/settings/test/bangumi")
            qbittorrent = await client.post("/api/settings/test/qbittorrent")

    assert bangumi.json()["status"] == "not_configured"
    assert qbittorrent.json()["status"] == "not_configured"
    _reset_caches()


@pytest.mark.anyio
async def test_settings_persist_independent_auto_download_switch(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "player:\n  bangumi_writeback_enabled: false\n"
        "scheduler:\n  auto_download_enabled: false\n"
        "cleanup:\n  enabled: false\n  retention_days: 14\n  quarantine_days: 7\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTOANIME_CONFIG", str(config))
    _reset_caches()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/settings",
            json={
                "bangumi_writeback_enabled": True,
                "auto_download_enabled": True,
                "cleanup_enabled": True,
                "cleanup_retention_days": 30,
                "cleanup_quarantine_days": 10,
            },
        )

    assert response.status_code == 200
    assert response.json()["player"]["bangumi_writeback_enabled"] is True
    assert response.json()["scheduler"]["auto_download_enabled"] is True
    assert response.json()["cleanup"] == {
        "enabled": True,
        "retention_days": 30,
        "quarantine_days": 10,
        "interval_seconds": 86400.0,
    }
    persisted = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert persisted["player"]["bangumi_writeback_enabled"] is True
    assert persisted["scheduler"]["auto_download_enabled"] is True
    assert persisted["cleanup"] == {
        "enabled": True,
        "retention_days": 30,
        "quarantine_days": 10,
    }
    _reset_caches()


@pytest.mark.anyio
async def test_startup_reports_missing_migration_without_creating_tables(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "unmigrated.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{database}")
    _reset_caches()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"]["status"] == "error"
    assert "alembic upgrade head" in response.json()["database"]["detail"]
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "system_state" not in tables
    _reset_caches()
