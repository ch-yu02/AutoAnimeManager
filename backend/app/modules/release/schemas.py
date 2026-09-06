from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class RawRelease:
    source_id: str
    title: str
    description: str
    release_url: str
    magnet_uri: str | None
    published_at: datetime | None
    author: str | None
    category: str | None
    size_bytes: int | None = None
    provider: str | None = None


@dataclass(slots=True)
class ParsedRelease:
    raw: RawRelease
    normalized_title: str
    release_group: str | None
    season: int | None
    part: int | None
    episode_start: float | None
    episode_end: float | None
    subtitle_language: str | None
    resolution: str | None
    codec: str | None
    is_batch: bool
    size_bytes: int | None


@dataclass(slots=True)
class ScoredRelease:
    parsed: ParsedRelease
    magnet_hash: str | None
    score: float
    decision: str
    match_reasons: list[str]
    reject_reasons: list[str]
    duplicate: bool
