from __future__ import annotations

from contextlib import asynccontextmanager
import mimetypes
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from backend.app import __version__
from backend.app.api.health import router as health_router
from backend.app.api.bangumi import router as bangumi_router
from backend.app.api.settings import router as settings_router
from backend.app.api.subjects import router as subjects_router
from backend.app.api.library import router as library_router
from backend.app.api.playback import router as playback_router
from backend.app.api.downloads import router as downloads_router
from backend.app.api.releases import router as releases_router
from backend.app.api.scheduler import router as scheduler_router
from backend.app.api.cleanup import router as cleanup_router
from backend.app.config import ensure_runtime_directories, get_settings
from backend.app.database.session import check_database
from backend.app.logging import configure_logging
from backend.app.modules.bangumi.sync_service import BangumiSyncService
from backend.app.modules.scheduler import (
    AutoDownloadScheduler,
    DemandPlanner,
    SchedulerService,
    SchedulerTasks,
)
from backend.app.modules.library.scanner import LibraryScanner
from backend.app.modules.library.service import LibraryScanService
from backend.app.modules.playback.session_service import PlaybackSessionService
from backend.app.modules.playback.state_service import PlaybackStateService
from backend.app.modules.playback.writeback import writeback_episode_state
from backend.app.modules.download import DownloadService
from backend.app.modules.release import ReleaseSearchService
from backend.app.modules.release.providers import KissSubRSSProvider
from backend.app.modules.cleanup import CleanupService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_runtime_directories(settings)
    configure_logging(settings.app.log_level)
    app.state.bangumi_sync_service = BangumiSyncService(
        settings_provider=lambda: get_settings().bangumi
    )
    app.state.library_scan_service = LibraryScanService(
        LibraryScanner(settings_provider=get_settings)
    )
    playback_state_service = PlaybackStateService(settings_provider=lambda: get_settings().player)
    app.state.playback_session_service = PlaybackSessionService(
        playback_state_service,
        settings_provider=lambda: get_settings().player,
        writeback=writeback_episode_state,
    )
    app.state.cleanup_service = CleanupService(
        app.state.playback_session_service.active_media_file_ids
    )
    download_service = DownloadService()
    app.state.download_service = download_service
    app.state.release_search_service = ReleaseSearchService(
        KissSubRSSProvider(lambda: get_settings().release_search),
        download_service,
        settings_provider=get_settings,
    )
    planner = DemandPlanner()
    app.state.auto_download_scheduler = AutoDownloadScheduler(app.state.release_search_service, planner)
    tasks = SchedulerTasks(
        app.state.bangumi_sync_service,
        app.state.library_scan_service,
        planner,
        app.state.auto_download_scheduler,
        download_service,
        app.state.cleanup_service,
    )
    scheduler = SchedulerService()
    scheduler.register(
        "BangumiSync", lambda: get_settings().scheduler.bangumi_sync_interval_seconds, tasks.bangumi
    )
    scheduler.register(
        "LibraryScan", lambda: get_settings().scheduler.library_scan_interval_seconds, tasks.library
    )
    scheduler.register(
        "DemandRefresh", lambda: get_settings().scheduler.demand_refresh_interval_seconds, tasks.demand
    )
    scheduler.register(
        "ReleaseSearch", lambda: get_settings().scheduler.auto_download_interval_seconds, tasks.releases
    )
    scheduler.register(
        "DownloadMonitor", lambda: get_settings().scheduler.download_monitor_interval_seconds, tasks.downloads
    )
    scheduler.register(
        "Cleanup", lambda: get_settings().cleanup.interval_seconds, tasks.cleanup_files
    )
    app.state.scheduler = scheduler
    if check_database()[0]:
        scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        await download_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AutoAnime API",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(bangumi_router, prefix="/api")
    app.include_router(subjects_router, prefix="/api")
    app.include_router(library_router, prefix="/api")
    app.include_router(playback_router, prefix="/api")
    app.include_router(downloads_router, prefix="/api")
    app.include_router(releases_router, prefix="/api")
    app.include_router(scheduler_router, prefix="/api")
    app.include_router(cleanup_router, prefix="/api")

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    def frontend_response(file_path: str) -> Response:
        root = frontend_dist.resolve()
        candidate = (root / unquote(file_path)).resolve()
        if not candidate.is_relative_to(root) or candidate.is_dir() or not candidate.is_file():
            if file_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = root / "index.html"
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Frontend build not found")
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return Response(candidate.read_bytes(), media_type=media_type)

    @app.get("/", include_in_schema=False, response_model=None)
    async def root() -> Response | dict[str, str]:
        if frontend_dist.is_dir():
            return frontend_response("")
        return {"service": "AutoAnime", "docs": "/docs"}

    @app.get("/{file_path:path}", include_in_schema=False)
    async def frontend(file_path: str) -> Response:
        if not frontend_dist.is_dir():
            raise HTTPException(status_code=404, detail="Frontend build not found")
        return frontend_response(file_path)

    return app


app = create_app()
