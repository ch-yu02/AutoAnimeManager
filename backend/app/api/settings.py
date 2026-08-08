from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.config import get_settings, public_settings
from backend.app.modules.bangumi.client import BangumiClient
from backend.app.modules.bangumi.errors import BangumiError

router = APIRouter(prefix="/settings", tags=["settings"])


class ConnectionTestResult(BaseModel):
    service: str
    status: str
    detail: str


class SettingsPatch(BaseModel):
    bangumi_username: str | None = Field(default=None, min_length=1)
    bangumi_access_token: str | None = Field(default=None, min_length=1)


@router.get("")
async def read_settings() -> dict[str, object]:
    return public_settings(get_settings())


@router.patch("")
async def update_settings(payload: SettingsPatch) -> dict[str, object]:
    """Persist the phase-1 editable Bangumi settings in the configured YAML file."""
    import yaml

    config_path = Path(os.getenv("AUTOANIME_CONFIG", "config.yaml"))
    raw: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    bangumi = raw.get("bangumi")
    if bangumi is None:
        bangumi = {}
        raw["bangumi"] = bangumi
    if not isinstance(bangumi, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_config", "message": "bangumi 配置必须是对象"},
        )
    if payload.bangumi_username is not None:
        bangumi["username"] = payload.bangumi_username
    if payload.bangumi_access_token is not None:
        bangumi["access_token"] = payload.bangumi_access_token
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            temporary_path = Path(temporary.name)
        temporary_path.chmod(0o600)
        os.replace(temporary_path, config_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    get_settings.cache_clear()
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
    try:
        async with BangumiClient(get_settings().bangumi) as client:
            await client.test_connection(settings.username)
    except BangumiError as exc:
        return ConnectionTestResult(service="bangumi", status=exc.code, detail=exc.message)
    except Exception:
        return ConnectionTestResult(service="bangumi", status="unavailable", detail="无法连接 Bangumi API")
    return ConnectionTestResult(service="bangumi", status="ok", detail="Bangumi API 与 Token 检查通过")


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
