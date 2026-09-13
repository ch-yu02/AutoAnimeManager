from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import ReleaseSearchConfig, get_settings
from backend.app.database.models import (
    DownloadJob,
    DownloadJobEpisode,
    Episode,
    EpisodeFile,
    MediaFile,
    ReleaseCandidate,
    Subject,
    SubjectRelation,
)
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
    def __init__(self) -> None:
        self.created: list[tuple[int, str, list[int] | None]] = []

    async def create(
        self, episode_id: int, magnet: str, *, replacement_media_ids=None
    ) -> dict[str, object]:
        self.created.append((episode_id, magnet, replacement_media_ids))
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
    downloads = FakeDownloadService()
    service = ReleaseSearchService(provider, downloads, lambda: settings)

    result = await asyncio.wait_for(service.search(episode_id), timeout=5)
    candidate = result["candidates"][0]
    assert result["provider"] == "fake"
    assert result["rejected_count"] == 1
    assert len(result["candidates"]) == 1
    assert candidate["decision"] == "AUTO_ACCEPT"
    assert candidate["downloadable"] is True

    debugged = service.debug_auto_select(result["id"])
    debug_candidate = debugged["candidates"][0]
    assert debug_candidate["debug_selected_at"] is not None
    assert debug_candidate["selected_at"] is None
    assert debug_candidate["download_job_id"] is None
    assert downloads.created == []

    downloaded = await service.download_candidate(candidate["id"])
    assert downloaded["download"]["id"] == "download-job"
    with session_scope() as session:
        stored = session.get(ReleaseCandidate, candidate["id"])
        assert stored is not None
        assert stored.download_job_id == "download-job"
        assert stored.selected_at is not None
        assert stored.debug_selected_at is not None
        assert len(list(session.scalars(
            select(ReleaseCandidate).where(ReleaseCandidate.episode_id == episode_id)
        ))) == 2
    _reset()


