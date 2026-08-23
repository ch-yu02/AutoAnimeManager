from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, update

from backend.app.config import AppSettings
from backend.app.database.models import EpisodeFile, IgnoredMediaPath, LibraryScanRun, MediaFile, PlaybackState
from backend.app.database.session import session_scope
from backend.app.modules.library.matcher import match_media_file, refresh_episode_statuses
from backend.app.modules.library.parser import PARSER_VERSION, parse_filename
from backend.app.modules.library.probe import probe_media

logger = logging.getLogger(__name__)
VIDEO_CANDIDATE_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".ts",
    ".flv", ".wmv", ".mpg", ".mpeg", ".vob", ".ogv",
}


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def partial_hash(path: Path, chunk_size: int) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as stream:
        digest.update(stream.read(chunk_size))
        if size > chunk_size:
            stream.seek(max(0, size - chunk_size))
            digest.update(stream.read(chunk_size))
    digest.update(str(size).encode("ascii"))
    return digest.hexdigest()


def _full_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parser_is_outdated(media: MediaFile) -> bool:
    try:
        parsed = json.loads(media.parse_result)
    except (json.JSONDecodeError, TypeError):
        return True
    return not isinstance(parsed, dict) or parsed.get("parser_version") != PARSER_VERSION


def calculate_full_hash(media: MediaFile) -> str:
    path = Path(media.path)
    if not media.exists or not path.is_file():
        raise FileNotFoundError(media.path)
    media.full_hash = _full_hash(path)
    return media.full_hash


def delete_media_record(session, media: MediaFile) -> None:
    """Delete a media inventory row without leaving mappings or playback references behind."""
    session.execute(update(PlaybackState).where(PlaybackState.media_file_id == media.id).values(media_file_id=None))
    session.execute(delete(EpisodeFile).where(EpisodeFile.media_file_id == media.id))
    session.delete(media)


def refresh_primary_conflicts(session) -> None:
    for media in session.scalars(
        select(MediaFile).where(MediaFile.review_reason.in_(["PRIMARY_FILE_CONFLICT", "HARDLINK_DUPLICATE"]))
    ):
        media.review_reason = None if media.subject_id else "RESTORED_FOR_REVIEW"
    primary_mappings = list(session.scalars(
        select(EpisodeFile)
        .join(MediaFile, MediaFile.id == EpisodeFile.media_file_id)
        .where(EpisodeFile.is_primary.is_(True), MediaFile.exists.is_(True), MediaFile.ignored.is_(False))
    ))
    episode_counts: dict[int, int] = {}
    for mapping in primary_mappings:
        episode_counts[mapping.episode_id] = episode_counts.get(mapping.episode_id, 0) + 1
    conflicts = {episode_id for episode_id, count in episode_counts.items() if count > 1}
    for episode_id in conflicts:
        mappings = [mapping for mapping in primary_mappings if mapping.episode_id == episode_id]
        files = [session.get(MediaFile, mapping.media_file_id) for mapping in mappings]
        active_files = [media for media in files if media is not None and not media.ignored]
        identities = {(media.device_id, media.inode) for media in active_files if media.device_id is not None and media.inode is not None}
        hardlinked = len(identities) == 1 and len(active_files) > 1
        for media in active_files:
            if media.full_hash is None:
                try:
                    calculate_full_hash(media)
                except OSError:
                    pass
            media.review_reason = "HARDLINK_DUPLICATE" if hardlinked else "PRIMARY_FILE_CONFLICT"


