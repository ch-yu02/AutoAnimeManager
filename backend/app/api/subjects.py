from __future__ import annotations

import json
from datetime import date, datetime
from difflib import SequenceMatcher

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select

from backend.app.database.models.episode import Episode
from backend.app.database.models.media import EpisodeFile, MediaFile
from backend.app.database.models.playback import PlaybackState
from backend.app.database.models.subject import Subject, SubjectRelation
from backend.app.database.models.sync import SyncRun
from backend.app.database.session import session_scope
from backend.app.modules.bangumi.errors import BangumiError
from backend.app.modules.playback.writeback import writeback_subject_collection
from backend.app.modules.library.parser import normalize_title

router = APIRouter(prefix="/subjects", tags=["subjects"])


class SubjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bangumi_subject_id: int
    name: str
    name_cn: str
    display_name: str
    image_url: str
    subject_type: int | None
    air_date: date | None
    air_status: str
    platform: str
    collection_type: str | None
    collection_updated_at: datetime | None
    total_main_episodes: int | None
    keep_forever: bool
    episode_count: int
    main_episode_count: int
    last_synced_at: datetime | None


class RelationView(BaseModel):
    subject_id: int
    bangumi_subject_id: int
    name: str
    name_cn: str
    relation_type: str


class SubjectDetail(SubjectListItem):
    summary: str
    url: str
    relations: list[RelationView]
    recent_sync: dict[str, object] | None = None


class EpisodeView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bangumi_episode_id: int
    subject_id: int
    episode_type: str
    sort_number: float | None
    display_number: str
    name: str
    name_cn: str
    air_date: date | None
    bangumi_watch_status: str | None
    watched: bool
    ignored: bool
    local_status: str
    media_files: list[dict[str, object]] = Field(default_factory=list)
    playback: dict[str, object] | None = None
    last_synced_at: datetime | None


class CollectionUpdate(BaseModel):
    collection_type: str


class SubjectSearchResult(BaseModel):
    id: int
    bangumi_subject_id: int
    display_name: str
    matched_title: str
    display_label: str
    collection_type: str | None
    air_date: date | None


def _display_name(subject: Subject) -> str:
    return subject.name_cn or subject.name or f"Bangumi #{subject.bangumi_subject_id}"


def _list_item(
    session,
    subject: Subject,
    episode_count: int | None = None,
    main_episode_count: int | None = None,
) -> SubjectListItem:
    if episode_count is None or main_episode_count is None:
        episode_count, main_episode_count = session.execute(
            select(
                func.count(Episode.id),
                func.count(Episode.id).filter(Episode.episode_type == "MAIN"),
            ).where(Episode.subject_id == subject.id)
        ).one()
    return SubjectListItem(
        id=subject.id,
        bangumi_subject_id=subject.bangumi_subject_id,
        name=subject.name,
        name_cn=subject.name_cn,
        display_name=_display_name(subject),
        image_url=subject.image_url,
        subject_type=subject.subject_type,
        air_date=subject.air_date,
        air_status=subject.air_status,
        platform=subject.platform,
        collection_type=subject.collection_type,
        collection_updated_at=subject.collection_updated_at,
        total_main_episodes=subject.total_main_episodes,
        keep_forever=subject.keep_forever,
        episode_count=episode_count,
        main_episode_count=main_episode_count,
        last_synced_at=subject.last_synced_at,
    )


@router.get("", response_model=list[SubjectListItem])
async def list_subjects(
    collection_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    collection_status: str | None = Query(default=None),
    local_only: bool = Query(default=False),
) -> list[SubjectListItem]:
    selected_type = collection_type or status_filter or collection_status
    with session_scope() as session:
        episode_counts = (
            select(
                Episode.subject_id.label("subject_id"),
                func.count(Episode.id).label("episode_count"),
                func.sum(case((Episode.episode_type == "MAIN", 1), else_=0)).label("main_episode_count"),
            )
            .group_by(Episode.subject_id)
            .subquery()
        )
        query = (
            select(
                Subject,
                func.coalesce(episode_counts.c.episode_count, 0),
                func.coalesce(episode_counts.c.main_episode_count, 0),
            )
            .outerjoin(episode_counts, episode_counts.c.subject_id == Subject.id)
            .where(Subject.collection_type.is_not(None))
            .order_by(Subject.updated_at.desc())
        )
        if selected_type:
            query = query.where(Subject.collection_type == selected_type.upper())
        if local_only:
            local_subject_ids = (
                select(Episode.subject_id)
                .join(EpisodeFile, EpisodeFile.episode_id == Episode.id)
                .join(MediaFile, MediaFile.id == EpisodeFile.media_file_id)
                .where(
                    MediaFile.exists.is_(True),
                    MediaFile.ignored.is_(False),
                )
                .distinct()
            )
            query = query.where(Subject.id.in_(local_subject_ids))
        rows = session.execute(query)
        return [
            _list_item(session, subject, int(episode_count), int(main_episode_count))
            for subject, episode_count, main_episode_count in rows
        ]


