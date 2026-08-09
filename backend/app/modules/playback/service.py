from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.app.config import PlayerConfig
from backend.app.database.models import Episode, MediaFile
from backend.app.modules.playback.process_manager import ManagedMpv, MpvProcessManager, PlaybackBusyError
from backend.app.modules.playback.state_service import PlaybackStateService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ActivePlayback:
    episode: Episode
    media: MediaFile
    managed: ManagedMpv
    position_seconds: float = 0
    duration_seconds: float | None = None
    paused: bool = False
    completed_naturally: bool = False
    auto_advance_suppressed: bool = False
    pending_seek_save: bool = False
    writeback_sent: bool = False


class PlaybackService:
    def __init__(
        self,
        state_service: PlaybackStateService,
        process_manager: MpvProcessManager,
        settings_provider,
        writeback=None,
    ) -> None:
        self.state_service = state_service
        self.process_manager = process_manager
        self.settings_provider = settings_provider
        self.writeback = writeback
        self.active: ActivePlayback | None = None
        self.last_episode_id: int | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._periodic_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def start(self, episode_id: int, *, from_start: bool = False) -> dict[str, object]:
        async with self._lock:
            if self.active is not None:
                raise PlaybackBusyError("已有受控 MPV 会话")
            episode, media = self.state_service.playable_media(episode_id)
            state = self.state_service.begin(episode.id, media.id)
            resume = 0.0 if from_start else float(state["position_seconds"] or 0)
            managed = await self.process_manager.launch(media.path, resume)
            active = ActivePlayback(
                episode=episode,
                media=media,
                managed=managed,
                position_seconds=resume,
                duration_seconds=state["duration_seconds"],
                writeback_sent=bool(state["watched"]),
            )
            self.active = active
            self.last_episode_id = episode.id
            try:
                managed.client.add_event_handler(self._handle_event)
                for observer_id, name in enumerate(("time-pos", "duration", "pause"), start=1):
                    await managed.client.observe(observer_id, name)
            except Exception:
                self.active = None
                try:
                    await self.process_manager.stop(managed)
                finally:
                    await self.process_manager.release(managed)
                raise
            self._periodic_task = asyncio.create_task(self._periodic_save(active))
            self._monitor_task = asyncio.create_task(self._monitor(active))
            return self.current()

    def current(self) -> dict[str, object]:
        active = self.active
        if active is None:
            return {"status": "IDLE", "episode_id": None}
        next_item = self.state_service.next_playable(active.episode.id)
        return {
            "status": "PAUSED" if active.paused else "PLAYING",
            "episode_id": active.episode.id,
            "media_file_id": active.media.id,
            "path": active.media.path,
            "position_seconds": active.position_seconds,
            "duration_seconds": active.duration_seconds,
            "progress_ratio": (
                min(1.0, active.position_seconds / active.duration_seconds)
                if active.duration_seconds and active.duration_seconds > 0 else 0.0
            ),
            "has_next": next_item is not None,
        }

    async def pause(self) -> dict[str, object]:
        active = self._require_active()
        await active.managed.client.command(["set_property", "pause", True])
        active.paused = True
        await self._save(active)
        return self.current()

    async def resume(self) -> dict[str, object]:
        active = self._require_active()
        await active.managed.client.command(["set_property", "pause", False])
        active.paused = False
        await self._save(active)
        return self.current()

    async def seek(self, position_seconds: float) -> dict[str, object]:
        active = self._require_active()
        position = max(0.0, position_seconds)
        await active.managed.client.command(["set_property", "time-pos", position])
        active.pending_seek_save = False
        active.position_seconds = position
        await self._save(active)
        return self.current()

    async def stop(self) -> dict[str, object]:
        active = self._require_active()
        active.auto_advance_suppressed = True
        try:
            await self._save(active)
        except Exception:
            logger.exception("停止播放前保存观看进度失败", extra={"episode_id": active.episode.id})
        await self.process_manager.stop(active.managed)
        if self._monitor_task is not None:
            await asyncio.gather(self._monitor_task, return_exceptions=True)
        return {"status": "IDLE", "episode_id": None}

    async def play_next(self) -> dict[str, object]:
        episode_id = self.active.episode.id if self.active else self.last_episode_id
        if episode_id is None:
            raise LookupError("no_playback_history")
        next_item = self.state_service.next_playable(episode_id)
        if next_item is None:
            raise LookupError("next_episode_not_ready")
        if self.active is not None:
            await self.stop()
        return await self.start(next_item[0].id)

    async def mark_watched(self, episode_id: int, watched: bool) -> dict[str, object]:
        state = self.state_service.mark_watched(episode_id, watched)
        await self._writeback(episode_id, watched)
        return state

    async def shutdown(self) -> None:
        if self.active is not None:
            try:
                await self.stop()
            except Exception:
                logger.exception("关闭 MPV 会话失败")

    def _require_active(self) -> ActivePlayback:
        if self.active is None:
            raise LookupError("no_active_playback")
        return self.active

    async def _periodic_save(self, active: ActivePlayback) -> None:
        interval = self.settings_provider().progress_save_interval_seconds
        try:
            while self.active is active:
                await asyncio.sleep(interval)
                if self.active is active:
                    try:
                        await self._save(active)
                    except Exception:
                        logger.exception("定时保存观看进度失败", extra={"episode_id": active.episode.id})
        except asyncio.CancelledError:
            pass

    async def _save(self, active: ActivePlayback, *, ended: bool = False) -> dict[str, object]:
        state = self.state_service.record(
            active.episode.id,
            active.media.id,
            active.position_seconds,
            active.duration_seconds,
            ended=ended,
        )
        if state["watched"] and not active.writeback_sent:
            active.writeback_sent = True
            await self._writeback(active.episode.id, True)
        return state

    async def _handle_event(self, event: dict[str, Any]) -> None:
        active = self.active
        if active is None:
            return
        event_name = event.get("event")
        if event_name == "property-change":
            name, data = event.get("name"), event.get("data")
            if name == "time-pos" and isinstance(data, (int, float)):
                active.position_seconds = max(0.0, float(data))
                if active.pending_seek_save:
                    active.pending_seek_save = False
                    await self._save(active)
            elif name == "duration" and isinstance(data, (int, float)) and data > 0:
                active.duration_seconds = float(data)
            elif name == "pause" and isinstance(data, bool):
                active.paused = data
                await self._save(active)
        elif event_name == "seek":
            active.pending_seek_save = True
        elif event_name == "end-file":
            active.completed_naturally = event.get("reason") == "eof"
            await self._save(active, ended=active.completed_naturally)
        elif event_name == "shutdown":
            await self._save(active)

    async def _monitor(self, active: ActivePlayback) -> None:
        await active.managed.process.wait()
        try:
            await self._save(active, ended=active.completed_naturally)
        except Exception:
            logger.exception("MPV 退出时保存观看进度失败", extra={"episode_id": active.episode.id})
        finally:
            if self._periodic_task is not None:
                self._periodic_task.cancel()
                await asyncio.gather(self._periodic_task, return_exceptions=True)
                self._periodic_task = None
            try:
                await self.process_manager.release(active.managed)
            finally:
                async with self._lock:
                    if self.active is active:
                        self.active = None
        if (
            active.completed_naturally
            and not active.auto_advance_suppressed
            and self.settings_provider().auto_play_next
        ):
            next_item = self.state_service.next_playable(active.episode.id)
            if next_item is not None:
                try:
                    await self.start(next_item[0].id)
                except Exception:
                    logger.exception("自动播放下一集失败")

    async def _writeback(self, episode_id: int, watched: bool) -> None:
        config: PlayerConfig = self.settings_provider()
        if not config.bangumi_writeback_enabled or self.writeback is None:
            return
        try:
            await self.writeback(episode_id, watched)
        except Exception:
            logger.exception("Bangumi 观看状态回写失败", extra={"episode_id": episode_id})
