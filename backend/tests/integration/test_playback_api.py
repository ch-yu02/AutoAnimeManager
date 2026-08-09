from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config

from backend.app.config import get_settings
from backend.app.database.models import Episode, PlaybackState, Subject
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
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            idle = await client.get("/api/playback/current")
            watched = await client.post(f"/api/episodes/{episodes[0]}/mark-watched")
            next_unwatched = await client.get(f"/api/subjects/{subject_id}/next-unwatched")
            unwatched = await client.post(f"/api/episodes/{episodes[0]}/mark-unwatched")

    assert idle.json() == {"status": "IDLE", "episode_id": None}
    assert watched.json()["watched"] is True
    assert watched.json()["watched_source"] == "MANUAL"
    assert next_unwatched.json()["episode_id"] == episodes[1]
    assert unwatched.json()["watched"] is False
    with session_scope() as session:
        state = session.get(PlaybackState, 1)
        assert state is not None and state.watched_source == "MANUAL"
    _reset_caches()
