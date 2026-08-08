from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config

from backend.app.config import get_settings
from backend.app.database.models import Episode, Subject
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
async def test_subject_list_detail_and_episodes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'subjects.db'}")
    _reset_caches()
    _migrate()

    app = create_app()
    async with app.router.lifespan_context(app):
        with session_scope() as session:
            subject = Subject(
                bangumi_subject_id=100,
                name="Original",
                name_cn="测试条目",
                collection_type="DOING",
                keep_forever=False,
            )
            session.add(subject)
            session.flush()
            session.add(
                Episode(
                    bangumi_episode_id=200,
                    subject_id=subject.id,
                    episode_type="SPECIAL",
                    display_number="SP",
                    name="Special",
                    name_cn="特别篇",
                    watched=False,
                    ignored=False,
                )
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            listing = await client.get("/api/subjects?collection_status=DOING")
            detail = await client.get("/api/subjects/1")
            episodes = await client.get("/api/subjects/1/episodes")

    assert listing.status_code == 200
    assert listing.json()[0]["display_name"] == "测试条目"
    assert detail.status_code == 200
    assert detail.json()["relations"] == []
    assert episodes.status_code == 200
    assert episodes.json()[0]["episode_type"] == "SPECIAL"
    _reset_caches()


@pytest.mark.anyio
async def test_settings_update_is_visible_to_sync_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'settings.db'}")
    _reset_caches()
    _migrate()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.patch(
                "/api/settings",
                json={"bangumi_username": "new-user", "bangumi_access_token": "new-token"},
            )

        current = app.state.bangumi_sync_service.settings_provider()
        assert response.status_code == 200
        assert current.username == "new-user"
        assert current.access_token.get_secret_value() == "new-token"
        assert (tmp_path / "config.yaml").stat().st_mode & 0o777 == 0o600
    _reset_caches()
