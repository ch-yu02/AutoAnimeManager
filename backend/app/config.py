from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class AppConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    timezone: str = "Asia/Shanghai"


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/database/autoanime.db"

    @field_validator("url")
    @classmethod
    def require_sqlite(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError("阶段 0 仅支持 sqlite:/// 数据库 URL")
        return value


class BangumiConfig(BaseModel):
    base_url: str = "https://api.bgm.tv"
    username: str = ""
    access_token: SecretStr = SecretStr("")


class QBittorrentConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8080"
    username: str = ""
    password: SecretStr = SecretStr("")
    category: str = "autoanime"


class PlayerConfig(BaseModel):
    mpv_path: str = "mpv"


class StorageConfig(BaseModel):
    download_path: Path = Path("data/downloads")
    library_path: Path = Path("data/library")
    quarantine_path: Path = Path("data/quarantine")


class SchedulerConfig(BaseModel):
    enabled: bool = False


class AppSettings(BaseSettings):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    bangumi: BangumiConfig = BangumiConfig()
    qbittorrent: QBittorrentConfig = QBittorrentConfig()
    player: PlayerConfig = PlayerConfig()
    storage: StorageConfig = StorageConfig()
    scheduler: SchedulerConfig = SchedulerConfig()

    model_config = SettingsConfigDict(
        env_prefix="AUTOANIME_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 环境变量应覆盖 YAML，便于部署时安全注入凭证。
        return env_settings, init_settings, dotenv_settings, file_secret_settings


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError(f"配置路径不是文件：{path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"配置文件 YAML 格式无效：{path}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"配置文件顶层必须是对象：{path}")
    return loaded


@lru_cache
def get_settings() -> AppSettings:
    config_path = Path(os.getenv("AUTOANIME_CONFIG", "config.yaml"))
    return AppSettings(**_load_yaml(config_path))


def public_settings(settings: AppSettings) -> dict[str, Any]:
    """Return configuration safe for API responses and logs."""
    data = settings.model_dump(mode="json")
    data["bangumi"]["access_token"] = "***" if settings.bangumi.access_token.get_secret_value() else ""
    data["qbittorrent"]["password"] = "***" if settings.qbittorrent.password.get_secret_value() else ""
    return data


def ensure_runtime_directories(settings: AppSettings) -> None:
    paths = [
        Path("data/database"),
        Path("data/cache"),
        Path("data/logs"),
        Path("data/backups"),
        settings.storage.download_path,
        settings.storage.library_path,
        settings.storage.quarantine_path,
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        try:
            probe.touch(exist_ok=True)
            probe.unlink()
        except OSError as exc:
            raise ValueError(f"目录不可写：{path}") from exc
