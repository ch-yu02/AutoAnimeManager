from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select

from backend.app.config import BangumiConfig, get_settings
from backend.app.database.models import Episode, MediaFile, Subject, SubjectRelation
from backend.app.database.session import create_schema, get_engine
from backend.app.modules.bangumi.schemas import (
    BangumiCollection,
    BangumiEpisode,
    BangumiRelation,
    BangumiSubject,
)
from backend.app.modules.bangumi.errors import BangumiTemporaryError
from backend.app.modules.bangumi.sync_service import BangumiSyncService


class FakeBangumiClient:
    def __init__(self) -> None:
        self.collections = [BangumiCollection(10, "DOING"), BangumiCollection(20, "WISH")]
        self.fail_subject_ids: set[int] = set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get_user_collections(self, username: str):
        return self.collections

    async def get_subject(self, subject_id: int):
        if subject_id in self.fail_subject_ids:
            raise BangumiTemporaryError("temporary")
        return BangumiSubject(
            subject_id,
            f"name-{subject_id}",
            f"中文-{subject_id}",
            "summary",
            f"https://bgm.tv/subject/{subject_id}",
            "",
            2,
            date(2024, 1, 1),
            "FINISHED",
            1,
        )

    async def get_episodes(self, subject_id: int):
        return [
            BangumiEpisode(subject_id * 10, "MAIN", 1, "1", "episode", "第一集", date(2024, 1, 2)),
            BangumiEpisode(subject_id * 10 + 1, "OP", 0, "OP", "opening", "", None),
        ]

    async def get_subject_relations(self, subject_id: int):
        return [BangumiRelation(20 if subject_id == 10 else 10, "SEQUEL")]

    async def get_episode_collection(self, subject_id: int):
        return {subject_id * 10: "WATCHED"}


