from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.config import get_settings
from backend.app.database.models import (
    DownloadJob,
    DownloadJobEpisode,
    Episode,
    EpisodeFile,
    MediaFile,
    Subject,
)
from backend.app.database.session import session_scope
from backend.app.modules.download.importer import FileImporter, ImportFailure, subject_download_directory
from backend.app.modules.download.magnet import normalize_magnet
from backend.app.modules.download.qbittorrent import QBittorrentAdapter, QBittorrentError
from backend.app.modules.library.matcher import refresh_episode_statuses
from backend.app.modules.library.scanner import delete_media_record, refresh_primary_conflicts


logger = logging.getLogger(__name__)
ACTIVE_STATES = {"CREATED", "QUEUED", "DOWNLOADING", "STALLED", "COMPLETED", "IMPORTING"}
TERMINAL_STATES = {"IMPORTED", "FAILED"}


class DuplicateDownload(RuntimeError):
    def __init__(self, message: str, job_id: str) -> None:
        super().__init__(message)
        self.job_id = job_id


class DownloadNotFound(RuntimeError):
    pass


class EpisodeNotDownloadable(RuntimeError):
    pass


class DownloadDeleteNotAllowed(RuntimeError):
    pass


class DownloadService:
    def __init__(self, adapter=None, importer: FileImporter | None = None) -> None:
        self.adapter = adapter or QBittorrentAdapter(lambda: get_settings().qbittorrent)
        self.importer = importer or FileImporter(get_settings)
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._reconcile_lock = asyncio.Lock()
        self._import_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autoanime-import")
        self._imports: dict[str, Future[None]] = {}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._import_executor.shutdown(wait=True, cancel_futures=False)
        await self.adapter.close()

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.reconcile_all()
            except Exception:
                logger.exception("下载任务恢复失败")
            await asyncio.sleep(get_settings().qbittorrent.poll_interval_seconds)

    async def create(self, episode_id: int, magnet: str) -> dict[str, object]:
        magnet_uri, torrent_hash = normalize_magnet(magnet)
        try:
            with session_scope() as session:
                episode = session.get(Episode, episode_id)
                if episode is None:
                    raise EpisodeNotDownloadable("Episode 不存在")
                subject = session.get(Subject, episode.subject_id)
                if subject is None:
                    raise EpisodeNotDownloadable("Episode 对应条目不存在")
                ready_file = session.scalar(
                    select(MediaFile.id)
                    .join(EpisodeFile, EpisodeFile.media_file_id == MediaFile.id)
                    .where(
                        EpisodeFile.episode_id == episode.id,
                        MediaFile.exists.is_(True),
                        MediaFile.ignored.is_(False),
                    )
                )
                if ready_file is not None:
                    raise EpisodeNotDownloadable("Episode 已有可播放的本地文件")
                duplicate = session.scalar(
                    select(DownloadJob).where(
                        (DownloadJob.magnet_hash == torrent_hash) | (DownloadJob.torrent_hash == torrent_hash)
                    )
                )
                if duplicate is not None:
                    raise DuplicateDownload("相同 magnet 已提交", duplicate.id)
                episode_job = session.scalar(
                    select(DownloadJob)
                    .join(DownloadJobEpisode, DownloadJobEpisode.job_id == DownloadJob.id)
                    .where(DownloadJobEpisode.episode_id == episode.id)
                )
                if episode_job is not None:
                    raise DuplicateDownload("该 Episode 已有下载任务", episode_job.id)
                job_id = str(uuid.uuid4())
                save_path = subject_download_directory(get_settings(), subject)
                save_path.mkdir(parents=True, exist_ok=True)
                job = DownloadJob(
                    id=job_id,
                    magnet_uri=magnet_uri,
                    magnet_hash=torrent_hash,
                    torrent_hash=torrent_hash,
                    subject_id=subject.id,
                    qbittorrent_task=torrent_hash,
                    progress=0,
                    state="CREATED",
                    save_path=str(save_path),
                )
                session.add(job)
                session.add(DownloadJobEpisode(job_id=job_id, episode_id=episode.id))
        except IntegrityError as exc:
            with session_scope() as session:
                duplicate = session.scalar(select(DownloadJob).where(
                    (DownloadJob.magnet_hash == torrent_hash) | (DownloadJob.torrent_hash == torrent_hash)
                )) or session.scalar(
                    select(DownloadJob)
                    .join(DownloadJobEpisode, DownloadJobEpisode.job_id == DownloadJob.id)
                    .where(DownloadJobEpisode.episode_id == episode_id)
                )
                if duplicate is not None:
                    raise DuplicateDownload("相同 magnet 或 Episode 已有下载任务", duplicate.id) from exc
            raise
        await self.reconcile(job_id)
        return self.get(job_id)

    def list(self) -> list[dict[str, object]]:
        with session_scope() as session:
            jobs = list(session.scalars(select(DownloadJob).order_by(DownloadJob.created_at.desc())))
            return [self._view(session, job) for job in jobs]

    def get(self, job_id: str) -> dict[str, object]:
        with session_scope() as session:
            job = session.get(DownloadJob, job_id)
            if job is None:
                raise DownloadNotFound("下载任务不存在")
            return self._view(session, job)

    @staticmethod
    def _view(session, job: DownloadJob) -> dict[str, object]:
        subject = session.get(Subject, job.subject_id)
        episodes = list(
            session.scalars(
                select(Episode)
                .join(DownloadJobEpisode, DownloadJobEpisode.episode_id == Episode.id)
                .where(DownloadJobEpisode.job_id == job.id)
                .order_by(Episode.sort_number, Episode.id)
            )
        )
        return {
            "id": job.id,
            "torrent_hash": job.torrent_hash,
            "magnet_hash": job.magnet_hash,
            "subject_id": job.subject_id,
            "subject": {
                "id": subject.id,
                "name": subject.name_cn or subject.name,
                "bangumi_subject_id": subject.bangumi_subject_id,
            } if subject else None,
            "episode_ids": [episode.id for episode in episodes],
            "episodes": [
                {
                    "id": episode.id,
                    "display_number": episode.display_number,
                    "name": episode.name_cn or episode.name,
                }
                for episode in episodes
            ],
            "qbittorrent_task": job.qbittorrent_task,
            "progress": job.progress,
            "state": job.state,
            "error": job.error,
            "save_path": job.save_path,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "completed_at": job.completed_at,
            "imported_at": job.imported_at,
        }

    async def reconcile_all(self) -> None:
        with session_scope() as session:
            ids = list(session.scalars(select(DownloadJob.id).where(DownloadJob.state.in_(ACTIVE_STATES))))
        for job_id in ids:
            await self.reconcile(job_id)

    async def reconcile(self, job_id: str) -> None:
        async with self._reconcile_lock:
            with session_scope() as session:
                job = session.get(DownloadJob, job_id)
                if job is None:
                    raise DownloadNotFound("下载任务不存在")
                state = job.state
                torrent_hash = job.torrent_hash or job.magnet_hash
                magnet = job.magnet_uri
                save_path = job.save_path
                subject_id = job.subject_id
                subject = session.get(Subject, subject_id)
                bangumi_subject_id = subject.bangumi_subject_id if subject else subject_id
            if state in TERMINAL_STATES:
                return
            try:
                if state == "CREATED":
                    settings = get_settings().qbittorrent
                    await self.adapter.add(
                        magnet,
                        save_path=save_path,
                        category=settings.category,
                        tags=[f"bgm-{bangumi_subject_id}", f"job-{job_id}"],
                        torrent_hash=torrent_hash,
                    )
                    with session_scope() as session:
                        job = session.get(DownloadJob, job_id)
                        if job:
                            job.state = "QUEUED"
                            job.error = None

                if state in {"COMPLETED", "IMPORTING"}:
                    await self._import(job_id, torrent_hash)
                    return

                info = await self.adapter.status(torrent_hash)
                if info is None:
                    settings = get_settings().qbittorrent
                    await self.adapter.add(
                        magnet,
                        save_path=save_path,
                        category=settings.category,
                        tags=[f"bgm-{bangumi_subject_id}", f"job-{job_id}"],
                        torrent_hash=torrent_hash,
                    )
                    with session_scope() as session:
                        job = session.get(DownloadJob, job_id)
                        if job:
                            job.state = "QUEUED"
                            job.error = "任务已提交，等待 qBittorrent 获取元数据"
                    return
                progress = min(1.0, max(0.0, float(info.get("progress", 0) or 0)))
                qb_state = str(info.get("state", ""))
                completed = progress >= 0.999999 and qb_state not in {"metaDL", "checkingDL", "checkingResumeData"}
                with session_scope() as session:
                    job = session.get(DownloadJob, job_id)
                    if job is None:
                        return
                    job.progress = progress
                    job.error = None
                    if qb_state.lower().startswith("error") or qb_state == "missingFiles":
                        job.state = "FAILED"
                        job.error = f"qBittorrent 任务异常：{qb_state}"
                        return
                    if completed:
                        job.state = "COMPLETED"
                        job.completed_at = datetime.now(UTC)
                    elif qb_state in {"stalledDL", "pausedDL", "stoppedDL"}:
                        job.state = "STALLED"
                        job.error = "下载已暂停" if qb_state in {"pausedDL", "stoppedDL"} else "下载暂时无可用数据"
                    elif qb_state in {"metaDL", "queuedDL", "checkingDL", "checkingResumeData"}:
                        job.state = "QUEUED"
                    else:
                        job.state = "DOWNLOADING"
                if completed:
                    await self._import(job_id, torrent_hash)
            except (QBittorrentError, OSError) as exc:
                logger.warning("下载任务 %s 暂停同步：%s", job_id, exc)
                with session_scope() as session:
                    job = session.get(DownloadJob, job_id)
                    if job and job.state not in TERMINAL_STATES:
                        job.state = "STALLED"
                        job.error = str(exc)[:2000]

    async def _import(self, job_id: str, torrent_hash: str) -> None:
        running = self._imports.get(job_id)
        if running is not None and not running.done():
            return
        with session_scope() as session:
            job = session.get(DownloadJob, job_id)
            if job is None:
                return
            job.state = "IMPORTING"
            job.error = None
        files = await self.adapter.files(torrent_hash)
        future = self._import_executor.submit(self._import_sync, job_id, files)
        self._imports[job_id] = future
        future.add_done_callback(lambda _: self._imports.pop(job_id, None))

    def _import_sync(self, job_id: str, files: list[dict[str, object]]) -> None:
        try:
            result = self.importer.import_job(job_id, files)
            with session_scope() as session:
                job = session.get(DownloadJob, job_id)
                if job is None:
                    return
                if result.review_files:
                    job.state = "FAILED"
                    job.error = f"{result.review_files} 个文件已进入媒体库审核"
                else:
                    job.state = "IMPORTED"
                    job.progress = 1.0
                    job.imported_at = datetime.now(UTC)
                    job.error = None
        except (ImportFailure, OSError) as exc:
            with session_scope() as session:
                job = session.get(DownloadJob, job_id)
                if job:
                    job.state = "FAILED"
                    job.error = str(exc)[:2000]

    async def pause(self, job_id: str) -> dict[str, object]:
        job = self.get(job_id)
        await self.adapter.pause(str(job["torrent_hash"]))
        with session_scope() as session:
            stored = session.get(DownloadJob, job_id)
            if stored:
                stored.state = "STALLED"
                stored.error = "下载已暂停"
        return self.get(job_id)

    async def resume(self, job_id: str) -> dict[str, object]:
        job = self.get(job_id)
        await self.adapter.resume(str(job["torrent_hash"]))
        with session_scope() as session:
            stored = session.get(DownloadJob, job_id)
            if stored:
                stored.state = "QUEUED"
                stored.error = None
        return self.get(job_id)

    async def retry(self, job_id: str) -> dict[str, object]:
        self.get(job_id)
        with session_scope() as session:
            stored = session.get(DownloadJob, job_id)
            if stored:
                stored.state = "STALLED"
                stored.error = None
        await self.reconcile(job_id)
        return self.get(job_id)

    async def delete(self, job_id: str, *, delete_files: bool) -> dict[str, object]:
        async with self._reconcile_lock:
            job = self.get(job_id)
            running = self._imports.get(job_id)
            if running is not None and not running.done():
                raise DownloadDeleteNotAllowed("任务正在导入，请等待导入结束")
            await self.adapter.delete(str(job["torrent_hash"]), delete_files=delete_files)
            if delete_files:
                self._remove_missing_media(Path(str(job["save_path"])))
            self._delete_record(job_id)
            return {"id": job_id, "deleted": True, "delete_files": delete_files}

    @staticmethod
    def _delete_record(job_id: str) -> None:
        with session_scope() as session:
            stored = session.get(DownloadJob, job_id)
            if stored is None:
                raise DownloadNotFound("下载任务不存在")
            for link in session.scalars(
                select(DownloadJobEpisode).where(DownloadJobEpisode.job_id == job_id)
            ):
                session.delete(link)
            session.delete(stored)

    @staticmethod
    def _remove_missing_media(directory: Path) -> None:
        directory = directory.expanduser().resolve()
        with session_scope() as session:
            for media in session.scalars(select(MediaFile).where(MediaFile.exists.is_(True))):
                path = Path(media.path)
                try:
                    in_directory = path.resolve().is_relative_to(directory)
                except OSError:
                    in_directory = False
                if in_directory and not path.is_file():
                    delete_media_record(session, media)
            refresh_primary_conflicts(session)
            refresh_episode_statuses(session)
