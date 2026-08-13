from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app.config import get_settings
from backend.app.database.models import (
    CleanupRecord,
    DownloadJob,
    DownloadJobEpisode,
    Episode,
    EpisodeFile,
    MediaFile,
    PlaybackState,
    Subject,
)
from backend.app.database.session import create_schema, get_engine, session_scope
from backend.app.modules.cleanup import CleanupNotAllowed, CleanupService


def _prepare(tmp_path: Path, monkeypatch) -> tuple[int, list[int], list[Path]]:
    library = tmp_path / "library"
    quarantine = tmp_path / "quarantine"
    library.mkdir()
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'cleanup.db'}")
    monkeypatch.setenv("AUTOANIME_STORAGE__LIBRARY_ROOTS", f'["{library}"]')
    monkeypatch.setenv("AUTOANIME_STORAGE__QUARANTINE_PATH", str(quarantine))
    monkeypatch.setenv("AUTOANIME_CLEANUP__RETENTION_DAYS", "0")
    monkeypatch.setenv("AUTOANIME_CLEANUP__QUARANTINE_DAYS", "1")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()
    paths = [library / "Episode 1.mkv", library / "Episode 2.mkv"]
    for index, path in enumerate(paths, start=1):
        path.write_bytes(f"video-{index}".encode())
    with session_scope() as session:
        subject = Subject(
            bangumi_subject_id=42,
            name="Cleanup Anime",
            collection_type="COLLECTED",
            air_status="FINISHED",
            total_main_episodes=2,
        )
        session.add(subject)
        session.flush()
        episode_ids = []
        for index, path in enumerate(paths, start=1):
            episode = Episode(
                bangumi_episode_id=4200 + index,
                subject_id=subject.id,
                episode_type="MAIN",
                sort_number=index,
                display_number=str(index),
                air_date=date.today() - timedelta(days=index),
                watched=True,
                successfully_imported_at=datetime.now(UTC) - timedelta(days=2),
            )
            session.add(episode)
            session.flush()
            episode_ids.append(episode.id)
            media = MediaFile(
                path=str(path), filename=path.name, file_size=path.stat().st_size,
                mtime_ns=path.stat().st_mtime_ns, subject_id=subject.id,
                exists=True, ignored=False, last_scanned_at=datetime.now(UTC),
            )
            session.add(media)
            session.flush()
            session.add(EpisodeFile(
                episode_id=episode.id, media_file_id=media.id,
                mapping_source="DOWNLOAD_JOB", confidence=1, is_primary=True,
            ))
            session.add(PlaybackState(
                episode_id=episode.id, media_file_id=media.id, watched=True,
                watched_source="MANUAL", completed_at=datetime.now(UTC) - timedelta(days=2),
            ))
            torrent_hash = f"{index:040x}"
            job = DownloadJob(
                id=f"job-{index}", magnet_uri=f"magnet:?xt=urn:btih:{torrent_hash}",
                magnet_hash=torrent_hash, torrent_hash=torrent_hash,
                subject_id=subject.id, state="IMPORTED", save_path=str(library),
                progress=1, imported_at=datetime.now(UTC),
            )
            session.add(job)
            session.flush()
            session.add(DownloadJobEpisode(job_id=job.id, episode_id=episode.id))
        return subject.id, episode_ids, paths


@pytest.mark.anyio
async def test_manual_keep_is_highest_priority_cleanup_blocker(tmp_path: Path, monkeypatch) -> None:
    subject_id, _, _ = _prepare(tmp_path, monkeypatch)
    service = CleanupService()
    assert service.eligibility(subject_id)["eligible"] is True

    service.set_keep_forever(subject_id, True)
    blocked = service.eligibility(subject_id)

    assert blocked["eligible"] is False
    assert "条目已设为永久保留" in blocked["blockers"]
    with pytest.raises(CleanupNotAllowed):
        await service.quarantine(subject_id)


