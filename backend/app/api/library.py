from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from backend.app.config import get_settings
from backend.app.database.models import Episode, EpisodeFile, IgnoredMediaPath, MediaFile, Subject
from backend.app.database.session import session_scope
from backend.app.modules.library.manifest import write_manifest
from backend.app.modules.library.matcher import refresh_episode_statuses
from backend.app.modules.library.service import LibraryBusyError, LibraryScanService
from backend.app.modules.library.scanner import calculate_full_hash, delete_media_record, refresh_primary_conflicts

router = APIRouter(prefix="/library", tags=["library"])


class ManualMatchRequest(BaseModel):
    subject_id: int
    episode_ids: list[int] = Field(default_factory=list)
    primary: bool = True
    lock: bool = True
    write_manifest: bool = True


class IgnoreRequest(BaseModel):
    ignored: bool = True


def _service(request: Request) -> LibraryScanService:
    return request.app.state.library_scan_service


def _json_list(value: str) -> list[object]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _file_views(session, media_items: list[MediaFile]) -> dict[int, dict[str, object]]:
    """Build library payloads with a fixed number of queries for an entire page."""
    if not media_items:
        return {}

    media_ids = [media.id for media in media_items]
    subject_ids = {media.subject_id for media in media_items if media.subject_id is not None}
    subjects = {
        subject.id: subject
        for subject in session.scalars(select(Subject).where(Subject.id.in_(subject_ids)))
    } if subject_ids else {}

    mappings: dict[int, list[tuple[EpisodeFile, Episode]]] = defaultdict(list)
    for mapping, episode in session.execute(
        select(EpisodeFile, Episode)
        .join(Episode, Episode.id == EpisodeFile.episode_id)
        .where(EpisodeFile.media_file_id.in_(media_ids))
        .order_by(EpisodeFile.media_file_id, EpisodeFile.id)
    ):
        mappings[mapping.media_file_id].append((mapping, episode))

    hardlinks: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    for device_id, inode, media_id, path in session.execute(
        select(MediaFile.device_id, MediaFile.inode, MediaFile.id, MediaFile.path).where(
            MediaFile.device_id.is_not(None),
            MediaFile.inode.is_not(None),
            MediaFile.exists.is_(True),
        )
    ):
        hardlinks[(device_id, inode)].append((media_id, path))

    result: dict[int, dict[str, object]] = {}
    for media in media_items:
        subject = subjects.get(media.subject_id)
        try:
            parsed = json.loads(media.parse_result)
        except json.JSONDecodeError:
            parsed = {}
        key = (media.device_id, media.inode)
        linked_paths = (
            [path for media_id, path in hardlinks.get(key, []) if media_id != media.id]
            if media.device_id is not None and media.inode is not None else []
        )
        result[media.id] = {
            "id": media.id, "path": media.path, "filename": media.filename,
            "file_size": media.file_size, "mtime_ns": media.mtime_ns,
            "partial_hash": media.partial_hash, "full_hash": media.full_hash,
            "hardlink_paths": linked_paths,
            "duration_seconds": media.duration_seconds, "video_codec": media.video_codec,
            "resolution": media.resolution, "exists": media.exists, "ignored": media.ignored,
            "review_reason": media.review_reason, "parse_result": parsed,
            "subject": ({
                "id": subject.id,
                "name": subject.name_cn or subject.name,
                "image_url": subject.image_url,
            } if subject else None),
            "created_at": media.created_at,
            "subject_mapping_source": media.subject_mapping_source,
            "subject_confidence": media.subject_confidence,
            "subject_reasons": _json_list(media.subject_reasons),
            "locked": media.subject_manually_locked,
            "episodes": [
                {
                    "id": episode.id, "display_number": episode.display_number,
                    "type": episode.episode_type, "name": episode.name_cn or episode.name,
                    "source": mapping.mapping_source, "confidence": mapping.confidence,
                    "primary": mapping.is_primary, "locked": mapping.manually_locked,
                    "reasons": _json_list(mapping.reasons),
                }
                for mapping, episode in mappings.get(media.id, [])
            ],
        }
    return result


