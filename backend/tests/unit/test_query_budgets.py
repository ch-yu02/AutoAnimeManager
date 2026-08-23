from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import event, select

from backend.app.api.library import review_queue
from backend.app.api.subjects import list_episodes
from backend.app.config import get_settings
from backend.app.database.models import (
    DownloadJob,
    DownloadJobEpisode,
    Episode,
    EpisodeFile,
    MediaFile,
    Subject,
    TaskRun,
)
from backend.app.database.session import create_schema, get_engine, session_scope
from backend.app.modules.cleanup import CleanupService
from backend.app.modules.download.service import DownloadService
from backend.app.modules.scheduler import SchedulerService


def _reset_caches() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _count_queries(operation) -> int:
    engine = get_engine()
    count = 0

    def increment(*_args) -> None:
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", increment)
    try:
        operation()
    finally:
        event.remove(engine, "before_cursor_execute", increment)
    return count


def test_list_endpoints_use_fixed_query_budgets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'queries.db'}")
    _reset_caches()
    create_schema()
    now = datetime.now(UTC)
    with session_scope() as session:
        subject = Subject(
            bangumi_subject_id=1,
            name="Query Budget",
            collection_type="DOING",
            air_status="AIRING",
        )
        session.add(subject)
        session.flush()
        for number in range(1, 13):
            episode = Episode(
                bangumi_episode_id=100 + number,
                subject_id=subject.id,
                episode_type="MAIN",
                sort_number=number,
                display_number=str(number),
            )
            session.add(episode)
            session.flush()
            media = MediaFile(
                path=str(tmp_path / f"{number}.mkv"),
                filename=f"{number}.mkv",
                file_size=1,
                mtime_ns=1,
                subject_id=subject.id,
                subject_mapping_source="AUTO",
                exists=True,
                ignored=False,
                last_scanned_at=now,
            )
            session.add(media)
            session.flush()
            session.add(EpisodeFile(
                episode_id=episode.id,
                media_file_id=media.id,
                mapping_source="AUTO",
                confidence=1,
            ))
        torrent_hash = "1" * 40
        job = DownloadJob(
            id="job-1",
            magnet_uri=f"magnet:?xt=urn:btih:{torrent_hash}",
            magnet_hash=torrent_hash,
            torrent_hash=torrent_hash,
            subject_id=subject.id,
            state="IMPORTED",
            save_path=str(tmp_path),
        )
        session.add(job)
        session.flush()
        first_episode = session.scalar(select(Episode).order_by(Episode.id))
        assert first_episode is not None
        session.add(DownloadJobEpisode(job_id=job.id, episode_id=first_episode.id))
        subject_id = subject.id

    assert _count_queries(lambda: asyncio.run(list_episodes(subject_id))) == 4
    assert _count_queries(lambda: asyncio.run(review_queue())) == 4

    downloads = DownloadService()
    try:
        assert _count_queries(downloads.list) == 3
    finally:
        asyncio.run(downloads.stop())
    _reset_caches()


def test_scheduler_and_cleanup_prefilters_have_constant_query_cost(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'background.db'}")
    _reset_caches()
    create_schema()
    now = datetime.now(UTC)
    with session_scope() as session:
        for index in range(100):
            session.add(Subject(
                bangumi_subject_id=1000 + index,
                name=f"Subject {index}",
                air_status="AIRING",
            ))
        for index, task_name in enumerate(("BangumiSync", "LibraryScan", "Cleanup")):
            session.add(TaskRun(
                id=f"run-{index}",
                task_name=task_name,
                trigger="SCHEDULED",
                status="SUCCESS",
                attempt=1,
                started_at=now,
                finished_at=now,
            ))

    scheduler = SchedulerService()
    assert _count_queries(
        lambda: scheduler._latest_many(("BangumiSync", "LibraryScan", "Cleanup"))
    ) == 1
    assert _count_queries(CleanupService().candidates) == 1
    _reset_caches()