@router.get("/search", response_model=list[SubjectSearchResult])
async def search_subjects(
    query: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[SubjectSearchResult]:
    needle = normalize_title(query)
    if not needle:
        return []
    needle_tokens = needle.split()
    matches: list[tuple[float, bool, Subject, str]] = []
    with session_scope() as session:
        useful_subjects = select(Subject).where(or_(
            Subject.subject_type == 2,
            Subject.collection_type.is_not(None),
        ))
        for subject in session.scalars(useful_subjects):
            try:
                aliases = json.loads(subject.aliases)
            except (json.JSONDecodeError, TypeError):
                aliases = []
            titles = [subject.name_cn, subject.name]
            if isinstance(aliases, list):
                titles.extend(value for value in aliases if isinstance(value, str))
            best_score = 0.0
            best_title = ""
            for title in titles:
                normalized = normalize_title(title)
                if not normalized:
                    continue
                if normalized == needle:
                    score = 1.0
                elif normalized.startswith(needle):
                    score = 0.95
                elif needle in normalized:
                    score = 0.90
                elif all(token in normalized for token in needle_tokens):
                    score = 0.82
                else:
                    ratio = SequenceMatcher(None, needle, normalized).ratio()
                    score = ratio if ratio >= 0.72 else 0.0
                if score > best_score:
                    best_score = score
                    best_title = title
            if best_score:
                matches.append((best_score, subject.collection_type is not None, subject, best_title))
        matches.sort(key=lambda item: (-item[0], -int(item[1]), _display_name(item[2])))
        results = []
        for _, _, subject, matched_title in matches[:limit]:
            display_name = _display_name(subject)
            matched_suffix = f" · 命中：{matched_title}" if matched_title != display_name else ""
            date_suffix = f" · {subject.air_date.isoformat()}" if subject.air_date else ""
            results.append(SubjectSearchResult(
                id=subject.id,
                bangumi_subject_id=subject.bangumi_subject_id,
                display_name=display_name,
                matched_title=matched_title,
                display_label=(
                    f"{display_name}{matched_suffix}{date_suffix} · BGM#{subject.bangumi_subject_id}"
                ),
                collection_type=subject.collection_type,
                air_date=subject.air_date,
            ))
        return results


@router.get("/{subject_id}", response_model=SubjectDetail)
async def get_subject(subject_id: int) -> SubjectDetail:
    with session_scope() as session:
        subject = session.get(Subject, subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail={"code": "subject_not_found", "message": "条目不存在"})
        item = _list_item(session, subject)
        relations = []
        rows = session.execute(
            select(SubjectRelation, Subject)
            .join(Subject, Subject.id == SubjectRelation.related_subject_id)
            .where(SubjectRelation.subject_id == subject.id)
        )

        for relation, related in rows:
            relations.append(
                RelationView(
                    subject_id=related.id,
                    bangumi_subject_id=related.bangumi_subject_id,
                    name=related.name,
                    name_cn=related.name_cn,
                    relation_type=relation.relation_type,
                )
            )
        recent = session.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()))
        return SubjectDetail(
            **item.model_dump(),
            summary=subject.summary,
            url=subject.url,
            relations=relations,
            recent_sync=(
                {
                    "task_id": recent.id,
                    "status": recent.status,
                    "started_at": recent.started_at,
                    "finished_at": recent.finished_at,
                }
                if recent is not None
                else None
            ),
        )


@router.patch("/{subject_id}/collection")
async def update_subject_collection(
    subject_id: int, payload: CollectionUpdate
) -> dict[str, object]:
    try:
        return await writeback_subject_collection(subject_id, payload.collection_type)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "subject_not_found", "message": "条目不存在"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_collection_type", "message": "收藏状态无效"},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "bangumi_not_configured", "message": "请先配置 Bangumi Token"},
        ) from exc
    except BangumiError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("/{subject_id}/episodes", response_model=list[EpisodeView])
async def list_episodes(subject_id: int) -> list[EpisodeView]:
    with session_scope() as session:
        if session.get(Subject, subject_id) is None:
            raise HTTPException(status_code=404, detail={"code": "subject_not_found", "message": "条目不存在"})
        episodes = list(
            session.scalars(
                select(Episode)
                .where(Episode.subject_id == subject_id)
                .order_by(Episode.episode_type != "MAIN", Episode.sort_number, Episode.id)
            )
        )
        episode_ids = [episode.id for episode in episodes]
        files_by_episode: dict[int, list[dict[str, object]]] = {
            episode_id: [] for episode_id in episode_ids
        }
        if episode_ids:
            for mapping, media in session.execute(
                select(EpisodeFile, MediaFile)
                .join(MediaFile, MediaFile.id == EpisodeFile.media_file_id)
                .where(EpisodeFile.episode_id.in_(episode_ids))
                .order_by(
                    EpisodeFile.episode_id,
                    EpisodeFile.is_primary.desc(),
                    MediaFile.path,
                )
            ):
                files_by_episode[mapping.episode_id].append({
                    "id": media.id, "path": media.path, "exists": media.exists,
                    "primary": mapping.is_primary, "locked": mapping.manually_locked,
                })
        playback_by_episode = {
            playback.episode_id: playback
            for playback in session.scalars(
                select(PlaybackState).where(PlaybackState.episode_id.in_(episode_ids))
            )
        } if episode_ids else {}
        result = []
        for episode in episodes:
            playback = playback_by_episode.get(episode.id)
            result.append(
                EpisodeView(
                    **EpisodeView.model_validate(episode).model_dump(exclude={"media_files", "playback"}),
                    media_files=files_by_episode[episode.id],
                    playback=(
                        {
                            "position_seconds": playback.position_seconds,
                            "duration_seconds": playback.duration_seconds,
                            "progress_ratio": playback.progress_ratio,
                            "watched": playback.watched,
                            "watched_source": playback.watched_source,
                            "last_played_at": playback.last_played_at,
                        }
                        if playback else None
                    ),
                )
            )
        return result
