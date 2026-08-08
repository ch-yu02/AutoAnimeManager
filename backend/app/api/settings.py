from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.config import get_settings, public_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class ConnectionTestResult(BaseModel):
    service: str
    status: str
    detail: str


@router.get("")
async def read_settings() -> dict[str, object]:
    return public_settings(get_settings())


@router.post("/test/bangumi", response_model=ConnectionTestResult)
async def test_bangumi() -> ConnectionTestResult:
    settings = get_settings().bangumi
    if not settings.username or not settings.access_token.get_secret_value():
        return ConnectionTestResult(
            service="bangumi",
            status="not_configured",
            detail="请先配置 bangumi.username 和 bangumi.access_token",
        )
    return ConnectionTestResult(
        service="bangumi",
        status="not_implemented",
        detail="连接参数已就绪；真实 API 检查将在阶段 1 实现",
    )


@router.post("/test/qbittorrent", response_model=ConnectionTestResult)
async def test_qbittorrent() -> ConnectionTestResult:
    settings = get_settings().qbittorrent
    if not settings.username or not settings.password.get_secret_value():
        return ConnectionTestResult(
            service="qbittorrent",
            status="not_configured",
            detail="请先配置 qbittorrent.username 和 qbittorrent.password",
        )
    return ConnectionTestResult(
        service="qbittorrent",
        status="not_implemented",
        detail="连接参数已就绪；真实 WebUI API 检查将在下载阶段实现",
    )


@router.post("/test/mpv", response_model=ConnectionTestResult)
async def test_mpv() -> ConnectionTestResult:
    configured = get_settings().player.mpv_path
    candidate = Path(configured).expanduser()
    executable = str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else shutil.which(configured)
    if executable:
        return ConnectionTestResult(
            service="mpv",
            status="ok",
            detail=f"已找到 MPV：{executable}",
        )
    return ConnectionTestResult(
        service="mpv",
        status="unavailable",
        detail=f"找不到可执行文件：{configured}",
    )
