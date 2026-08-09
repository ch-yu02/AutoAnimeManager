from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app.modules.download.magnet import InvalidMagnet
from backend.app.modules.download.qbittorrent import QBittorrentError
from backend.app.modules.download.service import DuplicateDownload, EpisodeNotDownloadable
from backend.app.modules.release.provider import ReleaseProviderError
from backend.app.modules.release.service import (
    ReleaseCandidateNotFound,
    ReleaseNotDownloadable,
    ReleaseSearchNotFound,
    ReleaseSearchService,
)


router = APIRouter(prefix="/releases", tags=["releases"])


class ReleaseSearchRequest(BaseModel):
    episode_id: int = Field(gt=0)


def _service(request: Request) -> ReleaseSearchService:
    return request.app.state.release_search_service


@router.post("/search")
async def search_releases(payload: ReleaseSearchRequest, request: Request) -> dict[str, object]:
    try:
        return await _service(request).search(payload.episode_id)
    except LookupError as exc:
        raise HTTPException(404, detail={"code": "episode_not_found", "message": str(exc)}) from exc
    except ReleaseProviderError as exc:
        raise HTTPException(503, detail={"code": "release_provider_unavailable", "message": str(exc)}) from exc


@router.get("/search/{search_id}")
async def get_release_search(search_id: str, request: Request) -> dict[str, object]:
    try:
        return _service(request).get_search(search_id)
    except ReleaseSearchNotFound as exc:
        raise HTTPException(404, detail={"code": "release_search_not_found", "message": str(exc)}) from exc


@router.post("/candidates/{candidate_id}/download", status_code=status.HTTP_202_ACCEPTED)
async def download_release_candidate(candidate_id: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).download_candidate(candidate_id)
    except ReleaseCandidateNotFound as exc:
        raise HTTPException(404, detail={"code": "release_candidate_not_found", "message": str(exc)}) from exc
    except ReleaseNotDownloadable as exc:
        raise HTTPException(409, detail={"code": "release_not_downloadable", "message": str(exc)}) from exc
    except DuplicateDownload as exc:
        raise HTTPException(409, detail={"code": "duplicate_download", "message": str(exc), "job_id": exc.job_id}) from exc
    except EpisodeNotDownloadable as exc:
        raise HTTPException(409, detail={"code": "episode_not_downloadable", "message": str(exc)}) from exc
    except InvalidMagnet as exc:
        raise HTTPException(400, detail={"code": "invalid_magnet", "message": str(exc)}) from exc
    except QBittorrentError as exc:
        raise HTTPException(503, detail={"code": "qbittorrent_unavailable", "message": str(exc)}) from exc
