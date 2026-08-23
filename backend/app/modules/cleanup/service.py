from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from sqlalchemy import exists, func, or_, select

from backend.app.config import get_settings
from backend.app.database.models import (
    CleanupRecord,
    DownloadJob,
    Episode,
    EpisodeFile,
    MediaFile,
    PlaybackState,
    Subject,
)
from backend.app.database.session import session_scope
from backend.app.modules.download.service import ACTIVE_STATES
from backend.app.modules.library.matcher import refresh_episode_statuses
from backend.app.modules.library.scanner import delete_media_record, refresh_primary_conflicts


class CleanupNotFound(LookupError):
    pass


class CleanupNotAllowed(RuntimeError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("；".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True, slots=True)
class Eligibility:
    subject_id: int
    eligible: bool
    reasons: list[str]
    blockers: list[str]
    episodes: list[dict[str, object]]
    files: list[dict[str, object]]
    bytes_total: int
    eligible_at: datetime | None

    def view(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "eligible": self.eligible,
            "reasons": self.reasons,
            "blockers": self.blockers,
            "episodes": self.episodes,
            "files": self.files,
            "bytes_total": self.bytes_total,
            "eligible_at": self.eligible_at,
        }


class CleanupService:
    def __init__(self, active_media_ids: Callable[[], set[int]] | None = None) -> None:
        self.active_media_ids = active_media_ids or (lambda: set())
        self._lock = asyncio.Lock()

    def set_keep_forever(self, subject_id: int, keep: bool) -> dict[str, object]:
        with session_scope() as session:
            subject = session.get(Subject, subject_id)
            if subject is None:
                raise CleanupNotFound("条目不存在")
            subject.keep_forever = keep
            return {"subject_id": subject.id, "keep_forever": subject.keep_forever}

    def eligibility(self, subject_id: int, *, now: datetime | None = None) -> dict[str, object]:
        return self._eligibility(subject_id, now=now).view()

    def candidates(self, *, now: datetime | None = None) -> list[dict[str, object]]:
        current = now or datetime.now(UTC)
        retention_cutoff = current - timedelta(days=get_settings().cleanup.retention_days)
        main_episode = exists().where(
            Episode.subject_id == Subject.id,
            Episode.episode_type == "MAIN",
        )
        unwatched_episode = exists().where(
            Episode.subject_id == Subject.id,
            Episode.episode_type == "MAIN",
            Episode.watched.is_(False),
        )
        incomplete_playback = exists(
            select(Episode.id)
            .outerjoin(PlaybackState, PlaybackState.episode_id == Episode.id)
            .where(
                Episode.subject_id == Subject.id,
                Episode.episode_type == "MAIN",
                or_(PlaybackState.id.is_(None), PlaybackState.completed_at.is_(None)),
            )
        )
        recent_completion = exists(
            select(Episode.id)
            .join(PlaybackState, PlaybackState.episode_id == Episode.id)
            .where(
                Episode.subject_id == Subject.id,
                Episode.episode_type == "MAIN",
                PlaybackState.completed_at > retention_cutoff,
            )
        )
        active_download = exists().where(
            DownloadJob.subject_id == Subject.id,
            DownloadJob.state.in_(ACTIVE_STATES),
        )
        unresolved_mapping = exists().where(
            MediaFile.subject_id == Subject.id,
            MediaFile.review_reason.is_not(None),
        )
        available_media = exists().where(
            MediaFile.subject_id == Subject.id,
            MediaFile.exists.is_(True),
        )
        with session_scope() as session:
            ids = list(session.scalars(
                select(Subject.id)
                .where(
                    Subject.keep_forever.is_(False),
                    func.upper(Subject.air_status).in_({"FINISHED", "ENDED", "完结", "已完结"}),
                    main_episode,
                    ~unwatched_episode,
                    ~incomplete_playback,
                    ~recent_completion,
                    ~active_download,
                    ~unresolved_mapping,
                    available_media,
                )
                .order_by(Subject.id)
            ))
        return [
            view
            for subject_id in ids
            if (view := self.eligibility(subject_id, now=current))["eligible"]
        ]

    def records(self) -> list[dict[str, object]]:
        with session_scope() as session:
            records = list(session.scalars(
                select(CleanupRecord).order_by(CleanupRecord.created_at.desc())
            ))
            return [self._record_view(session, record) for record in records]

    async def quarantine(
        self, subject_id: int, *, trigger: str = "MANUAL", now: datetime | None = None
    ) -> dict[str, object]:
        async with self._lock:
            current = now or datetime.now(UTC)
            eligibility = self._eligibility(subject_id, now=current)
            if not eligibility.eligible:
                raise CleanupNotAllowed(eligibility.blockers)
            with session_scope() as session:
                active = session.scalar(select(CleanupRecord).where(
                    CleanupRecord.subject_id == subject_id,
                    CleanupRecord.status == "QUARANTINED",
                ))
                if active is not None:
                    return self._record_view(session, active)

            record_id = str(uuid.uuid4())
            root = get_settings().storage.quarantine_path.expanduser().resolve() / record_id
            root.mkdir(parents=True, exist_ok=False)
            moved: list[dict[str, object]] = []
            try:
                for index, file in enumerate(eligibility.files):
                    source = Path(str(file["path"])).expanduser().resolve()
                    destination = root / f"{index:04d}-{source.name}"
                    shutil.move(str(source), str(destination))
                    moved.append({
                        "media_id": file["id"],
                        "original_path": str(source),
                        "quarantine_path": str(destination),
                        "size": file["size"],
                    })
            except Exception:
                for item in reversed(moved):
                    destination = Path(str(item["quarantine_path"]))
                    original = Path(str(item["original_path"]))
                    if destination.exists() and not original.exists():
                        original.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(destination), str(original))
                shutil.rmtree(root, ignore_errors=True)
                raise

            with session_scope() as session:
                for item in moved:
                    media = session.get(MediaFile, int(item["media_id"]))
                    if media is not None:
                        media.path = str(item["quarantine_path"])
                        media.exists = False
                record = CleanupRecord(
                    id=record_id,
                    subject_id=subject_id,
                    status="QUARANTINED",
                    trigger=trigger,
                    reasons_json=json.dumps(eligibility.reasons, ensure_ascii=False),
                    episode_snapshot_json=json.dumps(eligibility.episodes, ensure_ascii=False, default=str),
                    files_json=json.dumps(moved, ensure_ascii=False),
                    bytes_total=eligibility.bytes_total,
                    eligible_at=eligibility.eligible_at or current,
                    quarantined_at=current,
                    delete_after=current + timedelta(days=get_settings().cleanup.quarantine_days),
                )
                session.add(record)
                refresh_episode_statuses(session)
                return self._record_view(session, record)

    async def restore(self, record_id: str, *, now: datetime | None = None) -> dict[str, object]:
        async with self._lock:
            with session_scope() as session:
                record = session.get(CleanupRecord, record_id)
                if record is None:
                    raise CleanupNotFound("清理记录不存在")
                if record.status != "QUARANTINED":
                    raise CleanupNotAllowed(["只有隔离中的条目可以恢复"])
                files = self._json_list(record.files_json)
            restored: list[dict[str, object]] = []
            try:
                for item in files:
                    source = Path(str(item["quarantine_path"]))
                    destination = Path(str(item["original_path"]))
                    if destination.exists():
                        raise FileExistsError(f"原路径已被占用：{destination}")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(destination))
                    restored.append(item)
            except Exception:
                for item in reversed(restored):
                    original = Path(str(item["original_path"]))
                    quarantine = Path(str(item["quarantine_path"]))
                    if original.exists() and not quarantine.exists():
                        quarantine.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(original), str(quarantine))
                raise

            with session_scope() as session:
                record = session.get(CleanupRecord, record_id)
                assert record is not None
                for item in files:
                    media = session.get(MediaFile, int(item["media_id"]))
                    if media is not None:
                        media.path = str(item["original_path"])
                        media.exists = Path(str(item["original_path"])).is_file()
                record.status = "RESTORED"
                record.restored_at = now or datetime.now(UTC)
                record.delete_after = None
                refresh_primary_conflicts(session)
                refresh_episode_statuses(session)
                self._remove_empty_quarantine(record_id)
                return self._record_view(session, record)

    async def permanently_delete(
        self, record_id: str, *, now: datetime | None = None, automatic: bool = False
    ) -> dict[str, object]:
        async with self._lock:
            current = now or datetime.now(UTC)
            with session_scope() as session:
                record = session.get(CleanupRecord, record_id)
                if record is None:
                    raise CleanupNotFound("清理记录不存在")
                if record.status != "QUARANTINED":
                    raise CleanupNotAllowed(["只有隔离中的条目可以永久删除"])
                if automatic and record.delete_after and self._aware(record.delete_after) > current:
                    raise CleanupNotAllowed(["隔离保留期尚未结束"])
                subject_id = record.subject_id
                files = self._json_list(record.files_json)

            eligibility = self._eligibility(subject_id, now=current, require_files=False)
            if not eligibility.eligible:
                raise CleanupNotAllowed(["永久删除复核失败", *eligibility.blockers])
            for item in files:
                Path(str(item["quarantine_path"])).unlink(missing_ok=True)
            with session_scope() as session:
                record = session.get(CleanupRecord, record_id)
                assert record is not None
                for item in files:
                    media = session.get(MediaFile, int(item["media_id"]))
                    if media is not None:
                        delete_media_record(session, media)
                record.status = "DELETED"
                record.deleted_at = current
                record.delete_after = None
                refresh_primary_conflicts(session)
                refresh_episode_statuses(session)
                self._remove_empty_quarantine(record_id)
                return self._record_view(session, record)

    async def run_automatic(self, *, now: datetime | None = None) -> dict[str, object]:
        current = now or datetime.now(UTC)
        if not get_settings().cleanup.enabled:
            return {"enabled": False, "quarantined": 0, "deleted": 0, "failed": 0}
        quarantined = deleted = failed = 0
        for candidate in self.candidates(now=current):
            try:
                await self.quarantine(int(candidate["subject_id"]), trigger="AUTOMATIC", now=current)
                quarantined += 1
            except (CleanupNotAllowed, OSError):
                failed += 1
        with session_scope() as session:
            due = list(session.scalars(select(CleanupRecord.id).where(
                CleanupRecord.status == "QUARANTINED",
                CleanupRecord.delete_after.is_not(None),
                CleanupRecord.delete_after <= current,
            )))
        for record_id in due:
            try:
                await self.permanently_delete(record_id, now=current, automatic=True)
                deleted += 1
            except (CleanupNotAllowed, OSError):
                failed += 1
        return {"enabled": True, "quarantined": quarantined, "deleted": deleted, "failed": failed}

    def _eligibility(
        self,
        subject_id: int,
        *,
        now: datetime | None = None,
        require_files: bool = True,
    ) -> Eligibility:
        current = now or datetime.now(UTC)
        blockers: list[str] = []
        reasons: list[str] = []
        with session_scope() as session:
            subject = session.get(Subject, subject_id)
            if subject is None:
                raise CleanupNotFound("条目不存在")
            main = list(session.scalars(select(Episode).where(
                Episode.subject_id == subject.id,
                Episode.episode_type == "MAIN",
            ).order_by(Episode.sort_number, Episode.id)))
            playback = {
                item.episode_id: item for item in session.scalars(select(PlaybackState).where(
                    PlaybackState.episode_id.in_([episode.id for episode in main])
                ))
            } if main else {}
            files = list(session.scalars(select(MediaFile).where(MediaFile.subject_id == subject.id)))
            active_download = session.scalar(select(DownloadJob.id).where(
                DownloadJob.subject_id == subject.id,
                DownloadJob.state.in_(ACTIVE_STATES),
            ).limit(1))
            unresolved = any(file.review_reason is not None for file in files)

            if subject.keep_forever:
                blockers.append("条目已设为永久保留")
            finished = subject.air_status.upper() in {"FINISHED", "ENDED", "完结", "已完结"}
            if not finished:
                blockers.append("Subject 尚未确认完结")
            if not main:
                blockers.append("没有 MAIN Episode")
            unwatched = [episode.display_number for episode in main if not episode.watched]
            if unwatched:
                blockers.append(f"仍有 {len(unwatched)} 个 MAIN Episode 未看")
            completed_times = [playback[episode.id].completed_at for episode in main if episode.id in playback]
            if not main:
                eligible_at = None
            elif len(completed_times) != len(main) or any(value is None for value in completed_times):
                blockers.append("部分 MAIN Episode 缺少完成时间")
                eligible_at = None
            else:
                last_completed = max(self._aware(value) for value in completed_times if value is not None)
                eligible_at = last_completed + timedelta(days=get_settings().cleanup.retention_days)
                if eligible_at > current:
                    blockers.append(f"保留期尚未结束（{eligible_at.isoformat()} 后可清理）")
            if active_download is not None:
                blockers.append("存在 active download")
            if unresolved:
                blockers.append("存在 unresolved mapping")
            active_ids = self.active_media_ids()
            if any(file.id in active_ids for file in files):
                blockers.append("媒体文件当前正在播放")
            disk_files = [file for file in files if file.exists and Path(file.path).is_file()]
            if require_files and not disk_files:
                blockers.append("没有可清理的本地媒体文件")

            if not blockers:
                reasons = [
                    "Subject 已完结",
                    f"全部 {len(main)} 个 MAIN Episode 已看且有完成时间",
                    f"已达到 {get_settings().cleanup.retention_days} 天保留期",
                    "没有 active download、unresolved mapping 或正在播放的文件",
                ]
            episode_view = [{
                "id": episode.id,
                "display_number": episode.display_number,
                "watched": episode.watched,
                "completed_at": playback.get(episode.id).completed_at if playback.get(episode.id) else None,
                "imported": episode.successfully_imported_at is not None,
            } for episode in main]
            file_view = [{"id": file.id, "path": file.path, "size": file.file_size} for file in disk_files]
            return Eligibility(
                subject_id=subject.id,
                eligible=not blockers,
                reasons=reasons,
                blockers=blockers,
                episodes=episode_view,
                files=file_view,
                bytes_total=sum(file.file_size for file in disk_files),
                eligible_at=eligible_at,
            )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _json_list(value: str) -> list[object]:
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _remove_empty_quarantine(record_id: str) -> None:
        directory = get_settings().storage.quarantine_path.expanduser().resolve() / record_id
        try:
            directory.rmdir()
        except OSError:
            pass

    @classmethod
    def _record_view(cls, session, record: CleanupRecord) -> dict[str, object]:
        subject = session.get(Subject, record.subject_id)
        return {
            "id": record.id,
            "subject_id": record.subject_id,
            "subject_name": (subject.name_cn or subject.name) if subject else "",
            "status": record.status,
            "trigger": record.trigger,
            "reasons": cls._json_list(record.reasons_json),
            "episodes": cls._json_list(record.episode_snapshot_json),
            "files": cls._json_list(record.files_json),
            "bytes_total": record.bytes_total,
            "eligible_at": record.eligible_at,
            "quarantined_at": record.quarantined_at,
            "restored_at": record.restored_at,
            "deleted_at": record.deleted_at,
            "delete_after": record.delete_after,
            "error": record.error,
        }
