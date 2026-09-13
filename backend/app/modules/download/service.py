from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import json
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
    def __init__(
        self,
        adapter=None,
        importer: FileImporter | None = None,
        *,
        reconcile_timeout_seconds: float | None = None,
        sync_concurrency: int = 6,
    ) -> None:
        self.adapter = adapter or QBittorrentAdapter(lambda: get_settings().qbittorrent)
        self.importer = importer or FileImporter(get_settings)
        self._job_locks: dict[str, asyncio.Lock] = {}
        self._reconcile_timeout_seconds = reconcile_timeout_seconds
        self._sync_concurrency = max(1, sync_concurrency)
        self._import_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autoanime-import")
        self._imports: dict[str, Future[object]] = {}

    async def stop(self) -> None:
        self._import_executor.shutdown(wait=True, cancel_futures=False)
        await self.adapter.close()

    async def create(
        self,
        episode_id: int,
        magnet: str,
        *,
        replacement_media_ids: list[int] | None = None,
    ) -> dict[str, object]:
        magnet_uri, torrent_hash = normalize_magnet(magnet)
        requested_replacements = set(replacement_media_ids or [])
        try:
            with session_scope() as session:
                episode = session.get(Episode, episode_id)
                if episode is None:
                    raise EpisodeNotDownloadable("Episode 不存在")
                subject = session.get(Subject, episode.subject_id)
                if subject is None:
                    raise EpisodeNotDownloadable("Episode 对应条目不存在")
                ready_files = list(session.scalars(
                    select(MediaFile)
                    .join(EpisodeFile, EpisodeFile.media_file_id == MediaFile.id)
                    .where(
                        EpisodeFile.episode_id == episode.id,
                        MediaFile.exists.is_(True),
                        MediaFile.ignored.is_(False),
                    )
                ))
                ready_ids = {media.id for media in ready_files}
                if ready_files and not requested_replacements:
                    raise EpisodeNotDownloadable("Episode 已有可播放的本地文件")
                if requested_replacements and ready_ids != requested_replacements:
                    raise EpisodeNotDownloadable("替换目标与 Episode 当前媒体不一致")
                if requested_replacements:
                    shared = session.scalar(
                        select(EpisodeFile.id).where(
                            EpisodeFile.media_file_id.in_(requested_replacements),
                            EpisodeFile.episode_id != episode.id,
                        ).limit(1)
                    )
                    if shared is not None:
                        raise EpisodeNotDownloadable("多 Episode 共用的媒体不能自动替换")
                duplicate = session.scalar(
                    select(DownloadJob).where(
                        (DownloadJob.magnet_hash == torrent_hash) | (DownloadJob.torrent_hash == torrent_hash)
                    )
                )
                if duplicate is not None:
                    raise DuplicateDownload("相同 magnet 已提交", duplicate.id)
                episode_jobs = list(session.scalars(
                    select(DownloadJob)
                    .join(DownloadJobEpisode, DownloadJobEpisode.job_id == DownloadJob.id)
                    .where(DownloadJobEpisode.episode_id == episode.id)
                ))
                if any(job.state in ACTIVE_STATES for job in episode_jobs):
                    active = next(job for job in episode_jobs if job.state in ACTIVE_STATES)
                    raise DuplicateDownload("该 Episode 已有下载任务", active.id)
                if episode_jobs and not requested_replacements:
                    raise DuplicateDownload("该 Episode 已有下载任务", episode_jobs[0].id)
                replaced_job_ids = [job.id for job in episode_jobs]
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
                    replacement_media_ids_json=json.dumps(sorted(requested_replacements)),
                    replaces_job_ids_json=json.dumps(replaced_job_ids),
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
            return self._views(session, jobs)

    def has_active_jobs(self) -> bool:
        with session_scope() as session:
            return session.scalar(
                select(DownloadJob.id).where(DownloadJob.state.in_(ACTIVE_STATES)).limit(1)
            ) is not None

    def get(self, job_id: str) -> dict[str, object]:
        with session_scope() as session:
            job = session.get(DownloadJob, job_id)
            if job is None:
                raise DownloadNotFound("下载任务不存在")
            return self._view(session, job)

    @staticmethod
    def _view(session, job: DownloadJob) -> dict[str, object]:
        return DownloadService._views(session, [job])[0]

    @staticmethod
    def _views(session, jobs: list[DownloadJob]) -> list[dict[str, object]]:
        if not jobs:
            return []
        subject_ids = {job.subject_id for job in jobs}
        subjects = {
            subject.id: subject
            for subject in session.scalars(select(Subject).where(Subject.id.in_(subject_ids)))
        }
        episodes_by_job: dict[str, list[Episode]] = {job.id: [] for job in jobs}
        episode_ids_by_job: dict[str, set[int]] = {job.id: set() for job in jobs}
        replaceable_job_ids: set[str] = set()
        for job_id, episode, media_id, reasons in session.execute(
            select(DownloadJobEpisode.job_id, Episode, MediaFile.id, EpisodeFile.reasons)
            .join(Episode, DownloadJobEpisode.episode_id == Episode.id)
            .outerjoin(EpisodeFile, EpisodeFile.episode_id == Episode.id)
            .outerjoin(
                MediaFile,
                (MediaFile.id == EpisodeFile.media_file_id)
                & MediaFile.exists.is_(True)
                & MediaFile.ignored.is_(False),
            )
            .where(DownloadJobEpisode.job_id.in_(episodes_by_job))
            .order_by(DownloadJobEpisode.job_id, Episode.sort_number, Episode.id)
        ):
            if episode.id not in episode_ids_by_job[job_id]:
                episodes_by_job[job_id].append(episode)
                episode_ids_by_job[job_id].add(episode.id)
            if media_id is not None and job_id in (reasons or ""):
                replaceable_job_ids.add(job_id)

        result = []
        for job in jobs:
            subject = subjects.get(job.subject_id)
            episodes = episodes_by_job[job.id]
            result.append({
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
                "can_replace_source": job.state == "IMPORTED" and job.id in replaceable_job_ids,
                "error": job.error,
                "save_path": job.save_path,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "completed_at": job.completed_at,
                "imported_at": job.imported_at,
            })
        return result

    async def reconcile_all(self) -> dict[str, int]:
        with session_scope() as session:
            ids = list(session.scalars(select(DownloadJob.id).where(DownloadJob.state.in_(ACTIVE_STATES))))
        semaphore = asyncio.Semaphore(self._sync_concurrency)

        async def reconcile_one(job_id: str) -> bool:
            async with semaphore:
                try:
                    async with asyncio.timeout(self._reconcile_timeout()):
                        return await self.reconcile(job_id)
                except TimeoutError:
                    logger.warning("下载任务 %s 同步超时", job_id)
                    with session_scope() as session:
                        job = session.get(DownloadJob, job_id)
                        if job is not None and job.state not in TERMINAL_STATES:
                            job.state = "STALLED"
                            job.error = "qBittorrent 同步超时，稍后自动重试"
                    return False

        results = await asyncio.gather(*(reconcile_one(job_id) for job_id in ids))
        failed = sum(not result for result in results)
        return {"processed": len(ids), "failed": failed}

    async def reconcile(self, job_id: str) -> bool:
        async with self._job_lock(job_id):
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
                return True
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
                    return True

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
                    return True
                progress = min(1.0, max(0.0, float(info.get("progress", 0) or 0)))
                qb_state = str(info.get("state", ""))
                completed = progress >= 0.999999 and qb_state not in {"metaDL", "checkingDL", "checkingResumeData"}
                with session_scope() as session:
                    job = session.get(DownloadJob, job_id)
                    if job is None:
                        return True
                    job.progress = progress
                    job.error = None
                    if qb_state.lower().startswith("error") or qb_state == "missingFiles":
                        job.state = "FAILED"
                        job.error = f"qBittorrent 任务异常：{qb_state}"
                        return True
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
                return True
            except (QBittorrentError, OSError) as exc:
                logger.warning("下载任务 %s 暂停同步：%s", job_id, exc)
                with session_scope() as session:
                    job = session.get(DownloadJob, job_id)
                    if job and job.state not in TERMINAL_STATES:
                        job.state = "STALLED"
                        job.error = str(exc)[:2000]
                return False

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
        loop = asyncio.get_running_loop()

        def imported(done: Future[object]) -> None:
            self._imports.pop(job_id, None)
            try:
                result = done.result()
            except Exception:
                return
            hashes = getattr(result, "replaced_torrent_hashes", ()) if result else ()
            if hashes and not loop.is_closed():
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._remove_replaced_tasks(tuple(hashes)))
                )

        future.add_done_callback(imported)

    def _import_sync(self, job_id: str, files: list[dict[str, object]]):
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
            return result
        except (ImportFailure, OSError) as exc:
            with session_scope() as session:
                job = session.get(DownloadJob, job_id)
                if job:
                    job.state = "FAILED"
                    job.error = str(exc)[:2000]
            return None

    async def _remove_replaced_tasks(self, torrent_hashes: tuple[str, ...]) -> None:
        for torrent_hash in torrent_hashes:
            try:
                await self.adapter.delete(torrent_hash, delete_files=False)
            except QBittorrentError as exc:
                logger.warning("旧 ANi qBittorrent 任务清理失败：%s", exc)

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
        async with self._job_lock(job_id):
            job = self.get(job_id)
            running = self._imports.get(job_id)
            if running is not None and not running.done():
                raise DownloadDeleteNotAllowed("任务正在导入，请等待导入结束")
            await self.adapter.delete(str(job["torrent_hash"]), delete_files=delete_files)
            if delete_files:
                self._remove_missing_media(Path(str(job["save_path"])))
            self._delete_record(job_id)
            return {"id": job_id, "deleted": True, "delete_files": delete_files}

    def _job_lock(self, job_id: str) -> asyncio.Lock:
        lock = self._job_locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            self._job_locks[job_id] = lock
        return lock

    def _reconcile_timeout(self) -> float:
        if self._reconcile_timeout_seconds is not None:
            return self._reconcile_timeout_seconds
        return max(5.0, get_settings().qbittorrent.timeout * 2 + 5)

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
