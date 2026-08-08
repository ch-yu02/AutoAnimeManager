from pathlib import Path
from datetime import UTC, datetime

import httpx
import pytest
import json
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database.models import Episode, EpisodeFile, MediaFile, Subject
from backend.app.database.session import get_engine, session_scope
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
async def test_manual_multi_episode_link_ignore_restore_and_unlink(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "library"
    library.mkdir()
    video = library / "manual.mkv"
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("AUTOANIME_STORAGE__LIBRARY_PATH", str(library))
    monkeypatch.setenv("AUTOANIME_STORAGE__FFPROBE_ENABLED", "false")
    _reset_caches()
    _migrate()
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=88, name="Manual Anime", collection_type="DOING")
        session.add(subject)
        session.flush()
        subject_id = subject.id
        for number in (1, 2):
            session.add(Episode(
                bangumi_episode_id=8800 + number, subject_id=subject.id,
                episode_type="MAIN", sort_number=number, display_number=str(number),
            ))
        session.flush()
        episode_ids = list(session.scalars(select(Episode.id).order_by(Episode.id)))
        session.add(MediaFile(
            path=str(video), filename=video.name, file_size=video.stat().st_size,
            mtime_ns=video.stat().st_mtime_ns, last_scanned_at=datetime.now(UTC),
            review_reason="LOW_CONFIDENCE",
        ))

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            linked = await client.post("/api/library/files/1/match", json={
                "subject_id": subject_id, "episode_ids": episode_ids,
                "primary": True, "lock": True, "write_manifest": True,
            })
            review = await client.get("/api/library/review")
            hashed = await client.post("/api/library/files/1/full-hash")
            ignored = await client.post("/api/library/files/1/ignore", json={"ignored": True})
            restored = await client.post("/api/library/files/1/ignore", json={"ignored": False})
            unlinked = await client.delete("/api/library/files/1/match")

    assert linked.status_code == 200
    assert len(linked.json()["episodes"]) == 2
    assert linked.json()["locked"] is True
    assert len(review.json()["manually_linked"]) == 1
    assert len(review.json()["locked"]) == 1
    assert review.json()["manually_linked"][0]["subject_reasons"] == ["用户人工关联"]
    assert hashed.json()["full_hash"]
    assert ignored.json()["ignored"] is True
    assert restored.json()["review_reason"] == "RESTORED_FOR_REVIEW"
    assert unlinked.json()["subject"] is None
    assert (library / "manifest.json").is_file()
    manifest = json.loads((library / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["subject_id"] == 88
    assert {item["episode_id"] for item in manifest["files"]} == {8801, 8802}
    assert all(item["filename"] == video.name for item in manifest["files"])
    with session_scope() as session:
        assert session.scalar(select(EpisodeFile)) is None
    _reset_caches()
