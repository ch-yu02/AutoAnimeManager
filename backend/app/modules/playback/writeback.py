from __future__ import annotations

from backend.app.config import get_settings
from backend.app.database.models import Episode
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
