from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.app.database.models import Subject
from backend.app.database.session import session_scope
from backend.app.modules.playback.state_service import PlaybackStateService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PlaybackSession:
    session_id: str
    episode_id: int
    media_file_id: int
    media_path: str
    subject_title: str
    episode_display_number: str
    episode_title: str
    initial_position_seconds: float
    duration_seconds: float | None
    created_at: datetime
    writeback_sent: bool = False

    def view(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "episode_id": self.episode_id,
            "media_file_id": self.media_file_id,
            "media_path": self.media_path,
            "subject_title": self.subject_title,
            "episode_display_number": self.episode_display_number,
            "episode_title": self.episode_title,
            "initial_position_seconds": self.initial_position_seconds,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at,
        }


class PlaybackSessionService:
    """Owns semantic playback sessions without owning a media player process."""

    def __init__(self, state_service: PlaybackStateService, settings_provider=None, writeback=None) -> None:
        self.state_service = state_service
        self.settings_provider = settings_provider
        self.writeback = writeback
        self._sessions: dict[str, PlaybackSession] = {}
        self._active_id: str | None = None
        self._lock = asyncio.Lock()

    async def create(self, episode_id: int, *, from_start: bool = False) -> dict[str, object]:
        episode, media = self.state_service.playable_media(episode_id)
        state = self.state_service.begin(episode.id, media.id)
        initial_position = 0.0 if from_start else float(state["position_seconds"] or 0.0)
        subject_title = ""
        subject_id = getattr(episode, "subject_id", None)
        if subject_id is not None:
            with session_scope() as session:
                subject = session.get(Subject, subject_id)
                if subject is not None:
                    subject_title = subject.name_cn or subject.name
        session = PlaybackSession(
            session_id=str(uuid.uuid4()),
            episode_id=episode.id,
            media_file_id=media.id,
            media_path=media.path,
            subject_title=subject_title,
            episode_display_number=str(getattr(episode, "display_number", "") or ""),
            episode_title=(
                str(getattr(episode, "name_cn", "") or getattr(episode, "name", "") or "")
            ),
            initial_position_seconds=initial_position,
            duration_seconds=state.get("duration_seconds"),
            created_at=datetime.now(UTC),
            writeback_sent=bool(state.get("watched")),
        )
        async with self._lock:
            self._sessions.clear()
            self._sessions[session.session_id] = session
            self._active_id = session.session_id
        return session.view()

    async def progress(
        self,
        session_id: str,
        position_seconds: float,
        duration_seconds: float | None,
        *,
        ended: bool = False,
    ) -> dict[str, object]:
        session = self._require(session_id)
        state = self.state_service.record(
            session.episode_id,
            session.media_file_id,
            position_seconds,
            duration_seconds,
            ended=ended,
        )
        if state["watched"] and not session.writeback_sent:
            session.writeback_sent = await self._writeback(session.episode_id, True)
        next_item = self.state_service.next_playable(session.episode_id) if ended else None
        return {
            "session_id": session_id,
            **state,
            "next_episode_id": next_item[0].id if next_item is not None else None,
        }

    async def close(self, session_id: str) -> dict[str, str]:
        async with self._lock:
            if session_id not in self._sessions:
                raise LookupError("playback_session_not_found")
            self._sessions.pop(session_id, None)
            if self._active_id == session_id:
                self._active_id = None
        return {"status": "closed", "session_id": session_id}

    def get(self, session_id: str) -> PlaybackSession:
        return self._require(session_id)

    def continue_watching(self) -> list[dict[str, object]]:
        return self.state_service.continue_watching()

    def active_media_file_ids(self) -> set[int]:
        return {session.media_file_id for session in self._sessions.values()}

    def first_unwatched(self, subject_id: int) -> dict[str, object] | None:
        return self.state_service.first_unwatched(subject_id)

    async def mark_watched(self, episode_id: int, watched: bool) -> dict[str, object]:
        state = self.state_service.mark_watched(episode_id, watched)
        await self._writeback(episode_id, watched)
        return state

    def _require(self, session_id: str) -> PlaybackSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise LookupError("playback_session_not_found")
        return session

    async def _writeback(self, episode_id: int, watched: bool) -> bool:
        if (
            self.settings_provider is None
            or self.writeback is None
            or not self.settings_provider().bangumi_writeback_enabled
        ):
            return True
        try:
            await self.writeback(episode_id, watched)
            return True
        except Exception:
            logger.exception("Bangumi 观看状态回写失败", extra={"episode_id": episode_id})
            return False
