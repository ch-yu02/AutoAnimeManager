from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.modules.cleanup import CleanupNotAllowed, CleanupNotFound, CleanupService


router = APIRouter(prefix="/cleanup", tags=["cleanup"])


class KeepRequest(BaseModel):
    keep_forever: bool


def _service(request: Request) -> CleanupService:
    return request.app.state.cleanup_service


def _translate(exc: CleanupNotFound | CleanupNotAllowed) -> HTTPException:
    if isinstance(exc, CleanupNotFound):
        return HTTPException(404, detail={"code": "cleanup_not_found", "message": str(exc)})
    return HTTPException(409, detail={
        "code": "cleanup_not_allowed", "message": str(exc), "reasons": exc.reasons,
    })


@router.get("/candidates")
async def candidates(request: Request) -> list[dict[str, object]]:
    return _service(request).candidates()


@router.get("/records")
async def records(request: Request) -> list[dict[str, object]]:
    return _service(request).records()


@router.get("/subjects/{subject_id}")
async def subject_eligibility(subject_id: int, request: Request) -> dict[str, object]:
    try:
        return _service(request).eligibility(subject_id)
    except CleanupNotFound as exc:
        raise _translate(exc) from exc


@router.patch("/subjects/{subject_id}/keep")
async def keep_subject(
    subject_id: int, payload: KeepRequest, request: Request
) -> dict[str, object]:
    try:
        return _service(request).set_keep_forever(subject_id, payload.keep_forever)
    except CleanupNotFound as exc:
        raise _translate(exc) from exc


@router.post("/subjects/{subject_id}/quarantine")
async def quarantine_subject(subject_id: int, request: Request) -> dict[str, object]:
    try:
        return await _service(request).quarantine(subject_id)
    except (CleanupNotFound, CleanupNotAllowed) as exc:
        raise _translate(exc) from exc


@router.post("/records/{record_id}/restore")
async def restore_record(record_id: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).restore(record_id)
    except (CleanupNotFound, CleanupNotAllowed) as exc:
        raise _translate(exc) from exc


@router.post("/records/{record_id}/permanent-delete")
async def permanently_delete_record(record_id: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).permanently_delete(record_id)
    except (CleanupNotFound, CleanupNotAllowed) as exc:
        raise _translate(exc) from exc
