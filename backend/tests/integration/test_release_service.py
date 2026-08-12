from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import ReleaseSearchConfig, get_settings
from backend.app.database.models import Episode, ReleaseCandidate, Subject, SubjectRelation
from backend.app.database.session import get_engine, session_scope
from backend.app.modules.release.schemas import RawRelease
from backend.app.modules.release.service import ReleaseSearchService


class FakeProvider:
    name = "fake"

    def __init__(self, releases: list[RawRelease]) -> None:
        self.releases = releases

    async def search(self, subject_names: list[str], episode_number: float | None) -> list[RawRelease]:
        return self.releases


class FakeDownloadService:
    async def create(self, episode_id: int, magnet: str) -> dict[str, object]:
        return {"id": "download-job", "episode_id": episode_id, "magnet": magnet}


def _reset() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _prepare(tmp_path: Path, monkeypatch) -> int:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'test.db'}")
    _reset()
    root = Path(__file__).resolve().parents[3]
    command.upgrade(Config(str(root / "alembic.ini")), "head")
    with session_scope() as session:
        subject = Subject(
            bangumi_subject_id=42,
            name="Test Anime",
            name_cn="测试动画",
            aliases='["テストアニメ"]',
        )
        session.add(subject)
        session.flush()
        episode = Episode(
            bangumi_episode_id=4206,
            subject_id=subject.id,
            episode_type="MAIN",
            sort_number=6,
            display_number="6",
            name="Episode 6",
        )
        session.add(episode)
        session.flush()
        return episode.id


@pytest.mark.anyio
async def test_search_persists_candidates_and_selection(tmp_path: Path, monkeypatch) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    provider = FakeProvider([
        RawRelease(
            source_id="release-1",
            title="[TestGroup] 测试动画 - 06 [1080p][HEVC]",
            description="",
            release_url="https://example.test/release-1",
            magnet_uri=magnet,
            published_at=None,
            author="TestGroup",
            category="动画",
        ),
        RawRelease(
            source_id="release-rejected",
            title="[OtherGroup] Other Anime - 99 [720p]",
            description="",
            release_url="https://example.test/release-rejected",
            magnet_uri="magnet:?xt=urn:btih:fedcba9876543210fedcba9876543210fedcba98",
            published_at=None,
            author="OtherGroup",
            category="动画",
        ),
    ])
    settings = SimpleNamespace(
        release_search=ReleaseSearchConfig(preferred_resolution="1080p", preferred_codec="HEVC")
    )
    service = ReleaseSearchService(provider, FakeDownloadService(), lambda: settings)

    result = await asyncio.wait_for(service.search(episode_id), timeout=5)
    candidate = result["candidates"][0]
    assert result["provider"] == "fake"
    assert result["rejected_count"] == 1
    assert len(result["candidates"]) == 1
    assert candidate["decision"] == "AUTO_ACCEPT"
    assert candidate["downloadable"] is True

    downloaded = await service.download_candidate(candidate["id"])
    assert downloaded["download"]["id"] == "download-job"
    with session_scope() as session:
        stored = session.get(ReleaseCandidate, candidate["id"])
        assert stored is not None
        assert stored.download_job_id == "download-job"
        assert stored.selected_at is not None
        assert len(list(session.scalars(
            select(ReleaseCandidate).where(ReleaseCandidate.episode_id == episode_id)
        ))) == 2
    _reset()


@pytest.mark.anyio
async def test_search_reuses_prequel_offset_for_continuous_episode_number(tmp_path: Path, monkeypatch) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        subject = session.get(Subject, episode.subject_id)
        assert subject is not None
        subject.name = "Test Anime 2nd Season"
        subject.name_cn = "测试动画 第二季"
        subject.aliases = '["Test Anime S2"]'
        for number in range(1, 6):
            session.add(Episode(
                bangumi_episode_id=4300 + number,
                subject_id=subject.id,
                episode_type="MAIN",
                sort_number=number,
                display_number=str(number),
                name=f"Episode {number}",
            ))
        prequel = Subject(bangumi_subject_id=41, name="Test Anime", name_cn="测试动画")
        session.add(prequel)
        session.flush()
        for number in range(1, 13):
            session.add(Episode(
                bangumi_episode_id=4100 + number,
                subject_id=prequel.id,
                episode_type="MAIN",
                sort_number=number,
                display_number=str(number),
                name=f"Episode {number}",
            ))
        session.add(SubjectRelation(
            subject_id=subject.id,
            related_subject_id=prequel.id,
            relation_type="前传",
        ))

    provider = FakeProvider([RawRelease(
        source_id="release-continuous",
        title="[TestGroup] Test Anime S2 - 18 [1080p][CHS&CHT]",
        description="",
        release_url="https://example.test/release-continuous",
        magnet_uri="magnet:?xt=urn:btih:89abcdef0123456789abcdef0123456789abcdef",
        published_at=None,
        author="TestGroup",
        category="动画",
    )])
    settings = SimpleNamespace(release_search=ReleaseSearchConfig(preferred_resolution="1080p"))
    service = ReleaseSearchService(provider, FakeDownloadService(), lambda: settings)

    result = await service.search(episode_id)
    candidate = result["candidates"][0]

    assert candidate["decision"] == "AUTO_ACCEPT"
    assert candidate["parsed"]["part"] is None
    assert "按前作累计集数换算匹配" in candidate["match_reasons"]
    assert "季度匹配" in candidate["match_reasons"]
    _reset()
