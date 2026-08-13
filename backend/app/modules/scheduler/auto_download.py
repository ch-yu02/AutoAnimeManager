from __future__ import annotations

import logging

from backend.app.config import get_settings
from backend.app.modules.scheduler.demand import DemandPlanner


logger = logging.getLogger(__name__)


class AutoDownloadScheduler:
    """ReleaseSearch task handler; timing and retries belong to SchedulerService."""

    def __init__(self, release_service, planner: DemandPlanner | None = None) -> None:
        self.release_service = release_service
        self.planner = planner or DemandPlanner()

    async def run_once(self) -> dict[str, int | bool]:
        if not get_settings().scheduler.auto_download_enabled:
            return {"enabled": False, "wanted": 0, "searched": 0, "downloaded": 0, "failed": 0}

        wanted = self.planner.wanted_episode_ids()
        searched = downloaded = failed = 0
        errors: list[str] = []
        for episode_id in wanted:
            try:
                result = await self.release_service.search(episode_id)
                searched += 1
                candidate = self.release_service.auto_candidate(str(result["id"]))
                if candidate is not None:
                    await self.release_service.download_candidate(
                        str(candidate["id"]), automatic=True
                    )
                    downloaded += 1
            except Exception as exc:
                failed += 1
                errors.append(f"episode {episode_id}: {exc}")
                logger.exception("自动下载处理失败", extra={"episode_id": episode_id})
        if errors:
            raise RuntimeError("; ".join(errors)[:2000])
        return {
            "enabled": True,
            "wanted": len(wanted),
            "searched": searched,
            "downloaded": downloaded,
            "failed": failed,
        }
