from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from backend.app.config import get_settings
from backend.app.database.models import DownloadJob, DownloadJobEpisode, Episode, EpisodeFile, MediaFile, Subject
from backend.app.database.session import create_schema, get_engine, session_scope
from backend.app.modules.scheduler import DemandPlanner


def test_wanted_is_only_unwatched_aired_main_episode_of_doing_subject(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'demand.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()
    today = date(2026, 8, 12)

    with session_scope() as session:
        doing = Subject(bangumi_subject_id=1, name="Doing", collection_type="DOING")
        wish = Subject(bangumi_subject_id=2, name="Wish", collection_type="WISH")
        session.add_all([doing, wish])
        session.flush()

        def episode(subject: Subject, bangumi_id: int, **values) -> Episode:
            item = Episode(
                bangumi_episode_id=bangumi_id,
                subject_id=subject.id,
                episode_type=values.pop("episode_type", "MAIN"),
                display_number=str(bangumi_id),
                air_date=values.pop("air_date", today),
                **values,
            )
            session.add(item)
            session.flush()
            return item

        wanted = episode(doing, 101)
        episode(doing, 102, watched=True)
        episode(doing, 103, bangumi_watch_status="WATCHED")
        episode(doing, 104, episode_type="SP")
        episode(doing, 105, episode_type="OP")
        episode(doing, 106, episode_type="ED")
        episode(doing, 107, air_date=today + timedelta(days=1))
        episode(doing, 108, ignored=True)
        episode(wish, 201)
        ready = episode(doing, 109)
        media = MediaFile(
            path=str(tmp_path / "ready.mkv"), filename="ready.mkv", file_size=1, mtime_ns=1,
            exists=True, ignored=False, last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
        session.add(EpisodeFile(
            episode_id=ready.id, media_file_id=media.id, mapping_source="TEST",
            confidence=1, is_primary=True,
        ))
        queued = episode(doing, 110)
        job = DownloadJob(
            id="job", magnet_uri="magnet:?xt=urn:btih:" + "a" * 40,
            magnet_hash="a" * 40, torrent_hash="a" * 40,
            subject_id=doing.id, save_path=str(tmp_path),
        )
        session.add(job)
        session.flush()
        session.add(DownloadJobEpisode(job_id=job.id, episode_id=queued.id))
        failed = episode(doing, 111)
        failed_job = DownloadJob(
            id="failed-job", magnet_uri="magnet:?xt=urn:btih:" + "b" * 40,
            magnet_hash="b" * 40, torrent_hash="b" * 40,
            subject_id=doing.id, save_path=str(tmp_path), state="FAILED",
        )
        session.add(failed_job)
        session.flush()
        session.add(DownloadJobEpisode(job_id=failed_job.id, episode_id=failed.id))

        def ready_media(item: Episode, media_id: int, group: str, *, aired_days_ago: int) -> None:
            item.air_date = today - timedelta(days=aired_days_ago)
            media = MediaFile(
                id=media_id,
                path=str(tmp_path / f"{group}-{media_id}.mkv"),
                filename=f"[{group}] Doing - {item.display_number}.mkv",
                file_size=1,
                mtime_ns=1,
                exists=True,
                ignored=False,
                parse_result=f'{{"release_group":"{group}"}}',
                last_scanned_at=datetime.now(UTC),
            )
            session.add(media)
            session.flush()
            session.add(EpisodeFile(
                episode_id=item.id,
                media_file_id=media.id,
                mapping_source="TEST",
                confidence=1,
                is_primary=True,
            ))

        old_ani = episode(doing, 112)
        ready_media(old_ani, 112, "ANi", aired_days_ago=3)
        fresh_ani = episode(doing, 113)
        ready_media(fresh_ani, 113, "ANi", aired_days_ago=2)
        fansub = episode(doing, 114)
        ready_media(fansub, 114, "字幕组", aired_days_ago=10)

    assert DemandPlanner().wanted_episode_ids(today=today) == [wanted.id, failed.id, old_ani.id]
