from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.app.modules.playback.state_service import PlaybackStateService

logger = logging.getLogger(__name__)


class WebPlaybackError(RuntimeError):
    pass


@dataclass(slots=True)
class WebPlaybackSession:
    id: str
    episode_id: int
    media_file_id: int
    directory: Path
    process: asyncio.subprocess.Process
    start_seconds: float
    initial_position_seconds: float
    duration_seconds: float | None
    writeback_sent: bool = False


def _ffmpeg_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _resolve_start_seconds(
    resume_seconds: float,
    duration_seconds: float | None,
    *,
    from_start: bool,
    position_seconds: float | None,
) -> float:
    start_seconds = (
        max(0.0, float(position_seconds))
        if position_seconds is not None
        else 0.0 if from_start else max(0.0, float(resume_seconds))
    )
    if duration_seconds:
        return min(start_seconds, max(0.0, float(duration_seconds) - 0.1))
    return start_seconds


class WebPlaybackService:
    def __init__(self, state_service: PlaybackStateService, settings_provider, writeback=None) -> None:
        self.state_service = state_service
        self.settings_provider = settings_provider
        self.writeback = writeback
        self.active: WebPlaybackSession | None = None
        self._lock = asyncio.Lock()

    async def _subtitle_filter(self, media_path: Path) -> str | None:
        external = sorted(
            (
                candidate for candidate in media_path.parent.iterdir()
                if candidate.is_file()
                and candidate.suffix.casefold() in {".ass", ".ssa", ".srt"}
                and candidate.stem.startswith(media_path.stem)
            ),
            key=lambda candidate: ("chs" not in candidate.name.casefold(), candidate.name),
        )
        if external:
            return f"subtitles=filename='{_ffmpeg_filter_path(external[0])}'"
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "s:0",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(media_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await probe.communicate()
        if probe.returncode == 0 and output.strip():
            return f"subtitles=filename='{_ffmpeg_filter_path(media_path)}':si=0"
        return None

    async def start(
        self,
        episode_id: int,
        *,
        from_start: bool = False,
        position_seconds: float | None = None,
    ) -> dict[str, object]:
        async with self._lock:
            await self._stop_locked()
            episode, media = self.state_service.playable_media(episode_id)
            state = self.state_service.begin(episode.id, media.id)
            duration_seconds = media.duration_seconds or state["duration_seconds"]
            start_seconds = _resolve_start_seconds(
                float(state["position_seconds"] or 0),
                duration_seconds,
                from_start=from_start,
                position_seconds=position_seconds,
            )
            directory = Path(tempfile.mkdtemp(prefix="autoanime-web-playback-"))
            session_id = uuid.uuid4().hex
            playlist = directory / "index.m3u8"
            segment_pattern = directory / "segment-%05d.ts"
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            ]
            command.extend(["-i", media.path, "-map", "0:v:0", "-map", "0:a:0?"])
            subtitle_filter = await self._subtitle_filter(Path(media.path))
            if subtitle_filter:
                command.extend(["-vf", subtitle_filter])
            command.extend([
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                "-force_key_frames", "expr:gte(t,n_forced*4)",
                "-f", "hls", "-hls_time", "4", "-hls_playlist_type", "vod",
                "-hls_flags", "independent_segments+temp_file",
                "-hls_segment_filename", str(segment_pattern), str(playlist),
            ])
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                shutil.rmtree(directory, ignore_errors=True)
                raise WebPlaybackError("无法启动 FFmpeg 网页转码") from exc
            session = WebPlaybackSession(
                id=session_id,
                episode_id=episode.id,
                media_file_id=media.id,
                directory=directory,
                process=process,
                start_seconds=0.0,
                initial_position_seconds=start_seconds,
                duration_seconds=duration_seconds,
                writeback_sent=bool(state["watched"]),
            )
            self.active = session

        _, stderr = await process.communicate()
        async with self._lock:
            if self.active is not session:
                raise WebPlaybackError("整集转码已取消")
            if process.returncode != 0 or not playlist.is_file():
                self.active = None
                shutil.rmtree(directory, ignore_errors=True)
                error = stderr.decode("utf-8", errors="replace")[-1000:]
                raise WebPlaybackError(f"FFmpeg 无法完成整集转码：{error or '未知错误'}")
            return self.view(session)

    def view(self, session: WebPlaybackSession) -> dict[str, object]:
        return {
            "session_id": session.id,
            "episode_id": session.episode_id,
            "media_file_id": session.media_file_id,
            "playlist_url": f"/api/playback/web/{session.id}/index.m3u8",
            "start_seconds": session.start_seconds,
            "initial_position_seconds": session.initial_position_seconds,
            "duration_seconds": session.duration_seconds,
        }

    def require(self, session_id: str) -> WebPlaybackSession:
        if self.active is None or self.active.id != session_id:
            raise LookupError("web_playback_not_found")
        return self.active

    async def progress(
        self, session_id: str, position_seconds: float, duration_seconds: float | None, *, ended: bool = False,
    ) -> dict[str, object]:
        session = self.require(session_id)
        absolute_position = session.start_seconds + max(0.0, position_seconds)
        total_duration = session.duration_seconds or (
            session.start_seconds + duration_seconds if duration_seconds else None
        )
        state = self.state_service.record(
            session.episode_id, session.media_file_id, absolute_position, total_duration, ended=ended,
        )
        if (
            state["watched"] and not session.writeback_sent and self.writeback is not None
            and self.settings_provider().bangumi_writeback_enabled
        ):
            session.writeback_sent = True
            try:
                await self.writeback(session.episode_id, True)
            except Exception:
                logger.exception("网页播放的 Bangumi 已看状态回写失败", extra={"episode_id": session.episode_id})
        return state

    async def stop(self, session_id: str | None = None) -> None:
        async with self._lock:
            if session_id is None or (self.active is not None and self.active.id == session_id):
                await self._stop_locked()

    async def _stop_locked(self) -> None:
        session = self.active
        self.active = None
        if session is None:
            return
        if session.process.returncode is None:
            try:
                session.process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(session.process.wait(), 3)
            except asyncio.TimeoutError:
                session.process.kill()
                await session.process.wait()
        shutil.rmtree(session.directory, ignore_errors=True)

    async def shutdown(self) -> None:
        await self.stop()
