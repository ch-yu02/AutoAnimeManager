from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from backend.app.config import get_settings
from backend.app.modules.bangumi.sync_service import BangumiSyncService

router = APIRouter(prefix="/bangumi", tags=["bangumi"])


def _service(request: Request) -> BangumiSyncService:
    return request.app.state.bangumi_sync_service


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def start_sync(request: Request) -> dict[str, object]:
    settings = get_settings().bangumi
    if not settings.username or not settings.access_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "not_configured", "message": "请先配置 bangumi.username 和 bangumi.access_token"},
        )
    result = await _service(request).start()
    return {"task_id": result.task_id, "status": result.status, "reused": result.reused}


@router.get("/sync/status")
async def sync_status(request: Request, task_id: str | None = None) -> dict[str, object]:
    return _service(request).get_status(task_id)