@pytest.mark.anyio
async def test_manual_replacement_uses_media_imported_by_selected_job(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    downloads = FakeDownloadService()
    service = ReleaseSearchService(
        FakeProvider([_raw(
            "corrected-source",
            "[NewGroup] 测试动画 - 06 [1080p][CHS]",
            "9",
        )]),
        downloads,
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )
    result = await service.search(episode_id)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        job = DownloadJob(
            id="wrong-source-job",
            magnet_uri="magnet:?xt=urn:btih:" + "8" * 40,
            magnet_hash="8" * 40,
            torrent_hash="8" * 40,
            subject_id=episode.subject_id,
            progress=1,
            state="IMPORTED",
            save_path=str(tmp_path),
        )
        session.add(job)
        session.add(DownloadJobEpisode(job_id=job.id, episode_id=episode.id))
        media = MediaFile(
            path=str(tmp_path / "wrong.mkv"),
            filename="[WrongGroup] 测试动画 - 06.mkv",
            file_size=1,
            mtime_ns=1,
            exists=True,
            ignored=False,
            subject_id=episode.subject_id,
            last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
        session.add(EpisodeFile(
            episode_id=episode.id,
            media_file_id=media.id,
            mapping_source="DOWNLOAD_JOB",
            confidence=1,
            reasons=json.dumps([f"下载任务 {job.id} 直接关联"], ensure_ascii=False),
            is_primary=True,
        ))
        media_id = media.id

    await service.download_candidate(
        result["candidates"][0]["id"], replacement_job_id="wrong-source-job"
    )

    assert downloads.created[0][2] == [media_id]
    _reset()


@pytest.mark.anyio
async def test_debug_auto_select_marks_nothing_without_auto_accept(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    provider = FakeProvider([RawRelease(
        source_id="manual",
        title="[TestGroup] 测试动画 - 06 [1080p]",
        description="",
        release_url="https://example.test/manual",
        magnet_uri="magnet:?xt=urn:btih:fedcba9876543210fedcba9876543210fedcba98",
        published_at=None,
        author="OtherGroup",
        category="动画",
    )])
    downloads = FakeDownloadService()
    settings = SimpleNamespace(release_search=ReleaseSearchConfig())
    service = ReleaseSearchService(provider, downloads, lambda: settings)

    result = await service.search(episode_id)
    with session_scope() as session:
        candidate = session.scalar(
            select(ReleaseCandidate).where(ReleaseCandidate.search_id == result["id"])
        )
        assert candidate is not None
        candidate.decision = "MANUAL_REVIEW"
    debugged = service.debug_auto_select(result["id"])

    assert len(debugged["candidates"]) == 1
    assert all(candidate["debug_selected_at"] is None for candidate in debugged["candidates"])
    assert downloads.created == []
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


@pytest.mark.anyio
async def test_search_accepts_episode_number_continued_across_same_season_arc(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        subject = session.get(Subject, episode.subject_id)
        assert subject is not None
        subject.name = "Re:ゼロから始める異世界生活 4th season 奪還編"
        subject.name_cn = "Re：从零开始的异世界生活 第四季 夺还篇"
        subject.aliases = '["Re：從零開始的異世界生活 第四季 奪還篇"]'
        episode.sort_number = 78
        episode.display_number = "78"

        prequel = Subject(
            bangumi_subject_id=41,
            name="Re:ゼロから始める異世界生活 4th season 喪失編",
            name_cn="Re：从零开始的异世界生活 第四季 丧失篇",
        )
        session.add(prequel)
        session.flush()
        for number in range(1, 12):
            session.add(Episode(
                bangumi_episode_id=4100 + number,
                subject_id=prequel.id,
                episode_type="MAIN",
                sort_number=66 + number,
                display_number=str(66 + number),
                name=f"Episode {number}",
            ))
        prior_season = Subject(
            bangumi_subject_id=40,
            name="Re:ゼロから始める異世界生活 3rd season",
            name_cn="Re：从零开始的异世界生活 第三季",
        )
        session.add(prior_season)
        session.flush()
        session.add(Episode(
            bangumi_episode_id=4001,
            subject_id=prior_season.id,
            episode_type="MAIN",
            sort_number=66,
            display_number="66",
            name="Previous season finale",
        ))
        session.add(SubjectRelation(
            subject_id=subject.id,
            related_subject_id=prequel.id,
            relation_type="前传",
        ))
        session.add(SubjectRelation(
            subject_id=prequel.id,
            related_subject_id=prior_season.id,
            relation_type="前传",
        ))

    provider = FakeProvider([_raw(
        "season-episode-12",
        "[ANi] Re：從零開始的異世界生活 第四季 - 12 [1080P][Baha][CHT]",
        "8",
    )])
    service = ReleaseSearchService(
        provider,
        FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    candidate = result["candidates"][0]

    assert candidate["decision"] == "AUTO_ACCEPT"
    assert "按同季度前篇累计集数换算匹配" in candidate["match_reasons"]
    assert service.auto_candidate(result["id"]) is not None
    _reset()


def _raw(source_id: str, title: str, hash_digit: str) -> RawRelease:
    return RawRelease(
        source_id=source_id,
        title=title,
        description="",
        release_url=f"https://example.test/{source_id}",
        magnet_uri="magnet:?xt=urn:btih:" + hash_digit * 40,
        published_at=None,
        author=source_id,
        category="动画",
    )


@pytest.mark.anyio
async def test_auto_selection_prefers_ani_before_fansub_delay(tmp_path: Path, monkeypatch) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    provider = FakeProvider([
        _raw("fansub", "[北宇治字幕组] 测试动画 - 06 [1080p][CHS&JPN]", "1"),
        _raw("ani", "[ANi] 测试动画 - 06 [1080p][CHT]", "2"),
    ])
    service = ReleaseSearchService(
        provider, FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    selected = service.auto_candidate(result["id"])

    assert selected is not None
    assert selected["parsed"]["release_group"] == "ANi"
    _reset()


@pytest.mark.anyio
async def test_auto_selection_prefers_fansub_after_three_days_without_local_media(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        episode.air_date = date.today() - timedelta(days=3)
    provider = FakeProvider([
        _raw("ani", "[ANi] 测试动画 - 06 [1080p][CHT]", "c"),
        _raw("fansub", "[北宇治字幕组] 测试动画 - 06 [1080p][CHS]", "d"),
    ])
    service = ReleaseSearchService(
        provider, FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    selected = service.auto_candidate(result["id"])

    assert selected is not None
    assert selected["parsed"]["release_group"] == "北宇治字幕组"
    _reset()


@pytest.mark.anyio
async def test_auto_selection_requires_baha_for_kuro_nezumi_group(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    provider = FakeProvider([
        _raw("without-baha", "[黒ネズミたち] 测试动画 - 06 [1080p][CHS]", "e"),
        _raw("with-baha", "[黒ネズミたち] 测试动画 - 06 [BAHA][1080p][CHS]", "f"),
    ])
    service = ReleaseSearchService(
        provider, FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    selected = service.auto_candidate(result["id"])

    assert selected is not None
    assert selected["title"] == "[黒ネズミたち] 测试动画 - 06 [BAHA][1080p][CHS]"
    _reset()


@pytest.mark.anyio
async def test_kuro_nezumi_without_baha_remains_manual_but_is_not_auto_selected(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    service = ReleaseSearchService(
        FakeProvider([
            _raw("without-baha", "[黒ネズミたち] 测试动画 - 06 [1080p][CHS]", "e"),
        ]),
        FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)

    assert service.auto_candidate(result["id"]) is None
    assert result["candidates"][0]["downloadable"] is True
    _reset()


@pytest.mark.anyio
async def test_auto_selection_locks_existing_subject_groups_and_ranks_them(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        for index, group in enumerate(("LoliHouse", "北宇治字幕组"), start=1):
            session.add(MediaFile(
                path=str(tmp_path / f"existing-{index}.mkv"),
                filename=f"[{group}] Test Anime - 0{index}.mkv",
                file_size=1,
                mtime_ns=1,
                exists=True,
                ignored=False,
                subject_id=episode.subject_id,
                parse_result=json.dumps({"release_group": group}, ensure_ascii=False),
                last_scanned_at=datetime.now(UTC),
            ))
    provider = FakeProvider([
        _raw("other", "[OtherGroup] 测试动画 - 06 [1080p][CHS&JPN]", "3"),
        _raw("loli", "[LoliHouse] 测试动画 - 06 [1080p][CHS]", "4"),
        _raw("kitauji", "[北宇治字幕组] 测试动画 - 06 [1080p][CHS&JPN]", "5"),
    ])
    service = ReleaseSearchService(
        provider, FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    selected = service.auto_candidate(result["id"])

    assert selected is not None
    assert selected["parsed"]["release_group"] == "北宇治字幕组"
    _reset()


@pytest.mark.anyio
async def test_debug_selection_matches_english_and_chinese_group_aliases(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        session.add(MediaFile(
            path=str(tmp_path / "sakurato-existing.mkv"),
            filename="[Sakurato] Test Anime - 05.mkv",
            file_size=1,
            mtime_ns=1,
            exists=True,
            ignored=False,
            subject_id=episode.subject_id,
            parse_result='{"release_group":"Sakurato"}',
            last_scanned_at=datetime.now(UTC),
        ))
    provider = FakeProvider([
        _raw("sakurato", "[桜都字幕组] 测试动画 - 06 [1080p][CHS]", "a"),
        _raw("other", "[其他字幕组] 测试动画 - 06 [1080p][CHS&JPN]", "b"),
    ])
    service = ReleaseSearchService(
        provider, FakeDownloadService(),
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    debugged = service.debug_auto_select(result["id"])
    marked = [item for item in debugged["candidates"] if item["debug_selected_at"]]

    assert len(marked) == 1
    assert marked[0]["parsed"]["release_group"] == "桜都字幕组"
    _reset()


@pytest.mark.anyio
async def test_three_day_old_ani_media_selects_preferred_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    episode_id = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        episode.air_date = date.today() - timedelta(days=3)
        media = MediaFile(
            path=str(tmp_path / "ani.mkv"),
            filename="[ANi] Test Anime - 06.mkv",
            file_size=1,
            mtime_ns=1,
            exists=True,
            ignored=False,
            subject_id=episode.subject_id,
            parse_result='{"release_group":"ANi"}',
            last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
        session.add(EpisodeFile(
            episode_id=episode.id,
            media_file_id=media.id,
            mapping_source="DOWNLOAD_JOB",
            confidence=1,
            is_primary=True,
        ))
        media_id = media.id
    downloads = FakeDownloadService()
    provider = FakeProvider([
        _raw("ani", "[ANi] 测试动画 - 06 [1080p][CHT]", "6"),
        _raw("fansub", "[字幕组] 测试动画 - 06 [1080p][CHS]", "7"),
    ])
    service = ReleaseSearchService(
        provider, downloads,
        lambda: SimpleNamespace(release_search=ReleaseSearchConfig()),
    )

    result = await service.search(episode_id)
    selected = service.auto_candidate(result["id"])
    assert selected is not None
    assert selected["parsed"]["release_group"] == "字幕组"
    await service.download_candidate(selected["id"], automatic=True)
    assert downloads.created[0][2] == [media_id]
    _reset()
