from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app.modules.playback.session_service import PlaybackSessionService

router = APIRouter(tags=["playback"])


class PlaybackStartRequest(BaseModel):
    episode_id: int
    from_start: bool = False


class SessionProgressRequest(BaseModel):
    position_seconds: float = Field(ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    ended: bool = False


def _session_service(request: Request) -> PlaybackSessionService:
    return request.app.state.playback_session_service


@router.post("/playback/sessions", status_code=status.HTTP_201_CREATED)
async def create_playback_session(payload: PlaybackStartRequest, request: Request) -> dict[str, object]:
    try:
        return await _session_service(request).create(payload.episode_id, from_start=payload.from_start)
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/playback/sessions/{session_id}/progress")
async def update_playback_session(
    session_id: str, payload: SessionProgressRequest, request: Request
) -> dict[str, object]:
    try:
        return await _session_service(request).progress(
            session_id,
            payload.position_seconds,
            payload.duration_seconds,
            ended=payload.ended,
        )
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.delete("/playback/sessions/{session_id}")
async def close_playback_session(session_id: str, request: Request) -> dict[str, str]:
    try:
        return await _session_service(request).close(session_id)
    except LookupError as exc:
        raise _translate_error(exc) from exc


def _translate_error(exc: Exception) -> HTTPException:
    code = str(exc)
    if code in {"episode_not_found", "subject_not_found"}:
        return HTTPException(404, detail={"code": code, "message": "条目或章节不存在"})
    if code == "playback_session_not_found":
        return HTTPException(404, detail={"code": code, "message": "播放会话不存在"})
    messages = {
        "media_not_ready": "章节没有可播放的本地文件",
    }
    return HTTPException(409, detail={"code": code, "message": messages.get(code, "播放操作失败")})


@router.get("/playback/continue")
async def continue_watching(request: Request) -> list[dict[str, object]]:
    return _session_service(request).continue_watching()


@router.get("/subjects/{subject_id}/next-unwatched")
async def first_unwatched(subject_id: int, request: Request) -> dict[str, object] | None:
    try:
        return _session_service(request).first_unwatched(subject_id)
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/episodes/{episode_id}/mark-watched")
async def mark_watched(episode_id: int, request: Request) -> dict[str, object]:
    try:
        return await _session_service(request).mark_watched(episode_id, True)
    except LookupError as exc:
        raise _translate_error(exc) from exc


@router.post("/episodes/{episode_id}/mark-unwatched")
async def mark_unwatched(episode_id: int, request: Request) -> dict[str, object]:
    try:
        return await _session_service(request).mark_watched(episode_id, False)
    except LookupError as exc:
        raise _translate_error(exc) from exc
