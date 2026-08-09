from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database.models import Episode, EpisodeFile, MediaFile, PlaybackState, Subject
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
async def test_manual_watch_api_and_first_unwatched(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'playback-api.db'}")
    _reset_caches()
    _migrate()
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=1, name="Anime", collection_type="DOING")
        session.add(subject)
        session.flush()
        subject_id = subject.id
        episodes = []
        for number in (1, 2):
            episode = Episode(
                bangumi_episode_id=100 + number, subject_id=subject.id, episode_type="MAIN",
                sort_number=number, display_number=str(number), watched=False,
            )
            session.add(episode)
            session.flush()
            episodes.append(episode.id)

    app = create_app()
    paths = app.openapi()["paths"]
    assert "/api/playback/sessions" in paths
    assert not any(path.startswith("/api/playback/web/") for path in paths)
    assert "/api/playback/start" not in paths
    assert "/api/playback/current" not in paths
    assert "/api/playback/pause" not in paths
    assert "/api/playback/resume" not in paths
    assert "/api/playback/seek" not in paths
    assert "/api/playback/stop" not in paths
    assert "/api/playback/next" not in paths
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            watched = await client.post(f"/api/episodes/{episodes[0]}/mark-watched")
            next_unwatched = await client.get(f"/api/subjects/{subject_id}/next-unwatched")
            unwatched = await client.post(f"/api/episodes/{episodes[0]}/mark-unwatched")

    assert watched.json()["watched"] is True
    assert watched.json()["watched_source"] == "MANUAL"
    assert next_unwatched.json()["episode_id"] == episodes[1]
    assert unwatched.json()["watched"] is False
    with session_scope() as session:
        state = session.get(PlaybackState, 1)
        assert state is not None and state.watched_source == "MANUAL"
    _reset_caches()


@pytest.mark.anyio
async def test_native_playback_session_api_persists_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'session-api.db'}")
    _reset_caches()
    _migrate()
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=10, name="Anime", collection_type="DOING")
        session.add(subject)
        session.flush()
        episode = Episode(
            bangumi_episode_id=101,
            subject_id=subject.id,
            episode_type="MAIN",
            sort_number=1,
            display_number="1",
            name="Episode",
            local_status="READY",
        )
        session.add(episode)
        session.flush()
        missing_next = Episode(
            bangumi_episode_id=102,
            subject_id=subject.id,
            episode_type="MAIN",
            sort_number=2,
            display_number="2",
            name="Missing Episode",
            local_status="MISSING",
        )
        later_episode = Episode(
            bangumi_episode_id=103,
            subject_id=subject.id,
            episode_type="MAIN",
            sort_number=3,
            display_number="3",
            name="Later Episode",
            local_status="READY",
        )
        session.add_all([missing_next, later_episode])
        session.flush()
        media = MediaFile(
            path=str(tmp_path / "episode.mkv"), filename="episode.mkv", file_size=1, mtime_ns=1,
            audio_languages="[]", subtitle_languages="[]", parse_result="{}", exists=True, ignored=False,
            subject_id=subject.id, last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
        session.add(EpisodeFile(
            episode_id=episode.id, media_file_id=media.id, mapping_source="MANUAL",
            confidence=1, reasons="[]", is_primary=True, manually_locked=True,
        ))
        session.add(EpisodeFile(
            episode_id=later_episode.id, media_file_id=media.id, mapping_source="MANUAL",
            confidence=1, reasons="[]", is_primary=True, manually_locked=True,
        ))
        episode_id = episode.id

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/api/playback/sessions", json={"episode_id": episode_id})
            session_id = created.json()["session_id"]
            progress = await client.post(
                f"/api/playback/sessions/{session_id}/progress",
                json={"position_seconds": 812.4, "duration_seconds": 1440},
            )
            closed = await client.delete(f"/api/playback/sessions/{session_id}")
            resumed = await client.post("/api/playback/sessions", json={"episode_id": episode_id})
            short = await client.post(
                f"/api/playback/sessions/{resumed.json()['session_id']}/progress",
                json={"position_seconds": 30, "duration_seconds": 1440},
            )
            completed = await client.post(
                f"/api/playback/sessions/{resumed.json()['session_id']}/progress",
                json={"position_seconds": 1300, "duration_seconds": 1440},
            )
            manually_unwatched = await client.post(f"/api/episodes/{episode_id}/mark-unwatched")
            ended_after_manual_override = await client.post(
                f"/api/playback/sessions/{resumed.json()['session_id']}/progress",
                json={"position_seconds": 1440, "duration_seconds": 1440, "ended": True},
            )

    assert created.status_code == 201
    assert created.json()["media_path"].endswith("episode.mkv")
    assert progress.status_code == 200
    assert progress.json()["position_seconds"] == 812.4
    assert progress.json()["next_episode_id"] is None
    assert closed.status_code == 200
    assert resumed.status_code == 201
    assert resumed.json()["initial_position_seconds"] == 812.4
    assert short.status_code == 200
    assert short.json()["position_seconds"] == 812.4
    assert completed.status_code == 200
    assert completed.json()["watched"] is True
    assert manually_unwatched.status_code == 200
    assert ended_after_manual_override.status_code == 200
    assert ended_after_manual_override.json()["watched"] is False
    assert ended_after_manual_override.json()["watched_source"] == "MANUAL"
    # EP2 缺失时不能跳过它自动播放已有文件的 EP3。
    assert ended_after_manual_override.json()["next_episode_id"] is None
    with session_scope() as session:
        state = session.scalar(select(PlaybackState).where(PlaybackState.episode_id == episode_id))
        assert state is not None and state.position_seconds == 1440
        assert state.watched is False and state.watched_source == "MANUAL"
    _reset_caches()
