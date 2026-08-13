from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import exists, or_, select

from backend.app.database.models import (
    DownloadJob,
    DownloadJobEpisode,
    Episode,
    EpisodeFile,
    MediaFile,
    Subject,
)
from backend.app.database.session import session_scope
from backend.app.modules.release_preferences import is_ani_group, media_release_group


class DemandPlanner:
    """Calculate downloadable episodes without persisting a second status source."""

    def wanted_episode_ids(self, *, today: date | None = None) -> list[int]:
        air_date = today or date.today()
        download_job = (
            select(DownloadJobEpisode.id)
            .join(DownloadJob, DownloadJob.id == DownloadJobEpisode.job_id)
            .where(
                DownloadJobEpisode.episode_id == Episode.id,
                DownloadJob.state.in_({
                    "CREATED", "QUEUED", "DOWNLOADING", "STALLED", "COMPLETED", "IMPORTING",
                }),
            )
        )
        with session_scope() as session:
            episodes = list(session.scalars(
                select(Episode.id)
                .join(Subject, Subject.id == Episode.subject_id)
                .where(
                    Subject.collection_type == "DOING",
                    Episode.episode_type == "MAIN",
                    Episode.air_date.is_not(None),
                    Episode.air_date <= air_date,
                    Episode.watched.is_(False),
                    or_(
                        Episode.bangumi_watch_status.is_(None),
                        Episode.bangumi_watch_status != "WATCHED",
                    ),
                    Episode.ignored.is_(False),
                    ~exists(download_job),
                )
                .order_by(Subject.id, Episode.sort_number, Episode.id)
            ))
            if not episodes:
                return []
            media_by_episode: dict[int, list[MediaFile]] = {episode_id: [] for episode_id in episodes}
            for episode_id, media in session.execute(
                select(EpisodeFile.episode_id, MediaFile)
                .join(MediaFile, MediaFile.id == EpisodeFile.media_file_id)
                .where(
                    EpisodeFile.episode_id.in_(episodes),
                    MediaFile.exists.is_(True),
                    MediaFile.ignored.is_(False),
                )
            ):
                media_by_episode[episode_id].append(media)
            air_dates = dict(session.execute(
                select(Episode.id, Episode.air_date).where(Episode.id.in_(episodes))
            ).all())
            wanted: list[int] = []
            for episode_id in episodes:
                media = media_by_episode[episode_id]
                if not media:
                    wanted.append(episode_id)
                    continue
                episode_air_date = air_dates[episode_id]
                if (
                    episode_air_date is not None
                    and episode_air_date <= air_date - timedelta(days=3)
                    and all(is_ani_group(media_release_group(item.parse_result, item.filename)) for item in media)
                ):
                    wanted.append(episode_id)
            return wanted
