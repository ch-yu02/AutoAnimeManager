from pathlib import Path
import sqlite3
from types import SimpleNamespace

from backend.app.modules.maintenance import MaintenanceService


def settings_for(database: Path, backups: Path, *, keep: int = 2):
    return SimpleNamespace(
        database=SimpleNamespace(url=f"sqlite:///{database}"),
        maintenance=SimpleNamespace(backup_path=backups, backup_keep_count=keep),
    )


def test_backup_is_consistent_verified_and_rotated(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO sample (value) VALUES ('ready')")

    service = MaintenanceService(lambda: settings_for(database, tmp_path / "backups"))
    stale = tmp_path / "backups" / "autoanime-stale.db.tmp-wal"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")
    first = service.create_backup()
    second = service.create_backup()
    third = service.create_backup()

    assert first["verified"] is True
    assert not stale.exists()
    assert second["verified"] is True
    assert third["verified"] is True
    backups = sorted((tmp_path / "backups").glob("autoanime-*.db"))
    assert len(backups) == 2
    with sqlite3.connect(backups[-1]) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "ready"


def test_verify_database_rejects_corrupt_backup(tmp_path: Path) -> None:
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not sqlite")

    try:
        MaintenanceService.verify_database(broken)
    except RuntimeError as exc:
        assert "验证失败" in str(exc)
    else:
        raise AssertionError("损坏数据库不应通过验证")