def test_sync_is_idempotent_and_preserves_local_watched(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'sync.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()

    fake_client = FakeBangumiClient()
    service = BangumiSyncService(
        BangumiConfig(username="user", access_token="token"),
        client_factory=lambda _: fake_client,
    )
    first = asyncio.run(service.sync_now())
    second = asyncio.run(service.sync_now())

    from backend.app.database.session import session_scope

    with session_scope() as session:
        assert first.status == second.status == "SUCCESS"
        assert session.scalar(select(func.count()).select_from(Subject)) == 2
        assert session.scalar(select(func.count()).select_from(Episode)) == 4
        assert session.scalar(select(func.count()).select_from(SubjectRelation)) == 2
        episode = session.scalar(select(Episode).where(Episode.bangumi_episode_id == 100))
        assert episode is not None
        episode.watched = True

    asyncio.run(service.sync_now())
    with session_scope() as session:
        episode = session.scalar(select(Episode).where(Episode.bangumi_episode_id == 100))
        assert episode is not None and episode.watched is True


def test_sync_reconciles_removed_collections_without_deleting_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'sync.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()

    fake_client = FakeBangumiClient()
    service = BangumiSyncService(
        BangumiConfig(username="user", access_token="token"),
        client_factory=lambda _: fake_client,
    )
    asyncio.run(service.sync_now())
    fake_client.collections = []
    result = asyncio.run(service.sync_now())

    from backend.app.database.session import session_scope

    with session_scope() as session:
        subjects = list(session.scalars(select(Subject)))
        episodes = list(session.scalars(select(Episode)))
        assert result.status == "SUCCESS"
        assert len(subjects) == 2
        assert len(episodes) == 4
        assert all(subject.collection_type is None for subject in subjects)


def test_partial_failure_preserves_existing_subject_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'sync.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()

    fake_client = FakeBangumiClient()
    service = BangumiSyncService(
        BangumiConfig(username="user", access_token="token"),
        client_factory=lambda _: fake_client,
    )
    asyncio.run(service.sync_now())
    fake_client.fail_subject_ids = {10}
    result = asyncio.run(service.sync_now())

    from backend.app.database.session import session_scope

    with session_scope() as session:
        subject = session.scalar(select(Subject).where(Subject.bangumi_subject_id == 10))
        assert result.status == "PARTIAL_FAILURE"
        assert subject is not None and subject.name == "name-10"
        assert session.scalar(select(func.count()).select_from(Subject)) == 2


def test_concurrent_sync_reuses_active_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'sync.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()

    async def scenario() -> None:
        class BlockingFakeBangumiClient(FakeBangumiClient):
            def __init__(self) -> None:
                super().__init__()
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def get_user_collections(self, username: str):
                self.started.set()
                await self.release.wait()
                return await super().get_user_collections(username)

        fake_client = BlockingFakeBangumiClient()
        service = BangumiSyncService(
            BangumiConfig(username="user", access_token="token"),
            client_factory=lambda _: fake_client,
        )
        first = await service.start()
        await fake_client.started.wait()
        second = await service.start()

        assert second.reused is True
        assert second.task_id == first.task_id
        fake_client.release.set()
        assert service._active_task is not None
        await service._active_task

    asyncio.run(scenario())


def test_watched_collections_are_fully_synced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'sync.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()

    fake_client = FakeBangumiClient()
    fake_client.collections.extend([
        BangumiCollection(30, "COLLECTED"),
        BangumiCollection(40, "DROPPED"),
        BangumiCollection(50, "ON_HOLD"),
    ])
    service = BangumiSyncService(
        BangumiConfig(username="user", access_token="token"),
        client_factory=lambda _: fake_client,
    )

    result = asyncio.run(service.sync_now())

    from backend.app.database.session import session_scope

    with session_scope() as session:
        watched = session.scalar(select(Subject).where(Subject.bangumi_subject_id == 30))
        dropped = session.scalar(select(Subject).where(Subject.bangumi_subject_id == 40))
        on_hold = session.scalar(select(Subject).where(Subject.bangumi_subject_id == 50))
        assert result.status == "SUCCESS"
        assert watched is not None and watched.collection_type == "COLLECTED"
        assert session.scalar(select(Episode).where(Episode.subject_id == watched.id)) is not None
        assert dropped is not None and dropped.collection_type == "DROPPED"
        assert on_hold is not None and on_hold.collection_type == "ON_HOLD"


def test_ambiguous_local_title_hydrates_matching_related_subject(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'related.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()
    from backend.app.database.session import session_scope

    with session_scope() as session:
        parent = Subject(
            bangumi_subject_id=212003, name="ウマ娘 プリティーダービー",
            aliases='["Uma Musume Pretty Derby"]', collection_type="COLLECTED",
        )
        related = Subject(bangumi_subject_id=380448, name="赛马娘 Pretty Derby 巅峰之路")
        session.add_all([parent, related])
        session.flush()
        session.add(SubjectRelation(
            subject_id=parent.id, related_subject_id=related.id, relation_type="相同世界观",
        ))
        session.add(MediaFile(
            path=str(tmp_path / "Road to the Top 01.mp4"), filename="Road to the Top 01.mp4",
            file_size=1, mtime_ns=1, last_scanned_at=datetime.now(UTC),
            review_reason="AMBIGUOUS_SUBJECT",
            parse_result='{"normalized_title":"uma musume pretty derby road to the top"}',
        ))

    class RelatedClient(FakeBangumiClient):
        async def get_subject(self, subject_id: int):
            if subject_id == 380448:
                return BangumiSubject(
                    380448, "ウマ娘 プリティーダービー ROAD TO THE TOP", "赛马娘 Pretty Derby 巅峰之路",
                    "", "https://bgm.tv/subject/380448", "", 2, date(2023, 4, 16), "FINISHED", 4,
                    aliases=("Uma Musume: Pretty Derby - Road to the Top",),
                )
            return await super().get_subject(subject_id)

        async def get_episodes(self, subject_id: int):
            if subject_id == 380448:
                return [BangumiEpisode(1185561 + number, "MAIN", number, str(number), "", "", None) for number in range(1, 5)]
            return await super().get_episodes(subject_id)

        async def get_subject_relations(self, subject_id: int):
            return [] if subject_id == 380448 else await super().get_subject_relations(subject_id)

    service = BangumiSyncService(BangumiConfig(), client_factory=lambda _: RelatedClient())
    asyncio.run(service._sync_locally_relevant_relations(RelatedClient()))

    with session_scope() as session:
        related = session.scalar(select(Subject).where(Subject.bangumi_subject_id == 380448))
        assert related is not None and related.keep_forever is True
        assert "Road to the Top" in related.aliases
        assert session.scalar(select(func.count()).select_from(Episode).where(Episode.subject_id == related.id)) == 4
