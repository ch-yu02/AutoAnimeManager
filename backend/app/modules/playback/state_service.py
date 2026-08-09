from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.config import PlayerConfig
from backend.app.database.models import Episode, EpisodeFile, MediaFile, PlaybackState, Subject
from backend.app.database.session import session_scope


def state_view(state: PlaybackState, episode: Episode | None = None, media: MediaFile | None = None) -> dict[str, object]:
    return {
        "episode_id": state.episode_id,
        "media_file_id": state.media_file_id,
        "position_seconds": state.position_seconds,
        "duration_seconds": state.duration_seconds,
        "progress_ratio": state.progress_ratio,
        "watched": state.watched,
        "watched_source": state.watched_source,
        "last_played_at": state.last_played_at,
        "completed_at": state.completed_at,
        "episode": (
            {
                "id": episode.id, "subject_id": episode.subject_id,
                "display_number": episode.display_number, "name": episode.name_cn or episode.name,
            }
            if episode else None
        ),
        "media": ({"id": media.id, "path": media.path, "exists": media.exists} if media else None),
    }


class PlaybackStateService:
    def __init__(self, settings_provider) -> None:
        self.settings_provider = settings_provider

    def playable_media(self, episode_id: int) -> tuple[Episode, MediaFile]:
        with session_scope() as session:
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise LookupError("episode_not_found")
            media = session.scalar(
                select(MediaFile)
                .join(EpisodeFile, EpisodeFile.media_file_id == MediaFile.id)
                .where(
                    EpisodeFile.episode_id == episode.id,
                    MediaFile.exists.is_(True),
                    MediaFile.ignored.is_(False),
                )
                .order_by(EpisodeFile.is_primary.desc(), EpisodeFile.confidence.desc(), MediaFile.id)
            )
            if media is None:
                raise LookupError("media_not_ready")
            session.expunge(episode)
            session.expunge(media)
            return episode, media

    def begin(self, episode_id: int, media_file_id: int) -> dict[str, object]:
        now = datetime.now(UTC)
        with session_scope() as session:
            state = session.scalar(select(PlaybackState).where(PlaybackState.episode_id == episode_id))
            if state is None:
                state = PlaybackState(episode_id=episode_id, media_file_id=media_file_id)
                session.add(state)
            state.media_file_id = media_file_id
            state.last_played_at = now
            session.flush()
            return state_view(state)

    def record(
        self,
        episode_id: int,
        media_file_id: int,
        position_seconds: float,
        duration_seconds: float | None,
        *,
        ended: bool = False,
    ) -> dict[str, object]:
        config: PlayerConfig = self.settings_provider()
        now = datetime.now(UTC)
        position = max(0.0, float(position_seconds))
        duration = float(duration_seconds) if duration_seconds and duration_seconds > 0 else None
        with session_scope() as session:
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise LookupError("episode_not_found")
            state = session.scalar(select(PlaybackState).where(PlaybackState.episode_id == episode_id))
            if state is None:
                state = PlaybackState(episode_id=episode_id, media_file_id=media_file_id)
                session.add(state)
            state.media_file_id = media_file_id
            state.last_played_at = now
            if ended or position >= config.minimum_progress_seconds:
                state.position_seconds = duration if ended and duration is not None else position
                state.duration_seconds = duration or state.duration_seconds
                effective_duration = state.duration_seconds
                state.progress_ratio = (
                    min(1.0, state.position_seconds / effective_duration)
                    if effective_duration and effective_duration > 0 else 0.0
                )
            remaining = (
                max(0.0, state.duration_seconds - state.position_seconds)
                if state.duration_seconds is not None else None
            )
            automatically_watched = ended or state.progress_ratio >= config.watched_ratio or (
                remaining is not None
                and state.position_seconds >= config.minimum_progress_seconds
                and remaining <= config.watched_remaining_seconds
            )
            if automatically_watched and state.watched_source != "MANUAL":
                state.watched = True
                state.watched_source = "AUTO"
                state.completed_at = state.completed_at or now
                episode.watched = True
            session.flush()
            return state_view(state, episode)

    def mark_watched(self, episode_id: int, watched: bool) -> dict[str, object]:
        now = datetime.now(UTC)
        with session_scope() as session:
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise LookupError("episode_not_found")
            state = session.scalar(select(PlaybackState).where(PlaybackState.episode_id == episode_id))
            if state is None:
                state = PlaybackState(episode_id=episode_id)
                session.add(state)
            state.watched = watched
            state.watched_source = "MANUAL"
            state.completed_at = now if watched else None
            episode.watched = watched
            session.flush()
            return state_view(state, episode)

    def next_playable(self, episode_id: int) -> tuple[Episode, MediaFile] | None:
        with session_scope() as session:
            current = session.get(Episode, episode_id)
            if current is None or current.sort_number is None:
                return None
            episode = session.scalar(
                select(Episode)
                .where(
                    Episode.subject_id == current.subject_id,
                    Episode.episode_type == "MAIN",
                    Episode.sort_number > current.sort_number,
                    Episode.ignored.is_(False),
                )
                .order_by(Episode.sort_number, Episode.id)
                .limit(1)
            )
            if episode is None:
                return None
            media = session.scalar(
                select(MediaFile)
                .join(EpisodeFile, EpisodeFile.media_file_id == MediaFile.id)
                .where(
                    EpisodeFile.episode_id == episode.id,
                    MediaFile.exists.is_(True),
                    MediaFile.ignored.is_(False),
                )
                .order_by(EpisodeFile.is_primary.desc(), EpisodeFile.confidence.desc(), MediaFile.id)
                .limit(1)
            )
            if media is None:
                return None
            session.expunge(episode)
            session.expunge(media)
            return episode, media

    def first_unwatched(self, subject_id: int) -> dict[str, object] | None:
        with session_scope() as session:
            if session.get(Subject, subject_id) is None:
                raise LookupError("subject_not_found")
            episode = session.scalar(
                select(Episode).where(
                    Episode.subject_id == subject_id,
                    Episode.episode_type == "MAIN",
                    Episode.watched.is_(False),
                    Episode.ignored.is_(False),
                ).order_by(Episode.sort_number, Episode.id)
            )
            if episode is None:
                return None
            media = session.scalar(
                select(MediaFile)
                .join(EpisodeFile, EpisodeFile.media_file_id == MediaFile.id)
                .where(EpisodeFile.episode_id == episode.id, MediaFile.exists.is_(True), MediaFile.ignored.is_(False))
                .order_by(EpisodeFile.is_primary.desc(), MediaFile.id)
            )
            return {
                "episode_id": episode.id, "display_number": episode.display_number,
                "name": episode.name_cn or episode.name, "ready": media is not None,
            }

    def continue_watching(self, limit: int = 12) -> list[dict[str, object]]:
        with session_scope() as session:
            rows = session.execute(
                select(PlaybackState, Episode, Subject, MediaFile)
                .join(Episode, Episode.id == PlaybackState.episode_id)
                .join(Subject, Subject.id == Episode.subject_id)
                .outerjoin(MediaFile, MediaFile.id == PlaybackState.media_file_id)
                .where(PlaybackState.watched.is_(False), PlaybackState.position_seconds > 0)
                .order_by(PlaybackState.last_played_at.desc())
                .limit(limit)
            )
            return [
                {
                    **state_view(state, episode, media),
                    "subject": {"id": subject.id, "name": subject.name_cn or subject.name, "image_url": subject.image_url},
                    "playable": media is not None and media.exists and not media.ignored,
                }
                for state, episode, subject, media in rows
            ]