@pytest.mark.anyio
async def test_quarantine_restore_and_permanent_delete_preserve_history(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id, episode_ids, paths = _prepare(tmp_path, monkeypatch)
    service = CleanupService()

    quarantined = await service.quarantine(subject_id)
    assert quarantined["status"] == "QUARANTINED"
    assert quarantined["bytes_total"] == 14
    assert all(not path.exists() for path in paths)
    assert all(Path(item["quarantine_path"]).is_file() for item in quarantined["files"])

    restored = await service.restore(str(quarantined["id"]))
    assert restored["status"] == "RESTORED"
    assert all(path.is_file() for path in paths)

    second = await service.quarantine(subject_id)
    deleted = await service.permanently_delete(str(second["id"]))
    assert deleted["status"] == "DELETED"
    assert all(not Path(item["quarantine_path"]).exists() for item in second["files"])
    with session_scope() as session:
        assert session.get(Subject, subject_id) is not None
        assert list(session.scalars(select(Episode).where(Episode.id.in_(episode_ids))))
        assert session.scalar(select(func.count()).select_from(PlaybackState)) == 2
        assert session.scalar(select(func.count()).select_from(DownloadJob)) == 2
        assert session.scalar(select(func.count()).select_from(MediaFile)) == 0
        assert session.scalar(select(func.count()).select_from(CleanupRecord)) == 2


@pytest.mark.anyio
async def test_active_playback_and_unresolved_mapping_block_cleanup(tmp_path: Path, monkeypatch) -> None:
    subject_id, _, _ = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        media = session.scalar(select(MediaFile).where(MediaFile.subject_id == subject_id))
        assert media is not None
        media.review_reason = "AMBIGUOUS_EPISODE"
        media_id = media.id
    service = CleanupService(lambda: {media_id})

    result = service.eligibility(subject_id)

    assert "存在 unresolved mapping" in result["blockers"]
    assert "媒体文件当前正在播放" in result["blockers"]


@pytest.mark.anyio
async def test_unknown_total_and_missing_import_proof_do_not_block_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id, episode_ids, _ = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        subject = session.get(Subject, subject_id)
        episode = session.get(Episode, episode_ids[0])
        assert subject is not None
        assert episode is not None
        subject.total_main_episodes = None
        episode.successfully_imported_at = None

    result = CleanupService().eligibility(subject_id)

    assert result["eligible"] is True
    assert result["blockers"] == []


def test_watched_episode_without_completion_time_blocks_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id, episode_ids, _ = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        playback = session.scalar(select(PlaybackState).where(
            PlaybackState.episode_id == episode_ids[0]
        ))
        assert playback is not None
        playback.completed_at = None

    result = CleanupService().eligibility(subject_id)

    assert result["eligible"] is False
    assert "部分 MAIN Episode 缺少完成时间" in result["blockers"]
    assert result["eligible_at"] is None


def test_subject_without_main_episodes_is_ineligible_without_breaking_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id, _, _ = _prepare(tmp_path, monkeypatch)
    with session_scope() as session:
        empty = Subject(
            bangumi_subject_id=43,
            name="Related Subject Without Episodes",
            air_status="FINISHED",
            total_main_episodes=None,
        )
        session.add(empty)
        session.flush()
        empty_id = empty.id

    service = CleanupService()
    result = service.eligibility(empty_id)

    assert result["eligible"] is False
    assert result["eligible_at"] is None
    assert "没有 MAIN Episode" in result["blockers"]
    assert [item["subject_id"] for item in service.candidates()] == [subject_id]


@pytest.mark.anyio
async def test_automatic_cleanup_quarantines_then_rechecks_before_delete(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id, _, _ = _prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTOANIME_CLEANUP__ENABLED", "true")
    get_settings.cache_clear()
    service = CleanupService()
    now = datetime.now(UTC)

    first = await service.run_automatic(now=now)
    assert first == {"enabled": True, "quarantined": 1, "deleted": 0, "failed": 0}

    service.set_keep_forever(subject_id, True)
    blocked = await service.run_automatic(now=now + timedelta(days=2))
    assert blocked == {"enabled": True, "quarantined": 0, "deleted": 0, "failed": 1}

    service.set_keep_forever(subject_id, False)
    deleted = await service.run_automatic(now=now + timedelta(days=2))
    assert deleted == {"enabled": True, "quarantined": 0, "deleted": 1, "failed": 0}
