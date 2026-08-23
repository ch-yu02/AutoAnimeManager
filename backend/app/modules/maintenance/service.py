from __future__ import annotations

import json
import platform
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from backend.app import __version__
from backend.app.config import get_settings, public_settings
from backend.app.database.models import CleanupRecord, DownloadJob, ReleaseCandidate, TaskRun
from backend.app.database.session import session_scope


class MaintenanceService:
    """Creates verified SQLite backups and privacy-conscious diagnostic archives."""

    def __init__(self, settings_provider=get_settings) -> None:
        self.settings_provider = settings_provider

    def database_path(self) -> Path:
        database = make_url(self.settings_provider().database.url).database
        if not database or database == ":memory:":
            raise RuntimeError("当前数据库不支持文件备份")
        return Path(database).expanduser().resolve()

    @staticmethod
    def verify_database(path: Path) -> None:
        if not path.is_file():
            raise RuntimeError(f"数据库不存在：{path}")
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库验证失败：{exc}") from exc
        if result is None or result[0] != "ok":
            raise RuntimeError(f"数据库完整性检查失败：{result[0] if result else '无结果'}")

    def create_backup(self) -> dict[str, object]:
        settings = self.settings_provider().maintenance
        source_path = self.database_path()
        destination_dir = settings.backup_path.expanduser().resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        # A power loss can leave only staging files behind. They are never valid
        # retention entries and must not accumulate across daily runs.
        for stale in destination_dir.glob("autoanime-*.db.tmp*"):
            stale.unlink(missing_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        destination = destination_dir / f"autoanime-{stamp}.db"
        temporary = destination.with_suffix(".db.tmp")
        try:
            with sqlite3.connect(source_path) as source, sqlite3.connect(temporary) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
            self.verify_database(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
            for suffix in ("-journal", "-wal", "-shm"):
                Path(f"{temporary}{suffix}").unlink(missing_ok=True)

        backups = sorted(destination_dir.glob("autoanime-*.db"), reverse=True)
        for expired in backups[settings.backup_keep_count:]:
            expired.unlink(missing_ok=True)
        return {
            "enabled": True,
            "created": True,
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "retained": min(len(backups), settings.backup_keep_count),
            "verified": True,
        }

    def generate_diagnostics(self) -> dict[str, object]:
        settings = self.settings_provider()
        destination_dir = settings.maintenance.diagnostics_path.expanduser().resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        destination = destination_dir / f"autoanime-diagnostics-{stamp}.zip"

        database_path = self.database_path()
        integrity = "ok"
        try:
            self.verify_database(database_path)
        except RuntimeError as exc:
            integrity = str(exc)

        with session_scope() as session:
            task_runs = [
                {
                    "id": item.id,
                    "task_name": item.task_name,
                    "trigger": item.trigger,
                    "status": item.status,
                    "attempt": item.attempt,
                    "started_at": item.started_at,
                    "finished_at": item.finished_at,
                    "next_retry_at": item.next_retry_at,
                    "result": self._load_json(item.result_json, {}),
                    "error": item.error,
                }
                for item in session.scalars(
                    select(TaskRun).order_by(TaskRun.started_at.desc()).limit(100)
                )
            ]
            downloads = [
                {
                    "id": item.id,
                    "subject_id": item.subject_id,
                    "state": item.state,
                    "progress": item.progress,
                    "error": item.error,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "completed_at": item.completed_at,
                    "imported_at": item.imported_at,
                }
                for item in session.scalars(
                    select(DownloadJob).order_by(DownloadJob.created_at.desc()).limit(100)
                )
            ]
            cleanup = [
                {
                    "id": item.id,
                    "subject_id": item.subject_id,
                    "status": item.status,
                    "trigger": item.trigger,
                    "bytes_total": item.bytes_total,
                    "eligible_at": item.eligible_at,
                    "quarantined_at": item.quarantined_at,
                    "restored_at": item.restored_at,
                    "deleted_at": item.deleted_at,
                    "error": item.error,
                }
                for item in session.scalars(
                    select(CleanupRecord).order_by(CleanupRecord.created_at.desc()).limit(100)
                )
            ]
            release_counts = dict(session.execute(
                select(ReleaseCandidate.decision, func.count(ReleaseCandidate.id))
                .group_by(ReleaseCandidate.decision)
            ).all())

        disk = shutil.disk_usage(database_path.parent)
        summary = {
            "generated_at": datetime.now(UTC),
            "autoanime_version": __version__,
            "python_version": sys.version,
            "platform": platform.platform(),
            "database_integrity": integrity,
            "database_size_bytes": database_path.stat().st_size if database_path.exists() else None,
            "database_disk_free_bytes": disk.free,
            "release_candidate_counts": release_counts,
        }
        log_path = Path("data/logs/autoanime.log")

        with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
            self._write_json(archive, "summary.json", summary)
            self._write_json(archive, "settings.redacted.json", public_settings(settings))
            self._write_json(archive, "task-runs.json", task_runs)
            self._write_json(archive, "download-import-audit.json", downloads)
            self._write_json(archive, "cleanup-audit.json", cleanup)
            if log_path.is_file():
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                archive.writestr(
                    "autoanime.log.tail.jsonl",
                    "\n".join(lines[-settings.maintenance.diagnostics_log_lines:]) + "\n",
                )
        return {"path": str(destination), "size_bytes": destination.stat().st_size}

    @staticmethod
    def _load_json(value: str, fallback):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return fallback

    @staticmethod
    def _write_json(archive: ZipFile, name: str, payload: object) -> None:
        archive.writestr(
            name,
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        )
