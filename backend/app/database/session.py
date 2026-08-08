from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from backend.app.config import get_settings
from backend.app.database.base import Base


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database.url,
        connect_args={"check_same_thread": False},
    )


def create_schema() -> None:
    # 导入模型以注册 metadata；正式环境仍以 Alembic 迁移为准。
    from backend.app.database import models  # noqa: F401

    Base.metadata.create_all(get_engine())


def check_database() -> tuple[bool, str | None]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # 健康检查必须返回状态，不应使接口崩溃。
        return False, str(exc)
