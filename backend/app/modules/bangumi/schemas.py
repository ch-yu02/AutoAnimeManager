from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


def _text(value: Any) -> str:
    return value if isinstance(value, str) else "" if value is None else str(value)


def parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class BangumiCollection:
    subject_id: int
    collection_type: str
    updated_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "BangumiCollection":
        subject_id = data.get("subject_id", data.get("subject", {}).get("id"))
        if not isinstance(subject_id, int):
            raise ValueError("收藏记录缺少 subject_id")
        raw_type = data.get("type", data.get("collection_type"))
        collection_type = {
            1: "WISH",
            2: "COLLECTED",
            3: "DOING",
            4: "ON_HOLD",
            5: "DROPPED",
        }.get(raw_type, _text(raw_type).upper() or "OTHER")
        return cls(subject_id, collection_type, parse_datetime(data.get("updated_at")), data)


@dataclass(frozen=True)
class BangumiSubject:
    id: int
    name: str
    name_cn: str
    summary: str
    url: str
    image_url: str
    subject_type: int | None
    air_date: date | None
    air_status: str
    total_main_episodes: int | None
    platform: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "BangumiSubject":
        subject_id = data.get("id")
        if not isinstance(subject_id, int):
            raise ValueError("条目响应缺少 id")
        eps = data.get("eps", data.get("total_episodes"))
        return cls(
            id=subject_id,
            name=_text(data.get("name")),
            name_cn=_text(data.get("name_cn")),
            summary=_text(data.get("summary")),
            url=_text(data.get("url")) or f"https://bgm.tv/subject/{subject_id}",
            image_url=_text(data.get("images", {}).get("large") or data.get("image")),
            subject_type=data.get("type") if isinstance(data.get("type"), int) else None,
            air_date=parse_date(data.get("date")),
            air_status=_text(data.get("air_status")),
            total_main_episodes=eps if isinstance(eps, int) else None,
            platform=_text(data.get("platform")),
        )


EPISODE_TYPES = {0: "MAIN", 1: "SPECIAL", 2: "OP", 3: "ED", 4: "PV", 5: "OTHER", 6: "OTHER"}


@dataclass(frozen=True)
class BangumiEpisode:
    id: int
    episode_type: str
    sort_number: float | None
    display_number: str
    name: str
    name_cn: str
    air_date: date | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "BangumiEpisode":
        episode_id = data.get("id")
        if not isinstance(episode_id, int):
            raise ValueError("章节响应缺少 id")
        raw_type = data.get("type")
        episode_type = EPISODE_TYPES.get(raw_type, _text(raw_type).upper() or "OTHER")
        sort = data.get("sort", data.get("ep"))
        try:
            sort_number = float(sort) if sort is not None else None
        except (TypeError, ValueError):
            sort_number = None
        display = data.get("sort", data.get("ep", data.get("id")))
        return cls(
            id=episode_id,
            episode_type=episode_type,
            sort_number=sort_number,
            display_number=_text(display),
            name=_text(data.get("name")),
            name_cn=_text(data.get("name_cn")),
            air_date=parse_date(data.get("airdate", data.get("air_date"))),
        )


@dataclass(frozen=True)
class BangumiRelation:
    related_subject_id: int
    relation_type: str
    related_name: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "BangumiRelation":
        related = data.get("subject", data)
        related_id = related.get("id", data.get("subject_id"))
        if not isinstance(related_id, int):
            raise ValueError("条目关系缺少 related subject id")
        return cls(
            related_subject_id=related_id,
            relation_type=_text(data.get("relation_type") or data.get("relation") or data.get("type")) or "OTHER",
            related_name=_text(related.get("name_cn") or related.get("name")),
        )
