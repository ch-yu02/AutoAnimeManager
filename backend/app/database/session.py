from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.database.base import Base


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.database.url,
        connect_args={"check_same_thread": False, "timeout": 30},
        # 下载导入在线程池运行；SQLite 连接不跨线程复用可避免阻塞并简化恢复。
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    return engine


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema() -> None:
    # 导入模型以注册 metadata；正式环境仍以 Alembic 迁移为准。
    from backend.app.database import models  # noqa: F401

    Base.metadata.create_all(get_engine())


def check_database() -> tuple[bool, str | None]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            try:
                current_revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
            except Exception:
                return False, "数据库尚未迁移，请执行 alembic upgrade head"

        root = Path(__file__).resolve().parents[3]
        alembic_config = Config(str(root / "alembic.ini"))
        expected_revision = ScriptDirectory.from_config(alembic_config).get_current_head()
        if current_revision != expected_revision:
            return False, f"数据库版本为 {current_revision or '未初始化'}，需要迁移到 {expected_revision}"
        return True, None
    except Exception as exc:  # 健康检查必须返回状态，不应使接口崩溃。
        return False, str(exc)
