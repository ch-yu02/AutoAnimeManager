from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, update

from backend.app.config import AppSettings
from backend.app.database.models import DownloadJob, DownloadJobEpisode, Episode, EpisodeFile, MediaFile, Subject
from backend.app.database.session import session_scope
from backend.app.modules.library.manifest import write_manifest
from backend.app.modules.library.matcher import refresh_episode_statuses
from backend.app.modules.library.parser import parse_filename
from backend.app.modules.library.probe import probe_media
from backend.app.modules.library.scanner import partial_hash, refresh_primary_conflicts


class ImportFailure(RuntimeError):
    pass


@dataclass(slots=True)
class ImportResult:
    imported_files: int
    review_files: int = 0


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")
    return cleaned[:180] or "未命名条目"


def subject_download_directory(settings: AppSettings, subject: Subject) -> Path:
    root = settings.storage.effective_library_roots()[0].expanduser().resolve()
    return root / f"[bgm-{subject.bangumi_subject_id}] {_safe_name(subject.name_cn or subject.name)}"


def _source_paths(job: DownloadJob, files: list[dict[str, object]], extensions: set[str]) -> list[Path]:
    base = Path(job.save_path).expanduser().resolve()
    result: list[Path] = []
    for item in files:
        if int(item.get("priority", 1) or 0) <= 0 or float(item.get("progress", 0) or 0) < 1:
            continue
        relative = Path(str(item.get("name", "")))
        candidate = (base / relative).resolve()
        if not candidate.is_relative_to(base):
            raise ImportFailure("qBittorrent 返回了下载目录之外的文件路径")
        if candidate.is_file() and candidate.suffix.lower() in extensions:
            result.append(candidate)
    return list(dict.fromkeys(result))


def _upsert_media(
    session,
    path: Path,
    settings: AppSettings,
    *,
    subject: Subject,
    review_reason: str | None,
) -> MediaFile:
    stat = path.stat()
    parsed = parse_filename(path)
    probe = probe_media(path, settings.storage.ffprobe_path, settings.storage.ffprobe_enabled)
    media = session.scalar(select(MediaFile).where(MediaFile.path == str(path)))
    if media is None:
        media = MediaFile(
            path=str(path), filename=path.name, file_size=stat.st_size, mtime_ns=stat.st_mtime_ns,
            last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
    media.filename = path.name
    media.file_size = stat.st_size
    media.mtime_ns = stat.st_mtime_ns
    media.device_id = stat.st_dev
    media.inode = stat.st_ino
    media.partial_hash = partial_hash(path, settings.storage.partial_hash_bytes)
    media.duration_seconds = probe.duration_seconds
    media.video_codec = probe.video_codec or parsed.codec
    media.resolution = probe.resolution or parsed.resolution
    media.audio_languages = json.dumps(probe.audio_languages or [], ensure_ascii=False)
    media.subtitle_languages = json.dumps(probe.subtitle_languages or [], ensure_ascii=False)
    media.parse_result = json.dumps(parsed.to_dict(), ensure_ascii=False)
    media.review_reason = review_reason
    media.exists = True
    media.ignored = False
    media.subject_id = subject.id
    media.subject_mapping_source = "DOWNLOAD_JOB"
    media.subject_confidence = 1.0 if review_reason is None else 0.0
    media.subject_reasons = json.dumps(["由下载任务直接关联"], ensure_ascii=False)
    # 下载异常必须停留在审核队列，不能被后续普通扫描绕过人工确认。
    media.subject_manually_locked = True
    media.last_scanned_at = datetime.now(UTC)
    return media


class FileImporter:
    def __init__(self, settings_provider) -> None:
        self.settings_provider = settings_provider

    def import_job(self, job_id: str, files: list[dict[str, object]]) -> ImportResult:
        settings = self.settings_provider()
        with session_scope() as session:
            job = session.get(DownloadJob, job_id)
            if job is None:
                raise ImportFailure("下载任务不存在")
            subject = session.get(Subject, job.subject_id)
            episode_links = list(
                session.scalars(select(DownloadJobEpisode).where(DownloadJobEpisode.job_id == job.id))
            )
            episodes = [session.get(Episode, link.episode_id) for link in episode_links]
            episodes = [episode for episode in episodes if episode is not None]
            if subject is None or not episodes:
                raise ImportFailure("下载任务关联的条目或 Episode 已不存在")
            sources = _source_paths(job, files, set(settings.storage.video_extensions))
            if not sources:
                raise ImportFailure("下载内容中没有完整、受支持的视频文件")
            roots = [root.expanduser().resolve() for root in settings.storage.effective_library_roots()]
            if any(not any(source.is_relative_to(root) for root in roots) for source in sources):
                raise ImportFailure("下载文件不在媒体库目录中，无法原地导入")

            expected_count = len(episodes)
            suspicious_multi_episode = any(
                (parsed := parse_filename(source)).is_batch
                or (parsed.episode_end is not None and parsed.episode_end != parsed.episode_start)
                for source in sources
            )
            review_reason = None
            if len(sources) != expected_count:
                review_reason = "DOWNLOAD_EPISODE_COUNT_MISMATCH"
            elif suspicious_multi_episode:
                review_reason = "DOWNLOAD_MULTI_EPISODE_FILE"

            imported = [
                _upsert_media(session, source, settings, subject=subject, review_reason=review_reason)
                for source in sources
            ]

            if review_reason is not None:
                refresh_primary_conflicts(session)
                refresh_episode_statuses(session)
                return ImportResult(imported_files=0, review_files=len(imported))

            for episode, media in zip(episodes, imported, strict=True):
                session.execute(delete(EpisodeFile).where(EpisodeFile.media_file_id == media.id))
                session.execute(
                    update(EpisodeFile).where(EpisodeFile.episode_id == episode.id).values(is_primary=False)
                )
                session.add(EpisodeFile(
                    episode_id=episode.id,
                    media_file_id=media.id,
                    mapping_source="DOWNLOAD_JOB",
                    confidence=1.0,
                    reasons=json.dumps([f"下载任务 {job.id} 直接关联"], ensure_ascii=False),
                    is_primary=True,
                    manually_locked=True,
                ))
                write_manifest(Path(media.path), subject.bangumi_subject_id, [episode.bangumi_episode_id], True)
            refresh_primary_conflicts(session)
            refresh_episode_statuses(session)
            return ImportResult(imported_files=len(imported))
