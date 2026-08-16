from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database.models import TaskRun
from backend.app.database.session import session_scope


logger = logging.getLogger(__name__)
TaskHandler = Callable[[], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    name: str
    interval: Callable[[], float]
    handler: TaskHandler


class UnknownScheduledTask(LookupError):
    pass


class SchedulerService:
    """Persistent single-process scheduler with per-task locking and backoff."""

    def __init__(self) -> None:
        self._definitions: dict[str, ScheduledTask] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._running_tasks: set[asyncio.Task[dict[str, object]]] = set()
        self._stopping = False

    def register(self, name: str, interval: Callable[[], float], handler: TaskHandler) -> None:
        if name in self._definitions:
            raise ValueError(f"调度任务已注册：{name}")
        self._definitions[name] = ScheduledTask(name, interval, handler)
        self._locks[name] = asyncio.Lock()

    def start(self) -> None:
        self._recover_interrupted()
        if not get_settings().scheduler.enabled:
            return
        if self._loop_task is None or self._loop_task.done():
            self._stopping = False
            self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None
        running = list(self._running_tasks)
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def run_task(self, name: str, *, trigger: str = "MANUAL") -> dict[str, object]:
        definition = self._definitions.get(name)
        if definition is None:
            raise UnknownScheduledTask(name)
        lock = self._locks[name]
        if lock.locked():
            active = self._latest(name, status="RUNNING")
            return self._view(active) if active is not None else {
                "task_name": name, "status": "RUNNING", "reused": True,
            }

        async with lock:
            now = datetime.now(UTC)
            previous = self._latest(name)
            attempt = previous.attempt + 1 if previous is not None and previous.status == "FAILED" else 1
            run_id = str(uuid.uuid4())
            with session_scope() as session:
                session.add(TaskRun(
                    id=run_id,
                    task_name=name,
                    trigger=trigger,
                    status="RUNNING",
                    attempt=attempt,
                    started_at=now,
                ))
            try:
                result = await definition.handler()
            except asyncio.CancelledError:
                self._finish_failure(run_id, attempt, "任务因应用停止而中断", retry_immediately=True)
                raise
            except Exception as exc:
                logger.exception("调度任务执行失败", extra={"task_name": name})
                self._finish_failure(run_id, attempt, str(exc))
            else:
                with session_scope() as session:
                    run = session.get(TaskRun, run_id)
                    if run is not None:
                        run.status = "SUCCESS"
                        run.finished_at = datetime.now(UTC)
                        run.next_retry_at = None
                        run.result_json = json.dumps(result, ensure_ascii=False, default=str)
                        run.error = None
            stored = self._get(run_id)
            assert stored is not None
            return self._view(stored)

    async def start_task(self, name: str, *, trigger: str = "MANUAL") -> dict[str, object]:
        if name not in self._definitions:
            raise UnknownScheduledTask(name)
        task = asyncio.create_task(self.run_task(name, trigger=trigger))
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        await asyncio.sleep(0)
        if task.done():
            return task.result()
        active = self._latest(name, status="RUNNING")
        return self._view(active) if active is not None else {
            "task_name": name, "status": "RUNNING", "trigger": trigger,
        }

    def status(self) -> dict[str, object]:
        return {
            "enabled": get_settings().scheduler.enabled,
            "running": self._loop_task is not None and not self._loop_task.done(),
            "tasks": [self._task_status(name) for name in self._definitions],
        }

    def history(self, limit: int = 50) -> list[dict[str, object]]:
        with session_scope() as session:
            runs = list(session.scalars(
                select(TaskRun).order_by(TaskRun.started_at.desc()).limit(limit)
            ))
            return [self._view(run) for run in runs]

    async def _run_loop(self) -> None:
        while not self._stopping:
            latest_runs = self._latest_many(self._definitions)
            for definition in self._definitions.values():
                if self._is_due(definition, latest_runs.get(definition.name)):
                    await self.start_task(definition.name, trigger="SCHEDULED")
            await asyncio.sleep(get_settings().scheduler.tick_seconds)

    def _is_due(self, definition: ScheduledTask, latest: TaskRun | None) -> bool:
        if self._locks[definition.name].locked():
            return False
        if latest is None:
            return True
        now = datetime.now(UTC)
        if latest.status == "RUNNING":
            return False
        if latest.status == "FAILED" and latest.next_retry_at is not None:
            retry_at = self._aware(latest.next_retry_at)
            return retry_at <= now
        baseline = self._aware(latest.finished_at or latest.started_at)
        return baseline + timedelta(seconds=definition.interval()) <= now

    def _task_status(self, name: str) -> dict[str, object]:
        latest = self._latest(name)
        return {
            "name": name,
            "interval_seconds": self._definitions[name].interval(),
            "active": self._locks[name].locked(),
            "latest": self._view(latest) if latest is not None else None,
        }

    def _finish_failure(
        self, run_id: str, attempt: int, error: str, *, retry_immediately: bool = False
    ) -> None:
        settings = get_settings().scheduler
        delay = 0.0 if retry_immediately else min(
            settings.failure_backoff_seconds * (2 ** min(20, max(0, attempt - 1))),
            settings.failure_backoff_max_seconds,
        )
        now = datetime.now(UTC)
        with session_scope() as session:
            run = session.get(TaskRun, run_id)
            if run is not None:
                run.status = "FAILED"
                run.finished_at = now
                run.next_retry_at = now + timedelta(seconds=delay)
                run.error = (error or "任务执行失败")[:2000]

    def _recover_interrupted(self) -> None:
        now = datetime.now(UTC)
        with session_scope() as session:
            for run in session.scalars(select(TaskRun).where(TaskRun.status == "RUNNING")):
                run.status = "FAILED"
                run.finished_at = now
                run.next_retry_at = now
                run.error = "应用退出时任务尚未完成；已安排启动后恢复"

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _view(run: TaskRun) -> dict[str, object]:
        try:
            result = json.loads(run.result_json)
        except (json.JSONDecodeError, TypeError):
            result = {}
        return {
            "id": run.id,
            "task_name": run.task_name,
            "trigger": run.trigger,
            "status": run.status,
            "attempt": run.attempt,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "next_retry_at": run.next_retry_at,
            "result": result,
            "error": run.error,
        }

    @staticmethod
    def _get(run_id: str) -> TaskRun | None:
        with session_scope() as session:
            return session.get(TaskRun, run_id)

    @staticmethod
    def _latest(name: str, status: str | None = None) -> TaskRun | None:
        with session_scope() as session:
            query = select(TaskRun).where(TaskRun.task_name == name)
            if status is not None:
                query = query.where(TaskRun.status == status)
            return session.scalar(query.order_by(TaskRun.started_at.desc(), TaskRun.id.desc()).limit(1))

    @staticmethod
    def _latest_many(names) -> dict[str, TaskRun]:
        with session_scope() as session:
            return {
                name: latest
                for name in names
                if (latest := session.scalar(
                    select(TaskRun)
                    .where(TaskRun.task_name == name)
                    .order_by(TaskRun.started_at.desc(), TaskRun.id.desc())
                    .limit(1)
                )) is not None
            }
