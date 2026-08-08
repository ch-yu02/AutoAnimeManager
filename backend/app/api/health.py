from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.app import __version__
from backend.app.config import get_settings
from backend.app.database import check_database

router = APIRouter(tags=["system"])


class ComponentStatus(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: ComponentStatus
    configuration: ComponentStatus


def _configuration_status() -> ComponentStatus:
    settings = get_settings()
    missing: list[str] = []
    if not settings.bangumi.username:
        missing.append("bangumi.username")
    if not settings.bangumi.access_token.get_secret_value():
        missing.append("bangumi.access_token")
    if not settings.qbittorrent.username:
        missing.append("qbittorrent.username")
    if not settings.qbittorrent.password.get_secret_value():
        missing.append("qbittorrent.password")
    if missing:
        return ComponentStatus(
            status="incomplete",
            detail="未配置：" + ", ".join(missing),
        )
    return ComponentStatus(status="ok")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    database_ok, database_error = check_database()
    configuration = _configuration_status()
    overall = "ok" if database_ok else "degraded"
    return HealthResponse(
        status=overall,
        version=__version__,
        database=ComponentStatus(
            status="ok" if database_ok else "error",
            detail=database_error,
        ),
        configuration=configuration,
    )


@router.get("/status")
async def status(request: Request) -> dict[str, object]:
    health_result = await health()
    scheduler = request.app.state.scheduler.status()
    return {
        **health_result.model_dump(),
        "scheduler": scheduler,
        "integrations": {
            "bangumi": "not_tested",
            "qbittorrent": "not_tested",
            "mpv": "not_tested",
        },
    }
