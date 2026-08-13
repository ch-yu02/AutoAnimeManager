from __future__ import annotations

import httpx
import pytest

from backend.app.main import create_app


class FakeCleanup:
    def candidates(self):
        return [{"subject_id": 1, "eligible": True}]

    def records(self):
        return [{"id": "cleanup-1", "status": "QUARANTINED"}]

    def eligibility(self, subject_id: int):
        return {"subject_id": subject_id, "eligible": True}

    def set_keep_forever(self, subject_id: int, keep: bool):
        return {"subject_id": subject_id, "keep_forever": keep}

    async def quarantine(self, subject_id: int):
        return {"id": "cleanup-1", "subject_id": subject_id, "status": "QUARANTINED"}

    async def restore(self, record_id: str):
        return {"id": record_id, "status": "RESTORED"}

    async def permanently_delete(self, record_id: str):
        return {"id": record_id, "status": "DELETED"}


@pytest.mark.anyio
async def test_cleanup_preview_keep_quarantine_restore_and_delete_routes() -> None:
    app = create_app()
    app.state.cleanup_service = FakeCleanup()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        eligibility = await client.get("/api/cleanup/subjects/1")
        keep = await client.patch(
            "/api/cleanup/subjects/1/keep", json={"keep_forever": True}
        )
        quarantine = await client.post("/api/cleanup/subjects/1/quarantine")
        restore = await client.post("/api/cleanup/records/cleanup-1/restore")
        deleted = await client.post("/api/cleanup/records/cleanup-1/permanent-delete")

    assert eligibility.json()["eligible"] is True
    assert keep.json()["keep_forever"] is True
    assert quarantine.json()["status"] == "QUARANTINED"
    assert restore.json()["status"] == "RESTORED"
    assert deleted.json()["status"] == "DELETED"
