from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.modules.playback.process_manager import MpvUnavailableError, PlaybackBusyError
from backend.app.modules.playback.service import PlaybackService
from backend.app.modules.playback.web_stream import WebPlaybackError, WebPlaybackService

router = APIRouter(tags=["playback"])


class PlaybackStartRequest(BaseModel):
    episode_id: int
    from_start: bool = False


class WebPlaybackStartRequest(PlaybackStartRequest):
    position_seconds: float | None = Field(default=None, ge=0)


class SeekRequest(BaseModel):
    position_seconds: float = Field(ge=0)


class WebProgressRequest(BaseModel):
    position_seconds: float = Field(ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    ended: bool = False


def _service(request: Request) -> PlaybackService:
    return request.app.state.playback_service


def _web_service(request: Request) -> WebPlaybackService:
    return request.app.state.web_playback_service


@router.post("/playback/web/start", status_code=status.HTTP_201_CREATED)
async def start_web_playback(payload: WebPlaybackStartRequest, request: Request) -> dict[str, object]:
    try:
        return await _web_service(request).start(
            payload.episode_id,
            from_start=payload.from_start,
            position_seconds=payload.position_seconds,
        )
    except LookupError as exc:
        raise _translate_error(exc) from exc
    except WebPlaybackError as exc:
        raise HTTPException(503, detail={"code": "web_playback_failed", "message": str(exc)}) from exc


@router.get("/playback/web/{session_id}/index.m3u8")
async def web_playlist(session_id: str, request: Request) -> FileResponse:
    try:
        session = _web_service(request).require(session_id)
    except LookupError as exc:
        raise HTTPException(404, detail="播放会话不存在") from exc
    return FileResponse(session.directory / "index.m3u8", media_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-store"})


@router.get("/playback/web/{session_id}/{segment_name}")
async def web_segment(session_id: str, segment_name: str, request: Request) -> FileResponse:
    if not segment_name.startswith("segment-") or not segment_name.endswith(".ts") or not segment_name[8:-3].isdigit():
        raise HTTPException(404, detail="视频分片不存在")
    try:
        session = _web_service(request).require(session_id)
    except LookupError as exc:
        raise HTTPException(404, detail="播放会话不存在") from exc
    segment = session.directory / segment_name
    if not segment.is_file():
        raise HTTPException(404, detail="视频分片尚未生成")
    return FileResponse(segment, media_type="video/mp2t", headers={"Cache-Control": "no-store"})


@router.post("/playback/web/{session_id}/progress")
async def web_progress(session_id: str, payload: WebProgressRequest, request: Request) -> dict[str, object]:
    try:
        return await _web_service(request).progress(
            session_id, payload.position_seconds, payload.duration_seconds, ended=payload.ended,
        )
    except LookupError as exc:
        raise HTTPException(404, detail="播放会话不存在") from exc


@router.delete("/playback/web/{session_id}")
async def stop_web_playback(session_id: str, request: Request) -> dict[str, str]:
    await _web_service(request).stop(session_id)
    return {"status": "stopped"}


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PlaybackBusyError):
        return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "playback_busy", "message": str(exc)})
    if isinstance(exc, MpvUnavailableError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "mpv_unavailable", "message": str(exc)})
    code = str(exc)
    if code in {"episode_not_found", "subject_not_found"}:
        return HTTPException(404, detail={"code": code, "message": "条目或章节不存在"})
    messages = {
        "media_not_ready": "章节没有可播放的本地文件",
        "no_active_playback": "当前没有受控播放器会话",
        "no_playback_history": "没有可用于定位下一集的播放记录",
        "next_episode_not_ready": "下一集尚未就绪",
    }
    return HTTPException(409, detail={"code": code, "message": messages.get(code, "播放操作失败")})


@router.post("/playback/start", status_code=status.HTTP_201_CREATED)
async def start_playback(payload: PlaybackStartRequest, request: Request) -> dict[str, object]:
    try:
        return await _service(request).start(payload.episode_id, from_start=payload.from_start)
    except (LookupError, PlaybackBusyError, MpvUnavailableError) as exc:
        raise _translate_error(exc) from exc


@router.get("/playback/current")
async def current_playback(request: Request) -> dict[str, object]:
    return _service(request).current()


@router.post("/playback/pause")
async def pause_playback(request: Request) -> dict[str, object]:
    try:
        return await _service(request).pause()
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/playback/resume")
async def resume_playback(request: Request) -> dict[str, object]:
    try:
        return await _service(request).resume()
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/playback/seek")
async def seek_playback(payload: SeekRequest, request: Request) -> dict[str, object]:
    try:
        return await _service(request).seek(payload.position_seconds)
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/playback/stop")
async def stop_playback(request: Request) -> dict[str, object]:
    try:
        return await _service(request).stop()
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/playback/next")
async def next_playback(request: Request) -> dict[str, object]:
    try:
        return await _service(request).play_next()
    except (LookupError, PlaybackBusyError, MpvUnavailableError) as exc:
        raise _translate_error(exc) from exc


@router.get("/playback/continue")
async def continue_watching(request: Request) -> list[dict[str, object]]:
    return _service(request).state_service.continue_watching()


@router.get("/subjects/{subject_id}/next-unwatched")
async def first_unwatched(subject_id: int, request: Request) -> dict[str, object] | None:
    try:
        return _service(request).state_service.first_unwatched(subject_id)
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/episodes/{episode_id}/mark-watched")
async def mark_watched(episode_id: int, request: Request) -> dict[str, object]:
    try:
        return await _service(request).mark_watched(episode_id, True)
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/episodes/{episode_id}/mark-unwatched")
async def mark_unwatched(episode_id: int, request: Request) -> dict[str, object]:
    try:
        return await _service(request).mark_watched(episode_id, False)
    except LookupError as exc:
        raise _translate_error(exc) from exc
