from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from backend.app.database.models.episode import Episode
from backend.app.database.models.subject import Subject, SubjectRelation
from backend.app.database.models.sync import SyncRun
from backend.app.database.session import session_scope

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
    total_main_episodes: int | None
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
    last_synced_at: datetime | None


def _display_name(subject: Subject) -> str:
    return subject.name_cn or subject.name or f"Bangumi #{subject.bangumi_subject_id}"


def _list_item(session, subject: Subject) -> SubjectListItem:
    episodes = list(session.scalars(select(Episode).where(Episode.subject_id == subject.id)))
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
        total_main_episodes=subject.total_main_episodes,
        episode_count=len(episodes),
        main_episode_count=sum(episode.episode_type == "MAIN" for episode in episodes),
        last_synced_at=subject.last_synced_at,
    )


@router.get("", response_model=list[SubjectListItem])
async def list_subjects(
    collection_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    collection_status: str | None = Query(default=None),
) -> list[SubjectListItem]:
    selected_type = collection_type or status_filter or collection_status
    with session_scope() as session:
        query = select(Subject).where(Subject.collection_type.is_not(None)).order_by(Subject.updated_at.desc())
        if selected_type:
            query = query.where(Subject.collection_type == selected_type.upper())
        subjects = list(session.scalars(query))
        return [_list_item(session, subject) for subject in subjects]


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
        return [EpisodeView.model_validate(episode) for episode in episodes]
