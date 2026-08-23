from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post("/backup")
async def create_backup(request: Request) -> dict[str, object]:
    return request.app.state.maintenance_service.create_backup()


@router.post("/diagnostics")
async def create_diagnostics(request: Request) -> dict[str, object]:
    return request.app.state.maintenance_service.generate_diagnostics()
