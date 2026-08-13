from __future__ import annotations

from datetime import UTC, datetime

from backend.app.config import get_settings
from backend.app.database.models import Episode, Subject
from backend.app.database.session import session_scope
from backend.app.modules.bangumi.client import BangumiClient


async def writeback_episode_state(episode_id: int, watched: bool) -> None:
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("episode_not_found")
        bangumi_episode_id = episode.bangumi_episode_id
    settings = get_settings().bangumi
    if not settings.access_token.get_secret_value():
        raise RuntimeError("Bangumi Token 未配置")
    async with BangumiClient(settings) as client:
        await client.set_episode_collection(bangumi_episode_id, watched)
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        if episode is not None:
            episode.bangumi_watch_status = "WATCHED" if watched else "NONE"


async def writeback_subject_collection(subject_id: int, collection_type: str) -> dict[str, object]:
    normalized = collection_type.upper()
    allowed = {"WISH", "DOING", "COLLECTED", "ON_HOLD", "DROPPED"}
    if normalized not in allowed:
        raise ValueError("invalid_collection_type")
    with session_scope() as session:
        subject = session.get(Subject, subject_id)
        if subject is None:
            raise LookupError("subject_not_found")
        bangumi_subject_id = subject.bangumi_subject_id
    settings = get_settings().bangumi
    if not settings.access_token.get_secret_value():
        raise RuntimeError("bangumi_not_configured")

    # Remote first: a failed Bangumi request must not leave an unsynchronized local label.
    async with BangumiClient(settings) as client:
        await client.set_subject_collection(bangumi_subject_id, normalized)

    updated_at = datetime.now(UTC)
    with session_scope() as session:
        subject = session.get(Subject, subject_id)
        if subject is None:
            raise LookupError("subject_not_found")
        subject.collection_type = normalized
        subject.collection_updated_at = updated_at
    return {
        "subject_id": subject_id,
        "bangumi_subject_id": bangumi_subject_id,
        "collection_type": normalized,
        "collection_updated_at": updated_at,
        "synced_to_bangumi": True,
    }
