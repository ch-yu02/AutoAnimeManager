from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy import delete, select

from backend.app.config import BangumiConfig, get_settings
from backend.app.database.models.episode import Episode
from backend.app.database.models.subject import Subject, SubjectRelation
from backend.app.database.models.sync import SyncRun
from backend.app.database.session import session_scope
from backend.app.modules.bangumi.client import BangumiClient
from backend.app.modules.bangumi.errors import BangumiError
from backend.app.modules.bangumi.schemas import (
    BangumiCollection,
    BangumiEpisode,
    BangumiRelation,
    BangumiSubject,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncStart:
    task_id: str
    status: str
    reused: bool = False


class BangumiSyncService:
    def __init__(
        self,
        settings: BangumiConfig | None = None,
        *,
        settings_provider: Callable[[], BangumiConfig] | None = None,
        client_factory: Callable[[BangumiConfig], BangumiClient] | None = None,
    ) -> None:
        if settings_provider is not None:
            self.settings_provider = settings_provider
        elif settings is not None:
            self.settings_provider = lambda: settings
        else:
            self.settings_provider = lambda: get_settings().bangumi
        self.client_factory = client_factory or (lambda config: BangumiClient(config))
        self._active_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None

    @property
    def active_id(self) -> str | None:
        return self._active_id

    def _create_run(self, task_id: str) -> None:
        with session_scope() as session:
            session.add(
                SyncRun(
                    id=task_id,
                    status="RUNNING",
                    started_at=datetime.now(UTC),
                    processed_count=0,
                    succeeded_count=0,
                    failed_count=0,
                )
            )

    async def start(self) -> SyncStart:
        if self._active_id is not None:
            return SyncStart(self._active_id, "RUNNING", reused=True)
        task_id = str(uuid.uuid4())
        self._active_id = task_id
        self._create_run(task_id)
        self._active_task = asyncio.create_task(self._run(task_id))
        return SyncStart(task_id, "RUNNING")

    async def sync_now(self) -> SyncStart:
        if self._active_id is not None:
            return SyncStart(self._active_id, "RUNNING", reused=True)
        task_id = str(uuid.uuid4())
        self._active_id = task_id
        self._create_run(task_id)
        try:
            await self._run(task_id)
        finally:
            self._active_id = None
        return SyncStart(task_id, self.get_status(task_id)["status"])

    async def _run(self, task_id: str) -> None:
        try:
            settings = self.settings_provider()
            async with self.client_factory(settings) as client:
                collections = await client.get_user_collections(settings.username)
                await self._sync_collections(task_id, client, collections)
        except BangumiError as exc:
            self._finish_run(task_id, "FAILED", error_summary=f"{exc.code}: {exc.message}")
        except Exception:
            logger.exception("Bangumi sync failed")
            self._finish_run(task_id, "FAILED", error_summary="unexpected_error: 同步任务执行失败")
        finally:
            if self._active_id == task_id:
                self._active_id = None
            self._active_task = None

    async def _sync_collections(
        self, task_id: str, client: BangumiClient, collections: list[BangumiCollection]
    ) -> None:
        eligible = []
        remote_ids = {collection.subject_id for collection in collections}
        with session_scope() as session:
            existing_collections = list(
                session.scalars(select(Subject).where(Subject.collection_type.is_not(None)))
            )
            for subject in existing_collections:
                if subject.bangumi_subject_id not in remote_ids:
                    subject.collection_type = None
                    subject.collection_updated_at = datetime.now(UTC)

            for collection in collections:
                existing = session.scalar(
                    select(Subject).where(Subject.bangumi_subject_id == collection.subject_id)
                )
                existing_target = existing is not None and (
                    existing.collection_type is not None or existing.keep_forever
                )
                if collection.collection_type in {"WISH", "DOING"} or existing_target:
                    eligible.append(collection)

        errors: list[str] = []
        succeeded = 0
        self._update_progress(task_id, processed=0, succeeded=0, failed=0)
        for processed, collection in enumerate(eligible, start=1):
            try:
                subject = await client.get_subject(collection.subject_id)
                episodes = await client.get_episodes(collection.subject_id)
                relations = await client.get_subject_relations(collection.subject_id)
                episode_status = await client.get_episode_collection(collection.subject_id)
                self._persist_subject(subject, collection, episodes, relations, episode_status)
                succeeded += 1
            except BangumiError as exc:
                errors.append(f"subject {collection.subject_id}: {exc.code}")
            except Exception:
                logger.exception("Bangumi subject sync failed", extra={"subject_id": collection.subject_id})
                errors.append(f"subject {collection.subject_id}: unexpected_error")
            self._update_progress(task_id, processed=processed, succeeded=succeeded, failed=len(errors))

        if not eligible:
            self._finish_run(task_id, "SUCCESS", processed=0, succeeded=0, failed=0)
        elif errors and succeeded:
            self._finish_run(task_id, "PARTIAL_FAILURE", processed=len(eligible), succeeded=succeeded, failed=len(errors), error_summary="; ".join(errors))
        elif errors:
            self._finish_run(task_id, "FAILED", processed=len(eligible), succeeded=0, failed=len(errors), error_summary="; ".join(errors))
        else:
            self._finish_run(task_id, "SUCCESS", processed=len(eligible), succeeded=succeeded, failed=0)

    def _persist_subject(
        self,
        subject_data: BangumiSubject,
        collection: BangumiCollection,
        episodes: list[BangumiEpisode],
        relations: list[BangumiRelation],
        episode_status: dict[int, str],
    ) -> None:
        now = datetime.now(UTC)
        with session_scope() as session:
            subject = session.scalar(select(Subject).where(Subject.bangumi_subject_id == subject_data.id))
            if subject is None:
                subject = Subject(bangumi_subject_id=subject_data.id)
                session.add(subject)
                session.flush()
            subject.name = subject_data.name
            subject.name_cn = subject_data.name_cn
            subject.summary = subject_data.summary
            subject.url = subject_data.url
            subject.image_url = subject_data.image_url
            subject.subject_type = subject_data.subject_type
            subject.air_date = subject_data.air_date
            subject.air_status = subject_data.air_status
            subject.platform = subject_data.platform
            subject.total_main_episodes = subject_data.total_main_episodes
            subject.collection_type = collection.collection_type
            subject.collection_updated_at = collection.updated_at
            subject.last_synced_at = now

            for episode_data in episodes:
                episode = session.scalar(
                    select(Episode).where(Episode.bangumi_episode_id == episode_data.id)
                )
                if episode is None:
                    episode = Episode(bangumi_episode_id=episode_data.id, subject_id=subject.id)
                    session.add(episode)
                episode.subject_id = subject.id
                episode.episode_type = episode_data.episode_type
                episode.sort_number = episode_data.sort_number
                episode.display_number = episode_data.display_number
                episode.name = episode_data.name
                episode.name_cn = episode_data.name_cn
                episode.air_date = episode_data.air_date
                episode.bangumi_watch_status = episode_status.get(episode_data.id)
                episode.last_synced_at = now

            session.execute(delete(SubjectRelation).where(SubjectRelation.subject_id == subject.id))
            for relation in relations:
                related = session.scalar(
                    select(Subject).where(Subject.bangumi_subject_id == relation.related_subject_id)
                )
                if related is None:
                    related = Subject(
                        bangumi_subject_id=relation.related_subject_id,
                        name=relation.related_name,
                        name_cn=relation.related_name,
                        collection_type=None,
                        last_synced_at=now,
                    )
                    session.add(related)
                    session.flush()
                session.add(
                    SubjectRelation(
                        subject_id=subject.id,
                        related_subject_id=related.id,
                        relation_type=relation.relation_type,
                    )
                )

    def _update_progress(self, task_id: str, *, processed: int, succeeded: int, failed: int) -> None:
        with session_scope() as session:
            run = session.get(SyncRun, task_id)
            if run is not None:
                run.processed_count = processed
                run.succeeded_count = succeeded
                run.failed_count = failed

    def _finish_run(
        self,
        task_id: str,
        status: str,
        *,
        processed: int | None = None,
        succeeded: int | None = None,
        failed: int | None = None,
        error_summary: str | None = None,
    ) -> None:
        with session_scope() as session:
            run = session.get(SyncRun, task_id)
            if run is None:
                return
            run.status = status
            run.finished_at = datetime.now(UTC)
            if processed is not None:
                run.processed_count = processed
            if succeeded is not None:
                run.succeeded_count = succeeded
            if failed is not None:
                run.failed_count = failed
            run.error_summary = error_summary

    def get_status(self, task_id: str | None = None) -> dict[str, object]:
        with session_scope() as session:
            run = session.get(SyncRun, task_id) if task_id else session.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()))
            if run is None:
                return {"status": "NEVER_RUN", "task_id": None, "processed_count": 0, "succeeded_count": 0, "failed_count": 0}
            return {
                "task_id": run.id,
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "processed_count": run.processed_count,
                "succeeded_count": run.succeeded_count,
                "failed_count": run.failed_count,
                "error_summary": run.error_summary,
            }
