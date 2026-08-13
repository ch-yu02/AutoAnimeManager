from __future__ import annotations

import httpx
import pytest

from backend.app.main import create_app


class FakeScheduler:
    def status(self) -> dict[str, object]:
        return {"enabled": True, "running": True, "tasks": [{"name": "DemandRefresh"}]}

    def history(self, limit: int) -> list[dict[str, object]]:
        return [{"id": "run-1", "limit": limit}]

    async def start_task(self, name: str, *, trigger: str) -> dict[str, object]:
        return {"task_name": name, "trigger": trigger, "status": "SUCCESS"}


@pytest.mark.anyio
async def test_scheduler_status_history_and_manual_run_routes() -> None:
    app = create_app()
    app.state.scheduler = FakeScheduler()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        status = await client.get("/api/scheduler")
        history = await client.get("/api/scheduler/runs?limit=10")
        run = await client.post("/api/scheduler/tasks/DemandRefresh/run")

    assert status.json()["tasks"][0]["name"] == "DemandRefresh"
    assert history.json() == [{"id": "run-1", "limit": 10}]
    assert run.json() == {
        "task_name": "DemandRefresh", "trigger": "MANUAL", "status": "SUCCESS",
    }
