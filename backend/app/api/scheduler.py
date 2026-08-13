from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.modules.scheduler import SchedulerService, UnknownScheduledTask


router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _service(request: Request) -> SchedulerService:
    return request.app.state.scheduler


@router.get("")
async def scheduler_status(request: Request) -> dict[str, object]:
    return _service(request).status()


@router.get("/runs")
async def scheduler_runs(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[dict[str, object]]:
    return _service(request).history(limit)


@router.post("/tasks/{task_name}/run")
async def run_scheduler_task(task_name: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).start_task(task_name, trigger="MANUAL")
    except UnknownScheduledTask as exc:
        raise HTTPException(
            404, detail={"code": "scheduler_task_not_found", "message": f"未知调度任务：{task_name}"}
        ) from exc
