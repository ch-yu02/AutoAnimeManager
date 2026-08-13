from types import SimpleNamespace

import pytest

from backend.app.modules.scheduler.auto_download import AutoDownloadScheduler


class FakePlanner:
    def wanted_episode_ids(self):
        return [1, 2]


class FakeReleaseService:
    def __init__(self) -> None:
        self.downloaded: list[str] = []

    async def search(self, episode_id: int):
        decision = "AUTO_ACCEPT" if episode_id == 1 else "MANUAL_REVIEW"
        return {
            "id": f"search-{episode_id}",
            "candidates": [{"id": f"candidate-{episode_id}", "decision": decision, "downloadable": True}],
        }

    async def download_candidate(self, candidate_id: str, *, automatic: bool = False):
        assert automatic is True
        self.downloaded.append(candidate_id)

    def auto_candidate(self, search_id: str):
        episode_id = int(search_id.rsplit("-", 1)[1])
        if episode_id != 1:
            return None
        return {"id": "candidate-1"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_only_auto_accept_candidate_is_downloaded(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.modules.scheduler.auto_download.get_settings",
        lambda: SimpleNamespace(scheduler=SimpleNamespace(auto_download_enabled=True)),
    )
    releases = FakeReleaseService()
    scheduler = AutoDownloadScheduler(releases, FakePlanner())

    result = await scheduler.run_once()

    assert result == {"enabled": True, "wanted": 2, "searched": 2, "downloaded": 1, "failed": 0}
    assert releases.downloaded == ["candidate-1"]


@pytest.mark.anyio
async def test_disabled_switch_does_not_plan_or_search(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.modules.scheduler.auto_download.get_settings",
        lambda: SimpleNamespace(scheduler=SimpleNamespace(auto_download_enabled=False)),
    )
    releases = FakeReleaseService()
    scheduler = AutoDownloadScheduler(releases, FakePlanner())

    assert await scheduler.run_once() == {
        "enabled": False, "wanted": 0, "searched": 0, "downloaded": 0, "failed": 0,
    }
    assert releases.downloaded == []
