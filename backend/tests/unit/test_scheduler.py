from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.config import get_settings
from backend.app.database.models import TaskRun
from backend.app.database.session import create_schema, get_engine, session_scope
from backend.app.modules.scheduler import SchedulerService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def scheduler_database(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'scheduler.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()
    yield
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_task_run_is_persisted_and_same_task_does_not_reenter(scheduler_database) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler() -> dict[str, object]:
        entered.set()
        await release.wait()
        return {"processed": 1}

    scheduler = SchedulerService()
    scheduler.register("DemandRefresh", lambda: 60, handler)
    first = asyncio.create_task(scheduler.run_task("DemandRefresh"))
    await entered.wait()

    reused = await scheduler.run_task("DemandRefresh")
    assert reused["status"] == "RUNNING"
    release.set()
    completed = await first

    assert completed["status"] == "SUCCESS"
    assert completed["result"] == {"processed": 1}
    assert len(scheduler.history()) == 1


@pytest.mark.anyio
async def test_failure_records_exponential_backoff(scheduler_database) -> None:
    async def handler() -> dict[str, object]:
        raise RuntimeError("provider unavailable")

    scheduler = SchedulerService()
    scheduler.register("ReleaseSearch", lambda: 60, handler)

    first = await scheduler.run_task("ReleaseSearch")
    second = await scheduler.run_task("ReleaseSearch")

    assert first["status"] == "FAILED"
    assert first["attempt"] == 1
    assert first["next_retry_at"] is not None
    assert second["status"] == "FAILED"
    assert second["attempt"] == 2
    assert second["next_retry_at"] > first["next_retry_at"]


@pytest.mark.anyio
async def test_startup_recovers_interrupted_run(scheduler_database) -> None:
    with session_scope() as session:
        session.add(TaskRun(
            id="interrupted",
            task_name="DownloadMonitor",
            trigger="SCHEDULED",
            status="RUNNING",
            attempt=1,
            started_at=datetime.now(UTC),
        ))

    scheduler = SchedulerService()
    scheduler.start()
    await scheduler.stop()

    recovered = scheduler.history()[0]
    assert recovered["status"] == "FAILED"
    assert recovered["next_retry_at"] is not None
    assert "恢复" in recovered["error"]
