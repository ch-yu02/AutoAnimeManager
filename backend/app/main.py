from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app import __version__
from backend.app.api.health import router as health_router
from backend.app.api.bangumi import router as bangumi_router
from backend.app.api.settings import router as settings_router
from backend.app.api.subjects import router as subjects_router
from backend.app.config import ensure_runtime_directories, get_settings
from backend.app.logging import configure_logging
from backend.app.modules.bangumi.sync_service import BangumiSyncService
from backend.app.modules.scheduler import SchedulerSkeleton


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
    yield
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

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "AutoAnime", "docs": "/docs"}

    return app


app = create_app()