def _file_view(session, media: MediaFile) -> dict[str, object]:
    return _file_views(session, [media])[media.id]


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
async def start_scan(request: Request) -> dict[str, object]:
    try:
        result = await _service(request).start()
    except LibraryBusyError as exc:
        raise HTTPException(409, detail={"code": "library_busy", "message": str(exc)}) from exc
    return {"task_id": result.task_id, "status": result.status, "reused": result.reused}


@router.get("/scan/status")
async def scan_status(request: Request, task_id: str | None = None) -> dict[str, object]:
    return _service(request).status(task_id)


@router.get("/files")
async def list_files(
    review: bool | None = Query(default=None), ignored: bool | None = Query(default=None),
    exists: bool | None = Query(default=None),
) -> list[dict[str, object]]:
    with session_scope() as session:
        query = select(MediaFile).order_by(MediaFile.path)
        if review is True:
            query = query.where(MediaFile.review_reason.is_not(None), MediaFile.ignored.is_(False))
        if ignored is not None:
            query = query.where(MediaFile.ignored.is_(ignored))
        if exists is not None:
            query = query.where(MediaFile.exists.is_(exists))
        media_items = list(session.scalars(query))
        views = _file_views(session, media_items)
        return [views[media.id] for media in media_items]


@router.get("/recent")
async def recent_files(limit: int = Query(default=12, ge=1, le=50)) -> list[dict[str, object]]:
    with session_scope() as session:
        query = (
            select(MediaFile)
            .where(MediaFile.exists.is_(True), MediaFile.ignored.is_(False))
            .order_by(MediaFile.created_at.desc(), MediaFile.id.desc())
            .limit(limit)
        )
        media_items = list(session.scalars(query))
        views = _file_views(session, media_items)
        return [views[media.id] for media in media_items]


@router.get("/review")
async def review_queue() -> dict[str, list[dict[str, object]]]:
    with session_scope() as session:
        media = list(session.scalars(select(MediaFile).order_by(MediaFile.path)))
        views = _file_views(session, media)
        return {
            "needs_review": [views[item.id] for item in media if item.review_reason and not item.ignored],
            "automatic": [views[item.id] for item in media if item.subject_mapping_source not in (None, "MANUAL")],
            "manually_linked": [views[item.id] for item in media if item.subject_mapping_source == "MANUAL"],
            "duplicates": [views[item.id] for item in media if item.review_reason in ("PRIMARY_FILE_CONFLICT", "HARDLINK_DUPLICATE")],
            "locked": [views[item.id] for item in media if item.subject_manually_locked],
            "ignored": [views[item.id] for item in media if item.ignored],
            "missing": [views[item.id] for item in media if not item.exists],
        }


@router.get("/review/count")
async def review_count() -> dict[str, int]:
    with session_scope() as session:
        count = session.scalar(select(func.count(MediaFile.id)).where(
            MediaFile.review_reason.is_not(None),
            MediaFile.ignored.is_(False),
        )) or 0
        return {"needs_review_count": int(count)}


@router.post("/review/rematch")
async def rematch_review(request: Request) -> dict[str, int]:
    try:
        return await _service(request).rematch_review()
    except LibraryBusyError as exc:
        raise HTTPException(409, detail={"code": "library_busy", "message": str(exc)}) from exc


