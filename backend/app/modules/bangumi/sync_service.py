from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import delete, exists, select

from backend.app.config import BangumiConfig, get_settings
from backend.app.database.models.episode import Episode
from backend.app.database.models.media import MediaFile
from backend.app.database.models.playback import PlaybackState
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
from backend.app.modules.library.parser import normalize_title


logger = logging.getLogger(__name__)
SYNC_MODES = {"FULL", "QUICK"}
COLLECTION_TYPES = {"WISH", "DOING", "COLLECTED", "ON_HOLD", "DROPPED"}


@dataclass(frozen=True)
class SyncStart:
    task_id: str
    status: str
    reused: bool = False


@dataclass(frozen=True)
class SubjectSyncPlan:
    collection: BangumiCollection
    fetch_metadata: bool
    fetch_episodes: bool
    fetch_relations: bool
    fetch_episode_status: bool

    @property
    def skipped(self) -> bool:
        return not any((
            self.fetch_metadata,
            self.fetch_episodes,
            self.fetch_relations,
            self.fetch_episode_status,
        ))


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

    @staticmethod
    def _mode(mode: str) -> str:
        normalized = mode.upper()
        if normalized not in SYNC_MODES:
            raise ValueError(f"未知 Bangumi 同步模式：{mode}")
        return normalized

    def _create_run(self, task_id: str, mode: str) -> None:
        with session_scope() as session:
            session.add(SyncRun(
                id=task_id,
                mode=mode,
                status="RUNNING",
                started_at=datetime.now(UTC),
                processed_count=0,
                succeeded_count=0,
                failed_count=0,
                skipped_count=0,
                request_count=0,
            ))

    async def start(self, mode: str = "FULL") -> SyncStart:
        mode = self._mode(mode)
        if self._active_id is not None:
            return SyncStart(self._active_id, "RUNNING", reused=True)
        task_id = str(uuid.uuid4())
        self._active_id = task_id
        self._create_run(task_id, mode)
        self._active_task = asyncio.create_task(self._run(task_id, mode))
        return SyncStart(task_id, "RUNNING")

    async def sync_now(self, mode: str = "FULL") -> SyncStart:
        mode = self._mode(mode)
        if self._active_id is not None:
            task_id = self._active_id
            task = self._active_task
            if task is not None:
                await task
            return SyncStart(task_id, self.get_status(task_id)["status"], reused=True)
        task_id = str(uuid.uuid4())
        self._active_id = task_id
        self._create_run(task_id, mode)
        try:
            await self._run(task_id, mode)
        finally:
            self._active_id = None
        return SyncStart(task_id, self.get_status(task_id)["status"])

    async def _run(self, task_id: str, mode: str) -> None:
        try:
            settings = self.settings_provider()
            async with self.client_factory(settings) as client:
                collections = await client.get_user_collections(settings.username)
                await self._sync_collections(task_id, client, collections, mode, settings)
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
        self,
        task_id: str,
        client: BangumiClient,
        collections: list[BangumiCollection],
        mode: str = "FULL",
        settings: BangumiConfig | None = None,
    ) -> None:
        settings = settings or self.settings_provider()
        plans = self._build_plans(collections, mode, settings)
        semaphore = asyncio.Semaphore(settings.sync_concurrency)
        request_count = 0

        async def request(factory: Callable[[], Awaitable[object]]) -> object:
            nonlocal request_count
            async with semaphore:
                request_count += 1
                return await factory()

        async def sync_subject(plan: SubjectSyncPlan) -> str | None:
            subject_id = plan.collection.subject_id
            operations: list[tuple[str, Callable[[], Awaitable[object]]]] = []
            if plan.fetch_metadata:
                operations.append(("metadata", lambda: client.get_subject(subject_id)))
            if plan.fetch_episodes:
                operations.append(("episodes", lambda: client.get_episodes(subject_id)))
            if plan.fetch_relations:
                operations.append(("relations", lambda: client.get_subject_relations(subject_id)))
            if plan.fetch_episode_status:
                operations.append(("episode_status", lambda: client.get_episode_collection(subject_id)))
            try:
                values = await asyncio.gather(*(request(factory) for _, factory in operations))
                fetched = dict(zip((name for name, _ in operations), values, strict=True))
                self._persist_subject(
                    fetched.get("metadata"),
                    subject_id,
                    plan.collection,
                    fetched.get("episodes"),
                    fetched.get("relations"),
                    fetched.get("episode_status"),
                )
                return None
            except BangumiError as exc:
                return f"subject {subject_id}: {exc.code}"
            except Exception:
                logger.exception("Bangumi subject sync failed", extra={"subject_id": subject_id})
                return f"subject {subject_id}: unexpected_error"

        skipped = sum(plan.skipped for plan in plans)
        processed = succeeded = skipped
        errors: list[str] = []
        self._update_progress(
            task_id,
            processed=processed,
            succeeded=succeeded,
            failed=0,
            skipped=skipped,
            requests=request_count,
        )
        tasks = [asyncio.create_task(sync_subject(plan)) for plan in plans if not plan.skipped]
        for completed in asyncio.as_completed(tasks):
            error = await completed
            processed += 1
            if error is None:
                succeeded += 1
            else:
                errors.append(error)
            self._update_progress(
                task_id,
                processed=processed,
                succeeded=succeeded,
                failed=len(errors),
                skipped=skipped,
                requests=request_count,
            )

        if mode == "FULL":
            await self._sync_locally_relevant_relations(client, request)

        status = "SUCCESS"
        if errors and succeeded:
            status = "PARTIAL_FAILURE"
        elif errors:
            status = "FAILED"
        self._finish_run(
            task_id,
            status,
            processed=len(plans),
            succeeded=succeeded,
            failed=len(errors),
            skipped=skipped,
            requests=request_count,
            error_summary="; ".join(errors) or None,
        )

    def _build_plans(
        self,
        collections: list[BangumiCollection],
        mode: str,
        settings: BangumiConfig,
    ) -> list[SubjectSyncPlan]:
        now = datetime.now(UTC)
        remote = {collection.subject_id: collection for collection in collections}
        plans: list[SubjectSyncPlan] = []
        with session_scope() as session:
            existing_subjects = list(session.scalars(
                select(Subject).where(Subject.collection_type.is_not(None))
            ))
            by_bangumi_id = {subject.bangumi_subject_id: subject for subject in existing_subjects}
            for subject in existing_subjects:
                collection = remote.get(subject.bangumi_subject_id)
                if collection is None:
                    subject.collection_type = None
                    subject.collection_updated_at = now
                    continue
                previous_type = subject.collection_type
                previous_updated = subject.collection_updated_at
                collection_changed = previous_type != collection.collection_type or self._newer(
                    collection.updated_at, previous_updated
                )
                subject.collection_type = collection.collection_type
                if collection.updated_at is not None:
                    subject.collection_updated_at = collection.updated_at
                if mode == "QUICK" and collection.collection_type != "DOING":
                    continue
                if collection.collection_type not in COLLECTION_TYPES and not subject.keep_forever:
                    continue
                metadata_due = self._expired(
                    subject.metadata_synced_at, settings.metadata_refresh_hours, now
                )
                relations_due = self._expired(
                    subject.relations_synced_at, settings.relations_refresh_hours, now
                )
                has_episodes = session.scalar(select(exists().where(Episode.subject_id == subject.id)))
                refresh_episodes = (
                    mode == "QUICK"
                    or collection.collection_type == "DOING"
                    or collection_changed
                    or not has_episodes
                )
                plans.append(SubjectSyncPlan(
                    collection=collection,
                    fetch_metadata=metadata_due,
                    fetch_episodes=refresh_episodes,
                    fetch_relations=relations_due,
                    fetch_episode_status=refresh_episodes,
                ))

            for collection in collections:
                if collection.subject_id in by_bangumi_id:
                    continue
                if mode == "QUICK" and collection.collection_type != "DOING":
                    continue
                if collection.collection_type not in COLLECTION_TYPES:
                    continue
                plans.append(SubjectSyncPlan(collection, True, True, True, True))
        return plans

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def _newer(cls, remote: datetime | None, local: datetime | None) -> bool:
        if remote is None:
            return False
        return local is None or cls._aware(remote) > cls._aware(local)

    @classmethod
    def _expired(cls, value: datetime | None, hours: float, now: datetime) -> bool:
        return value is None or cls._aware(value) + timedelta(hours=hours) <= now

    def _persist_subject(
        self,
        subject_data: object | None,
        bangumi_subject_id: int,
        collection: BangumiCollection | None,
        episode_data: object | None,
        relation_data: object | None,
        episode_status_data: object | None,
    ) -> None:
        subject_value = subject_data if isinstance(subject_data, BangumiSubject) else None
        episodes = episode_data if isinstance(episode_data, list) else None
        relations = relation_data if isinstance(relation_data, list) else None
        episode_status = episode_status_data if isinstance(episode_status_data, dict) else None
        now = datetime.now(UTC)
        with session_scope() as session:
            subject = session.scalar(
                select(Subject).where(Subject.bangumi_subject_id == bangumi_subject_id)
            )
            if subject is None:
                if subject_value is None:
                    raise RuntimeError("新 Bangumi 条目缺少元数据")
                subject = Subject(bangumi_subject_id=bangumi_subject_id)
                session.add(subject)
                session.flush()
            if subject_value is not None:
                subject.name = subject_value.name
                subject.name_cn = subject_value.name_cn
                subject.aliases = json.dumps(subject_value.aliases, ensure_ascii=False)
                subject.summary = subject_value.summary
                subject.url = subject_value.url
                subject.image_url = subject_value.image_url
                subject.subject_type = subject_value.subject_type
                subject.air_date = subject_value.air_date
                subject.air_status = subject_value.air_status
                subject.platform = subject_value.platform
                subject.total_main_episodes = subject_value.total_main_episodes
                subject.metadata_synced_at = now
            if collection is not None:
                subject.collection_type = collection.collection_type
                if collection.updated_at is not None:
                    subject.collection_updated_at = collection.updated_at

            if episodes is not None:
                for item in episodes:
                    if not isinstance(item, BangumiEpisode):
                        continue
                    episode = session.scalar(
                        select(Episode).where(Episode.bangumi_episode_id == item.id)
                    )
                    if episode is None:
                        episode = Episode(bangumi_episode_id=item.id, subject_id=subject.id)
                        session.add(episode)
                        session.flush()
                    episode.subject_id = subject.id
                    episode.episode_type = item.episode_type
                    episode.sort_number = item.sort_number
                    episode.display_number = item.display_number
                    episode.name = item.name
                    episode.name_cn = item.name_cn
                    episode.air_date = item.air_date
                    if episode_status is not None:
                        remote_status = episode_status.get(item.id, "NONE")
                        episode.bangumi_watch_status = remote_status
                        playback = session.scalar(
                            select(PlaybackState).where(PlaybackState.episode_id == episode.id)
                        )
                        if remote_status == "WATCHED":
                            episode.watched = True
                            if playback is None:
                                playback = PlaybackState(episode_id=episode.id)
                                session.add(playback)
                            if not playback.watched:
                                playback.watched = True
                                playback.watched_source = "BANGUMI"
                                playback.completed_at = playback.completed_at or now
                        elif playback is not None and playback.watched_source == "BANGUMI":
                            episode.watched = False
                            playback.watched = False
                            playback.completed_at = None
                    episode.last_synced_at = now

            if relations is not None:
                session.execute(delete(SubjectRelation).where(SubjectRelation.subject_id == subject.id))
                for relation in relations:
                    if not isinstance(relation, BangumiRelation):
                        continue
                    related = session.scalar(select(Subject).where(
                        Subject.bangumi_subject_id == relation.related_subject_id
                    ))
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
                    session.add(SubjectRelation(
                        subject_id=subject.id,
                        related_subject_id=related.id,
                        relation_type=relation.relation_type,
                    ))
                subject.relations_synced_at = now
            subject.last_synced_at = now

    async def _sync_locally_relevant_relations(
        self,
        client: BangumiClient,
        request: Callable[[Callable[[], Awaitable[object]]], Awaitable[object]] | None = None,
    ) -> None:
        """Hydrate related anime only when an ambiguous local filename provides title evidence."""
        relation_types = {"续集", "前传", "番外篇", "相同世界观", "不同演绎", "总集篇", "衍生"}
        with session_scope() as session:
            pending_titles = []
            for media in session.scalars(select(MediaFile).where(
                MediaFile.review_reason == "AMBIGUOUS_SUBJECT"
            )):
                try:
                    parsed = json.loads(media.parse_result)
                except (json.JSONDecodeError, TypeError):
                    continue
                title = parsed.get("normalized_title") if isinstance(parsed, dict) else None
                if isinstance(title, str) and title:
                    pending_titles.append(title)
            if not pending_titles:
                return

            related_ids: set[int] = set()
            for subject in session.scalars(select(Subject).where(Subject.collection_type.is_not(None))):
                try:
                    aliases = json.loads(subject.aliases)
                except (json.JSONDecodeError, TypeError):
                    aliases = []
                titles = [subject.name, subject.name_cn, *(aliases if isinstance(aliases, list) else [])]
                normalized = [normalize_title(title) for title in titles if isinstance(title, str) and title]
                if not any(
                    len(title) >= 8 and title in pending
                    for title in normalized for pending in pending_titles
                ):
                    continue
                for relation in session.scalars(select(SubjectRelation).where(
                    SubjectRelation.subject_id == subject.id
                )):
                    if relation.relation_type in relation_types:
                        related = session.get(Subject, relation.related_subject_id)
                        if related is not None and related.collection_type is None:
                            related_ids.add(related.bangumi_subject_id)

        async def call(factory: Callable[[], Awaitable[object]]) -> object:
            return await request(factory) if request is not None else await factory()

        for related_id in related_ids:
            try:
                subject_data = await call(lambda: client.get_subject(related_id))
                if not isinstance(subject_data, BangumiSubject):
                    continue
                titles = [subject_data.name, subject_data.name_cn, *subject_data.aliases]
                normalized = [normalize_title(title) for title in titles if title]
                if not any(
                    len(title) >= 8 and (title == pending or title in pending or pending in title)
                    for title in normalized for pending in pending_titles
                ):
                    continue
                episodes, relations = await asyncio.gather(
                    call(lambda: client.get_episodes(related_id)),
                    call(lambda: client.get_subject_relations(related_id)),
                )
                self._persist_subject(
                    subject_data, related_id, None, episodes, relations, None
                )
                with session_scope() as session:
                    related = session.scalar(select(Subject).where(
                        Subject.bangumi_subject_id == related_id
                    ))
                    if related is not None:
                        related.keep_forever = True
            except BangumiError:
                logger.warning(
                    "Bangumi related subject hydration failed", extra={"subject_id": related_id}
                )

    def _update_progress(
        self,
        task_id: str,
        *,
        processed: int,
        succeeded: int,
        failed: int,
        skipped: int,
        requests: int,
    ) -> None:
        with session_scope() as session:
            run = session.get(SyncRun, task_id)
            if run is not None:
                run.processed_count = processed
                run.succeeded_count = succeeded
                run.failed_count = failed
                run.skipped_count = skipped
                run.request_count = requests

    def _finish_run(
        self,
        task_id: str,
        status: str,
        *,
        processed: int | None = None,
        succeeded: int | None = None,
        failed: int | None = None,
        skipped: int | None = None,
        requests: int | None = None,
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
            if skipped is not None:
                run.skipped_count = skipped
            if requests is not None:
                run.request_count = requests
            run.error_summary = error_summary

    def get_status(self, task_id: str | None = None) -> dict[str, object]:
        with session_scope() as session:
            run = session.get(SyncRun, task_id) if task_id else session.scalar(
                select(SyncRun).order_by(SyncRun.started_at.desc())
            )
            if run is None:
                return {
                    "status": "NEVER_RUN", "task_id": None, "mode": None,
                    "processed_count": 0, "succeeded_count": 0, "failed_count": 0,
                    "skipped_count": 0, "request_count": 0, "duration_seconds": None,
                }
            finished = run.finished_at or datetime.now(UTC)
            duration = (self._aware(finished) - self._aware(run.started_at)).total_seconds()
            return {
                "task_id": run.id,
                "mode": run.mode,
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "duration_seconds": max(0.0, duration),
                "processed_count": run.processed_count,
                "succeeded_count": run.succeeded_count,
                "failed_count": run.failed_count,
                "skipped_count": run.skipped_count,
                "request_count": run.request_count,
                "error_summary": run.error_summary,
            }
