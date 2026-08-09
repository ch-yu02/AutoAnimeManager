from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.database.models import LibraryScanRun
from backend.app.database.session import session_scope
from backend.app.modules.library.scanner import LibraryScanner


@dataclass(frozen=True)
class ScanStart:
    task_id: str
    status: str
    reused: bool = False


class LibraryBusyError(RuntimeError):
    pass


class LibraryScanService:
    def __init__(self, scanner: LibraryScanner) -> None:
        self.scanner = scanner
        self._active_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._rematching = False

    async def start(self) -> ScanStart:
        if self._rematching:
            raise LibraryBusyError("待审核媒体正在重新匹配")
        if self._active_id:
            return ScanStart(self._active_id, "RUNNING", True)
        task_id = str(uuid.uuid4())
        with session_scope() as session:
            session.add(LibraryScanRun(id=task_id, status="RUNNING", started_at=datetime.now(UTC)))
        self._active_id = task_id
        self._active_task = asyncio.create_task(self._run(task_id))
        return ScanStart(task_id, "RUNNING")

    async def rematch_review(self) -> dict[str, int]:
        if self._active_id or self._rematching:
            raise LibraryBusyError("媒体库任务正在运行")
        self._rematching = True
        try:
            return self.scanner.rematch_review()
        finally:
            self._rematching = False

    async def _run(self, task_id: str) -> None:
        try:
            await asyncio.to_thread(self.scanner.scan, task_id)
        finally:
            if self._active_id == task_id:
                self._active_id = None
            self._active_task = None

    def status(self, task_id: str | None = None) -> dict[str, object]:
        with session_scope() as session:
            run = session.get(LibraryScanRun, task_id) if task_id else session.scalar(
                select(LibraryScanRun).order_by(LibraryScanRun.started_at.desc())
            )
            if run is None:
                return {"task_id": None, "status": "IDLE"}
            return {
                "task_id": run.id, "status": run.status, "started_at": run.started_at,
                "finished_at": run.finished_at, "discovered_count": run.discovered_count,
                "added_count": run.added_count, "changed_count": run.changed_count,
                "moved_count": run.moved_count, "missing_count": run.missing_count,
                "matched_count": run.matched_count, "review_count": run.review_count,
                "error_summary": run.error_summary,
            }