@router.post("/files/{file_id}/match")
async def manual_match(file_id: int, payload: ManualMatchRequest) -> dict[str, object]:
    with session_scope() as session:
        media = session.get(MediaFile, file_id)
        subject = session.get(Subject, payload.subject_id)
        if media is None:
            raise HTTPException(404, detail={"code": "file_not_found", "message": "媒体文件不存在"})
        if subject is None:
            raise HTTPException(404, detail={"code": "subject_not_found", "message": "条目不存在"})
        episodes = list(session.scalars(select(Episode).where(Episode.id.in_(payload.episode_ids)))) if payload.episode_ids else []
        if len(episodes) != len(set(payload.episode_ids)) or any(episode.subject_id != subject.id for episode in episodes):
            raise HTTPException(400, detail={"code": "invalid_episodes", "message": "章节必须存在且属于所选条目"})
        session.execute(delete(EpisodeFile).where(EpisodeFile.media_file_id == media.id))
        if payload.primary:
            for episode in episodes:
                session.execute(update(EpisodeFile).where(EpisodeFile.episode_id == episode.id).values(is_primary=False))
        media.subject_id = subject.id
        media.subject_mapping_source = "MANUAL"
        media.subject_confidence = 1.0
        media.subject_reasons = json.dumps(["用户人工关联"], ensure_ascii=False)
        media.subject_manually_locked = payload.lock
        media.review_reason = None if episodes else "EPISODE_NOT_LINKED"
        media.ignored = False
        for episode in episodes:
            session.add(EpisodeFile(
                episode_id=episode.id, media_file_id=media.id, mapping_source="MANUAL",
                confidence=1.0, reasons=json.dumps(["用户人工关联"], ensure_ascii=False),
                is_primary=payload.primary, manually_locked=payload.lock,
            ))
        refresh_primary_conflicts(session)
        refresh_episode_statuses(session)
        if payload.write_manifest and episodes and media.exists:
            try:
                write_manifest(Path(media.path), subject.bangumi_subject_id, [ep.bangumi_episode_id for ep in episodes], payload.primary)
            except OSError as exc:
                raise HTTPException(400, detail={"code": "manifest_write_failed", "message": f"关联已校验，但 manifest 无法写入：{exc}"}) from exc
        session.flush()
        return _file_view(session, media)


@router.delete("/files/{file_id}/match")
async def unlink(file_id: int) -> dict[str, object]:
    with session_scope() as session:
        media = session.get(MediaFile, file_id)
        if media is None:
            raise HTTPException(404, detail={"code": "file_not_found", "message": "媒体文件不存在"})
        session.execute(delete(EpisodeFile).where(EpisodeFile.media_file_id == media.id))
        media.subject_id = None
        media.subject_mapping_source = None
        media.subject_confidence = None
        media.subject_reasons = "[]"
        media.subject_manually_locked = False
        media.review_reason = "MANUALLY_UNLINKED"
        refresh_primary_conflicts(session)
        refresh_episode_statuses(session)
        return _file_view(session, media)


@router.post("/files/{file_id}/ignore")
async def ignore_file(file_id: int, payload: IgnoreRequest) -> dict[str, object]:
    with session_scope() as session:
        media = session.get(MediaFile, file_id)
        if media is None:
            raise HTTPException(404, detail={"code": "file_not_found", "message": "媒体文件不存在"})
        if payload.ignored:
            result = _file_view(session, media)
            result["ignored"] = True
            if session.scalar(select(IgnoredMediaPath.id).where(IgnoredMediaPath.path == media.path)) is None:
                session.add(IgnoredMediaPath(path=media.path))
            delete_media_record(session, media)
            refresh_primary_conflicts(session)
            refresh_episode_statuses(session)
            return result
        media.ignored = False
        media.review_reason = "RESTORED_FOR_REVIEW"
        refresh_primary_conflicts(session)
        refresh_episode_statuses(session)
        return _file_view(session, media)


@router.post("/files/{file_id}/reparse", status_code=status.HTTP_202_ACCEPTED)
async def reparse_file(file_id: int, request: Request) -> dict[str, object]:
    with session_scope() as session:
        media = session.get(MediaFile, file_id)
        if media is None:
            raise HTTPException(404, detail={"code": "file_not_found", "message": "媒体文件不存在"})
        if media.subject_manually_locked:
            raise HTTPException(409, detail={"code": "mapping_locked", "message": "请先解除人工锁定关联"})
        media.mtime_ns = -1
        media.ignored = False
    result = await _service(request).start()
    return {"task_id": result.task_id, "status": result.status, "reused": result.reused}


@router.post("/files/{file_id}/full-hash")
async def full_hash(file_id: int) -> dict[str, object]:
    with session_scope() as session:
        media = session.get(MediaFile, file_id)
        if media is None:
            raise HTTPException(404, detail={"code": "file_not_found", "message": "媒体文件不存在"})
        try:
            calculate_full_hash(media)
        except OSError as exc:
            raise HTTPException(409, detail={"code": "file_missing", "message": "媒体文件当前不可读取"}) from exc
        return _file_view(session, media)
