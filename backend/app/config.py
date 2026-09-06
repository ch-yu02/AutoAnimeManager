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
            raise ValueError("当前仅支持 sqlite:/// 数据库 URL")
        return value


class BangumiConfig(BaseModel):
    base_url: str = "https://api.bgm.tv"
    username: str = ""
    access_token: SecretStr = SecretStr("")
    timeout: float = Field(default=10.0, gt=0, le=120)
    page_size: int = Field(default=50, ge=1, le=100)
    cache_ttl_seconds: float = Field(default=30.0, ge=0, le=300)
    sync_concurrency: int = Field(default=6, ge=1, le=12)
    metadata_refresh_hours: float = Field(default=24.0, ge=1, le=720)
    relations_refresh_hours: float = Field(default=168.0, ge=1, le=2160)


class QBittorrentConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8080"
    username: str = ""
    password: SecretStr = SecretStr("")
    category: str = "autoanime"
    timeout: float = Field(default=10.0, gt=0, le=120)
    poll_interval_seconds: float = Field(default=3.0, ge=0.5, le=60)


class ReleaseSourceConfig(BaseModel):
    name: str
    rss_url: str
    rss_url_template: str
    use_proxy: bool = False
    enabled: bool = True


def _default_release_sources() -> list[ReleaseSourceConfig]:
    return [
        ReleaseSourceConfig(
            name="kisssub_rss",
            rss_url="https://www.kisssub.org/rss.xml",
            rss_url_template="https://www.kisssub.org/rss-{query}.xml",
            use_proxy=False,
        ),
        ReleaseSourceConfig(
            name="comicat_rss",
            rss_url="https://www.comicat.org/rss.xml",
            rss_url_template="https://www.comicat.org/rss-{query}.xml",
            use_proxy=True,
        ),
        ReleaseSourceConfig(
            name="acgnx_rss",
            rss_url="https://share.acgnx.se/rss.xml",
            rss_url_template="https://share.acgnx.se/rss-sort-1.xml?keyword={query}",
            use_proxy=True,
        ),
    ]


class ReleaseSearchConfig(BaseModel):
    # These legacy fields remain the canonical KissSub URLs for existing configs.
    provider: Literal["multi_rss", "kisssub_rss"] = "multi_rss"
    rss_url: str = "https://www.kisssub.org/rss.xml"
    rss_url_template: str = "https://www.kisssub.org/rss-{query}.xml"
    sources: list[ReleaseSourceConfig] = Field(default_factory=_default_release_sources)
    timeout: float = Field(default=15.0, gt=0, le=120)
    max_results: int = Field(default=100, ge=1, le=500)
    max_query_terms: int = Field(default=3, ge=1, le=10)
    preferred_groups: list[str] = Field(default_factory=list)
    preferred_language: str = ""
    preferred_resolution: str = "1080p"
    preferred_codec: str = ""
    allow_batch: bool = False
    debug_auto_selection_enabled: bool = False

    @field_validator("provider")
    @classmethod
    def normalize_legacy_provider(cls, value: str) -> str:
        return "multi_rss" if value == "kisssub_rss" else value


class PlayerConfig(BaseModel):
    progress_save_interval_seconds: float = Field(default=15.0, ge=1, le=300)
    minimum_progress_seconds: float = Field(default=60.0, ge=0, le=600)
    watched_ratio: float = Field(default=0.9, ge=0.5, le=1)
    watched_remaining_seconds: float = Field(default=300.0, ge=0, le=1800)
    auto_play_next: bool = False
    bangumi_writeback_enabled: bool = True


class StorageConfig(BaseModel):
    library_path: Path = Path("data/library")
    library_roots: list[Path] = Field(default_factory=list)
    quarantine_path: Path = Path("data/quarantine")
    video_extensions: list[str] = Field(
        default_factory=lambda: [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".ts"]
    )
    ffprobe_path: str = "ffprobe"
    ffprobe_enabled: bool = True
    partial_hash_bytes: int = Field(default=1024 * 1024, ge=64 * 1024, le=16 * 1024 * 1024)


    @field_validator("video_extensions")
    @classmethod
    def normalize_video_extensions(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            extension = value.strip().lower()
            if not extension:
                continue
            normalized.append(extension if extension.startswith(".") else f".{extension}")
        if not normalized:
            raise ValueError("storage.video_extensions 不能为空")
        return list(dict.fromkeys(normalized))

    def effective_library_roots(self) -> list[Path]:
        return self.library_roots or [self.library_path]


class CleanupConfig(BaseModel):
    enabled: bool = False
    retention_days: int = Field(default=14, ge=0, le=3650)
    quarantine_days: int = Field(default=7, ge=1, le=365)
    interval_seconds: float = Field(default=86400.0, ge=30, le=86400)


class MaintenanceConfig(BaseModel):
    backup_enabled: bool = True
    backup_interval_seconds: float = Field(default=86400.0, ge=300, le=604800)
    backup_keep_count: int = Field(default=7, ge=1, le=90)
    backup_path: Path = Path("data/backups")
    diagnostics_path: Path = Path("data/diagnostics")
    diagnostics_log_lines: int = Field(default=500, ge=50, le=5000)


class SchedulerConfig(BaseModel):
    enabled: bool = True
    auto_download_enabled: bool = False
    auto_download_interval_seconds: float = Field(default=86400.0, ge=30, le=86400)
    tick_seconds: float = Field(default=2.0, ge=0.5, le=60)
    bangumi_sync_interval_seconds: float = Field(default=1800.0, ge=30, le=86400)
    library_scan_interval_seconds: float = Field(default=900.0, ge=30, le=86400)
    demand_refresh_interval_seconds: float = Field(default=60.0, ge=5, le=3600)
    download_monitor_interval_seconds: float = Field(default=3.0, ge=0.5, le=300)
    download_monitor_idle_interval_seconds: float = Field(default=60.0, ge=5, le=3600)
    failure_backoff_seconds: float = Field(default=30.0, ge=1, le=3600)
    failure_backoff_max_seconds: float = Field(default=1800.0, ge=1, le=86400)


class AppSettings(BaseSettings):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    bangumi: BangumiConfig = BangumiConfig()
    qbittorrent: QBittorrentConfig = QBittorrentConfig()
    release_search: ReleaseSearchConfig = ReleaseSearchConfig()
    player: PlayerConfig = PlayerConfig()
    storage: StorageConfig = StorageConfig()
    cleanup: CleanupConfig = CleanupConfig()
    maintenance: MaintenanceConfig = MaintenanceConfig()
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


def ensure_database_directory(settings: AppSettings) -> None:
    database_file = Path(settings.database.url.removeprefix("sqlite:///"))
    database_file.expanduser().parent.mkdir(parents=True, exist_ok=True)


def ensure_runtime_directories(settings: AppSettings) -> None:
    database_file = Path(settings.database.url.removeprefix("sqlite:///"))
    paths = [
        database_file.expanduser().parent,
        Path("data/cache"),
        Path("data/logs"),
        settings.maintenance.backup_path,
        settings.maintenance.diagnostics_path,
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
