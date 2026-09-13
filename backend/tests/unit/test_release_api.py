from __future__ import annotations

import httpx
import pytest

from backend.app.main import create_app


class FakeReleaseSearchService:
    replacement_job_id: str | None = None

    async def search(self, episode_id: int) -> dict[str, object]:
        return {"id": "search-1", "episode_id": episode_id, "provider": "fake", "candidates": []}

    def get_search(self, search_id: str) -> dict[str, object]:
        return {"id": search_id, "episode_id": 1, "provider": "fake", "candidates": []}

    def debug_auto_select(self, search_id: str) -> dict[str, object]:
        return {"id": search_id, "episode_id": 1, "provider": "fake", "candidates": []}

    async def download_candidate(
        self, candidate_id: str, *, replacement_job_id: str | None = None
    ) -> dict[str, object]:
        self.replacement_job_id = replacement_job_id
        return {"candidate_id": candidate_id, "download": {"id": "job-1", "state": "QUEUED"}}


@pytest.mark.anyio
async def test_release_search_and_candidate_routes() -> None:
    app = create_app()
    app.state.release_search_service = FakeReleaseSearchService()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        searched = await client.post("/api/releases/search", json={"episode_id": 1})
        loaded = await client.get("/api/releases/search/search-1")
        debugged = await client.post("/api/releases/search/search-1/debug-auto-select")
        downloaded = await client.post(
            "/api/releases/candidates/candidate-1/download?replacement_job_id=old-job"
        )

    assert searched.status_code == 200
    assert searched.json()["provider"] == "fake"
    assert loaded.status_code == 200
    assert debugged.status_code == 200
    assert downloaded.status_code == 202
    assert downloaded.json()["download"]["id"] == "job-1"
    assert app.state.release_search_service.replacement_job_id == "old-job"
