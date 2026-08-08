from pathlib import Path

import httpx
import pytest

from backend.app.config import get_settings
from backend.app.database.session import get_engine
from backend.app.main import create_app


def _reset_caches() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health_and_redacted_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("AUTOANIME_BANGUMI__ACCESS_TOKEN", "must-not-leak")
    _reset_caches()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/api/health")
            settings = await client.get("/api/settings")

    assert health.status_code == 200
    assert health.json()["database"]["status"] == "ok"
    assert settings.status_code == 200
    assert settings.json()["bangumi"]["access_token"] == "***"
    assert "must-not-leak" not in settings.text
    _reset_caches()


@pytest.mark.anyio
async def test_connection_placeholders_are_explicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'test.db'}")
    _reset_caches()

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