class LibraryScanner:
    def __init__(self, settings_provider) -> None:
        self.settings_provider = settings_provider

    def _discover(self, settings: AppSettings, roots: list[Path] | None = None) -> list[Path]:
        roots = roots or [
            root.expanduser().resolve()
            for root in settings.storage.effective_library_roots()
            if root.expanduser().is_dir()
        ]
        excluded = [settings.storage.quarantine_path.expanduser().resolve()]
        extensions = set(settings.storage.video_extensions)
        with session_scope() as session:
            ignored_paths = set(session.scalars(select(IgnoredMediaPath.path)))
        files: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in extensions | VIDEO_CANDIDATE_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if str(resolved) in ignored_paths or any(_inside(resolved, directory) for directory in excluded):
                    continue
                files.append(resolved)
        return sorted(set(files))

    def rematch_review(self) -> dict[str, int]:
        processed = 0
        matched = 0
        with session_scope() as session:
            media_files = list(session.scalars(
                select(MediaFile).where(
                    MediaFile.review_reason.is_not(None),
                    MediaFile.exists.is_(True),
                    MediaFile.ignored.is_(False),
                    MediaFile.subject_manually_locked.is_(False),
                ).order_by(MediaFile.id)
            ))
            for media in media_files:
                path = Path(media.path)
                if not path.is_file():
                    delete_media_record(session, media)
                    continue
                processed += 1
                parsed = parse_filename(path)
                media.parse_result = json.dumps(parsed.to_dict(), ensure_ascii=False)
                if match_media_file(session, media, path, parsed):
                    matched += 1
            refresh_primary_conflicts(session)
            refresh_episode_statuses(session)
            review_count = sum(
                media.review_reason is not None and media.exists and not media.ignored
                for media in session.scalars(select(MediaFile))
            )
        return {"processed_count": processed, "matched_count": matched, "review_count": review_count}

    def scan(self, task_id: str | None = None) -> str:
        task_id = task_id or str(uuid.uuid4())
        now = datetime.now(UTC)
        with session_scope() as session:
            run = session.get(LibraryScanRun, task_id)
            if run is None:
                run = LibraryScanRun(id=task_id, status="RUNNING", started_at=now)
                session.add(run)
        try:
            settings = self.settings_provider()
            configured_roots = [
                root.expanduser().resolve()
                for root in settings.storage.effective_library_roots()
            ]
            available_roots = [root for root in configured_roots if root.is_dir()]
            if not available_roots:
                raise FileNotFoundError("所有媒体库目录当前均不可用，已保留现有媒体记录")
            with session_scope() as session:
                for media in session.scalars(select(MediaFile).where(MediaFile.ignored.is_(True))):
                    if session.scalar(select(IgnoredMediaPath.id).where(IgnoredMediaPath.path == media.path)) is None:
                        session.add(IgnoredMediaPath(path=media.path))
                    delete_media_record(session, media)
            paths = self._discover(settings, available_roots)
            allowed_extensions = set(settings.storage.video_extensions)
            seen: set[str] = set()
            with session_scope() as session:
                run = session.get(LibraryScanRun, task_id)
                assert run is not None
                run.discovered_count = len(paths)
                existing = list(session.scalars(select(MediaFile)))
                by_path = {item.path: item for item in existing}
                disk_paths = {str(path) for path in paths}
                for path in paths:
                    path_text = str(path)
                    seen.add(path_text)
                    stat = path.stat()
                    media = by_path.get(path_text)
                    precomputed_partial: str | None = None
                    unchanged = media is not None and media.file_size == stat.st_size and media.mtime_ns == stat.st_mtime_ns
                    if unchanged:
                        media.exists = True
                        media.last_scanned_at = now
                        if media.review_reason == "MISSING":
                            media.review_reason = None if media.subject_id else "RESTORED_FOR_REVIEW"
                        if (
                            not media.ignored
                            and not media.subject_manually_locked
                            and (media.review_reason is not None or _parser_is_outdated(media))
                        ):
                            parsed = parse_filename(path)
                            media.parse_result = json.dumps(parsed.to_dict(), ensure_ascii=False)
                            if match_media_file(session, media, path, parsed):
                                run.matched_count += 1
                        continue
                    if media is None:
                        media = next((item for item in existing if item.path not in disk_paths and item.device_id == stat.st_dev and item.inode == stat.st_ino), None)
                        if media is None:
                            precomputed_partial = partial_hash(path, settings.storage.partial_hash_bytes)
                            media = next((
                                item for item in existing
                                if item.path not in disk_paths
                                and item.file_size == stat.st_size
                                and item.partial_hash == precomputed_partial
                            ), None)
                        if media is not None:
                            run.moved_count += 1
                            by_path.pop(media.path, None)
                            media.path = path_text
                            media.filename = path.name
                        else:
                            media = MediaFile(
                                path=path_text, filename=path.name, file_size=stat.st_size,
                                mtime_ns=stat.st_mtime_ns, device_id=stat.st_dev, inode=stat.st_ino,
                                last_scanned_at=now,
                            )
                            session.add(media)
                            session.flush()
                            existing.append(media)
                            run.added_count += 1
                    else:
                        run.changed_count += 1
                    if path.suffix.lower() not in allowed_extensions:
                        media.filename = path.name
                        media.file_size = stat.st_size
                        media.mtime_ns = stat.st_mtime_ns
                        media.device_id = stat.st_dev
                        media.inode = stat.st_ino
                        media.partial_hash = None
                        media.full_hash = None
                        media.parse_result = "{}"
                        media.exists = True
                        media.review_reason = "UNSUPPORTED_FORMAT"
                        media.last_scanned_at = now
                        continue
                    parsed = parse_filename(path)
                    probe = probe_media(path, settings.storage.ffprobe_path, settings.storage.ffprobe_enabled)
                    media.filename = path.name
                    media.file_size = stat.st_size
                    media.mtime_ns = stat.st_mtime_ns
                    media.device_id = stat.st_dev
                    media.inode = stat.st_ino
                    media.partial_hash = precomputed_partial or partial_hash(path, settings.storage.partial_hash_bytes)
                    collision = session.scalar(
                        select(MediaFile).where(
                            MediaFile.id != media.id,
                            MediaFile.file_size == stat.st_size,
                            MediaFile.partial_hash == media.partial_hash,
                            MediaFile.exists.is_(True),
                        ).limit(1)
                    )
                    if collision is not None:
                        media.full_hash = _full_hash(path)
                        collision_path = Path(collision.path)
                        if collision.full_hash is None and collision_path.is_file():
                            collision.full_hash = _full_hash(collision_path)
                    media.duration_seconds = probe.duration_seconds
                    media.video_codec = probe.video_codec or parsed.codec
                    media.resolution = probe.resolution or parsed.resolution
                    media.audio_languages = json.dumps(probe.audio_languages or [], ensure_ascii=False)
                    media.subtitle_languages = json.dumps(probe.subtitle_languages or [], ensure_ascii=False)
                    media.parse_result = json.dumps(parsed.to_dict(), ensure_ascii=False)
                    media.exists = True
                    media.last_scanned_at = now
                    if not media.ignored:
                        if match_media_file(session, media, path, parsed):
                            run.matched_count += 1
                        elif media.review_reason:
                            run.review_count += 1
                for media in existing:
                    try:
                        stored_path = Path(media.path).resolve()
                    except OSError:
                        continue
                    if media.path not in seen and any(
                        _inside(stored_path, root) for root in available_roots
                    ):
                        delete_media_record(session, media)
                        run.missing_count += 1
                refresh_primary_conflicts(session)
                refresh_episode_statuses(session)
                run.review_count = sum(
                    item.review_reason is not None and not item.ignored and item.exists for item in existing
                )
                run.status = "SUCCEEDED"
                run.finished_at = datetime.now(UTC)
            return task_id
        except Exception as exc:
            logger.exception("媒体库扫描失败")
            with session_scope() as session:
                run = session.get(LibraryScanRun, task_id)
                if run:
                    run.status = "FAILED"
                    run.finished_at = datetime.now(UTC)
                    run.error_summary = str(exc)[:2000]
            return task_id
