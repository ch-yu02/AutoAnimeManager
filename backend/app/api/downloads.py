from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from backend.app.modules.download.magnet import InvalidMagnet
from backend.app.modules.download.qbittorrent import QBittorrentError
from backend.app.modules.download.service import (
    DownloadNotFound,
    DownloadDeleteNotAllowed,
    DownloadService,
    DuplicateDownload,
    EpisodeNotDownloadable,
)


router = APIRouter(prefix="/downloads", tags=["downloads"])


class DownloadCreate(BaseModel):
    episode_id: int = Field(gt=0)
    magnet: str = Field(min_length=10, max_length=12000)


def _service(request: Request) -> DownloadService:
    return request.app.state.download_service


def _not_found(exc: DownloadNotFound) -> HTTPException:
    return HTTPException(404, detail={"code": "download_not_found", "message": str(exc)})


@router.get("")
async def list_downloads(request: Request) -> list[dict[str, object]]:
    return _service(request).list()


@router.get("/{job_id}")
async def get_download(job_id: str, request: Request) -> dict[str, object]:
    try:
        return _service(request).get(job_id)
    except DownloadNotFound as exc:
        raise _not_found(exc) from exc


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_download(payload: DownloadCreate, request: Request) -> dict[str, object]:
    try:
        return await _service(request).create(payload.episode_id, payload.magnet)
    except InvalidMagnet as exc:
        raise HTTPException(400, detail={"code": "invalid_magnet", "message": str(exc)}) from exc
    except DuplicateDownload as exc:
        raise HTTPException(
            409,
            detail={"code": "duplicate_download", "message": str(exc), "job_id": exc.job_id},
        ) from exc
    except EpisodeNotDownloadable as exc:
        raise HTTPException(409, detail={"code": "episode_not_downloadable", "message": str(exc)}) from exc


@router.post("/{job_id}/pause")
async def pause_download(job_id: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).pause(job_id)
    except DownloadNotFound as exc:
        raise _not_found(exc) from exc
    except QBittorrentError as exc:
        raise HTTPException(503, detail={"code": "qbittorrent_unavailable", "message": str(exc)}) from exc


@router.post("/{job_id}/resume")
async def resume_download(job_id: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).resume(job_id)
    except DownloadNotFound as exc:
        raise _not_found(exc) from exc
    except QBittorrentError as exc:
        raise HTTPException(503, detail={"code": "qbittorrent_unavailable", "message": str(exc)}) from exc


@router.post("/{job_id}/retry")
async def retry_download(job_id: str, request: Request) -> dict[str, object]:
    try:
        return await _service(request).retry(job_id)
    except DownloadNotFound as exc:
        raise _not_found(exc) from exc


@router.delete("/{job_id}")
async def delete_download(
    job_id: str,
    request: Request,
    delete_files: bool = Query(default=False),
) -> dict[str, object]:
    try:
        return await _service(request).delete(job_id, delete_files=delete_files)
    except DownloadNotFound as exc:
        raise _not_found(exc) from exc
    except DownloadDeleteNotAllowed as exc:
        raise HTTPException(409, detail={"code": "download_delete_not_allowed", "message": str(exc)}) from exc
    except QBittorrentError as exc:
        raise HTTPException(503, detail={"code": "qbittorrent_unavailable", "message": str(exc)}) from exc
