from types import SimpleNamespace

import pytest

from backend.app.config import BangumiConfig
from backend.app.modules.scheduler.tasks import SchedulerTasks


class FakeSync:
    def __init__(self) -> None:
        self.mode: str | None = None

    async def sync_now(self, mode: str):
        self.mode = mode
        return SimpleNamespace(task_id="sync-1")

    def get_status(self, task_id: str):
        return {"task_id": task_id, "status": "SUCCESS", "mode": self.mode}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_scheduled_bangumi_task_uses_quick_mode(monkeypatch) -> None:
    sync = FakeSync()
    monkeypatch.setattr(
        "backend.app.modules.scheduler.tasks.get_settings",
        lambda: SimpleNamespace(bangumi=BangumiConfig(username="user", access_token="token")),
    )
    tasks = SchedulerTasks(sync, None, None, None, None)

    result = await tasks.bangumi()

    assert sync.mode == "QUICK"
    assert result["mode"] == "QUICK"
