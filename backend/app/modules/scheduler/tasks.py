from __future__ import annotations

from sqlalchemy import func, select

from backend.app.config import get_settings
from backend.app.database.models import DownloadJob
from backend.app.database.session import session_scope


class SchedulerTasks:
    def __init__(
        self, bangumi_sync, library_scan, planner, release_search, download_service,
        cleanup=None, maintenance=None,
    ) -> None:
        self.bangumi_sync = bangumi_sync
        self.library_scan = library_scan
        self.planner = planner
        self.release_search = release_search
        self.download_service = download_service
        self.cleanup = cleanup
        self.maintenance = maintenance

    async def bangumi(self) -> dict[str, object]:
        settings = get_settings().bangumi
        if not settings.username or not settings.access_token.get_secret_value():
            return {"skipped": True, "reason": "Bangumi 未配置"}
        started = await self.bangumi_sync.sync_now(mode="QUICK")
        status = self.bangumi_sync.get_status(started.task_id)
        if status["status"] not in {"SUCCESS"}:
            raise RuntimeError(str(status.get("error_summary") or "Bangumi 同步失败"))
        return status

    async def library(self) -> dict[str, object]:
        return await self.library_scan.scan_now()

    async def demand(self) -> dict[str, object]:
        wanted = self.planner.wanted_episode_ids()
        return {"wanted": len(wanted)}

    async def releases(self) -> dict[str, object]:
        return await self.release_search.run_once()

    async def downloads(self) -> dict[str, object]:
        with session_scope() as session:
            before = session.scalar(select(func.count(DownloadJob.id))) or 0
        reconciled = await self.download_service.reconcile_all()
        if reconciled["failed"]:
            raise RuntimeError(f"{reconciled['failed']} 个下载任务暂时无法连接 qBittorrent")
        with session_scope() as session:
            active = session.scalar(select(func.count(DownloadJob.id)).where(
                DownloadJob.state.in_({
                    "CREATED", "QUEUED", "DOWNLOADING", "STALLED", "COMPLETED", "IMPORTING",
                })
            )) or 0
            imported = session.scalar(select(func.count(DownloadJob.id)).where(
                DownloadJob.state == "IMPORTED"
            )) or 0
            failed = session.scalar(select(func.count(DownloadJob.id)).where(
                DownloadJob.state == "FAILED"
            )) or 0
        return {
            "jobs": before, "processed": reconciled["processed"], "active": active,
            "imported": imported, "failed": failed,
        }

    async def cleanup_files(self) -> dict[str, object]:
        if self.cleanup is None:
            return {"enabled": False, "quarantined": 0, "deleted": 0, "failed": 0}
        return await self.cleanup.run_automatic()

    async def backup_database(self) -> dict[str, object]:
        if self.maintenance is None or not get_settings().maintenance.backup_enabled:
            return {"enabled": False, "created": False}
        return self.maintenance.create_backup()
