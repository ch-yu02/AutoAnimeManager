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
from backend.app.config import ensure_runtime_directories, get_settings
from backend.app.logging import configure_logging
from backend.app.modules.bangumi.sync_service import BangumiSyncService
from backend.app.modules.scheduler import SchedulerSkeleton
from backend.app.modules.library.scanner import LibraryScanner
from backend.app.modules.library.service import LibraryScanService
from backend.app.modules.playback.session_service import PlaybackSessionService
from backend.app.modules.playback.state_service import PlaybackStateService
from backend.app.modules.playback.writeback import writeback_episode_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_runtime_directories(settings)
    configure_logging(settings.app.log_level)
    scheduler = SchedulerSkeleton(enabled=settings.scheduler.enabled)
    scheduler.start()
    app.state.scheduler = scheduler
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
    try:
        yield
    finally:
        scheduler.stop()


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
