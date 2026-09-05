from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from backend.app.config import BangumiConfig
from backend.app.modules.bangumi.errors import (
    BangumiAuthError,
    BangumiError,
    BangumiRateLimitError,
    BangumiResponseError,
    BangumiTemporaryError,
)
from backend.app.modules.bangumi.schemas import (
    BangumiCollection,
    BangumiEpisode,
    BangumiRelation,
    BangumiSubject,
)


class BangumiClient:
    def __init__(
        self,
        settings: BangumiConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
        retry_delay: float = 0.05,
    ) -> None:
        self.settings = settings
        self._client = http_client
        self._owns_client = http_client is None
        self.max_retries = max(0, max_retries)
        self.retry_delay = max(0.0, retry_delay)
        self.page_size = settings.page_size
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, Any]] = {}

    def _new_http_client(self) -> httpx.AsyncClient:
        # HTTPX honors HTTP_PROXY/HTTPS_PROXY/ALL_PROXY by default. Keep that
        # behavior explicit and identical for reads and writebacks.
        # Source: https://www.python-httpx.org/environment_variables/#proxies
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout,
            trust_env=True,
        )

    def _path(self, path: str) -> str:
        base = self.settings.base_url.rstrip("/")
        if base.endswith("/v0"):
            return path.removeprefix("/v0") or "/"
        return f"/v0{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.access_token.get_secret_value()}",
            "User-Agent": "AutoAnime/0.1 (+local)",
            "Accept": "application/json",
        }

    async def __aenter__(self) -> "BangumiClient":
        if self._client is None:
            self._client = self._new_http_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        cache_key = (path, tuple(sorted((key, str(value)) for key, value in (params or {}).items())))
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]

        client = self._client
        if client is None:
            client = self._new_http_client()
            self._client = client
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.get(self._path(path), params=params, headers=self._headers())
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError("Bangumi 请求超时") from exc
            except httpx.RequestError as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError("Bangumi 网络请求失败") from exc

            if response.status_code in (401, 403):
                raise BangumiAuthError("Bangumi Token 无效或无权访问", status_code=response.status_code)
            if response.status_code == 429:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiRateLimitError("Bangumi 请求过于频繁，请稍后重试", status_code=429)
            if response.status_code in (500, 502, 503, 504):
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError("Bangumi 服务暂时不可用", status_code=response.status_code)
            if response.status_code >= 400:
                raise BangumiError(
                    f"Bangumi 请求失败（HTTP {response.status_code}）", status_code=response.status_code
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise BangumiResponseError("Bangumi 返回了无法解析的响应", status_code=response.status_code) from exc
            if self.settings.cache_ttl_seconds > 0:
                self._cache[cache_key] = (time.monotonic() + self.settings.cache_ttl_seconds, payload)
            return payload
        raise BangumiTemporaryError("Bangumi 请求失败")

    async def _paged(self, path: str, *, extra_params: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        limit = self.page_size
        offset = 0
        while True:
            params = {"limit": limit, "offset": offset, **(extra_params or {})}
            payload = await self._request_json(path, params=params)
            if isinstance(payload, list):
                rows = payload
                total = len(rows)
            elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
                rows = payload["data"]
                pagination = payload.get("pagination") or {}
                total = payload.get("total", pagination.get("total"))
            else:
                raise BangumiResponseError("Bangumi 分页响应格式无效")
            if not all(isinstance(row, dict) for row in rows):
                raise BangumiResponseError("Bangumi 分页数据格式无效")
            for row in rows:
                yield row
            if not rows or len(rows) < limit or (isinstance(total, int) and offset + len(rows) >= total):
                break
            offset += len(rows)

    async def _list(self, path: str) -> list[dict[str, Any]]:
        payload = await self._request_json(path)
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise BangumiResponseError("Bangumi 列表响应格式无效")
        return payload

    async def get_user_collections(self, username: str | None = None) -> list[BangumiCollection]:
        user = username or self.settings.username
        rows = [row async for row in self._paged(f"/users/{user}/collections", extra_params={"subject_type": 2})]
        try:
            return [BangumiCollection.from_api(row) for row in rows]
        except ValueError as exc:
            raise BangumiResponseError("Bangumi 收藏数据缺少必要字段") from exc

    async def get_subject(self, subject_id: int) -> BangumiSubject:
        payload = await self._request_json(f"/subjects/{subject_id}")
        if not isinstance(payload, dict):
            raise BangumiResponseError("Bangumi 条目响应格式无效")
        try:
            return BangumiSubject.from_api(payload)
        except ValueError as exc:
            raise BangumiResponseError("Bangumi 条目数据缺少必要字段") from exc

    async def get_episodes(self, subject_id: int) -> list[BangumiEpisode]:
        rows = [row async for row in self._paged("/episodes", extra_params={"subject_id": subject_id})]
        try:
            return [BangumiEpisode.from_api(row) for row in rows]
        except ValueError as exc:
            raise BangumiResponseError("Bangumi 章节数据缺少必要字段") from exc

    async def get_episode_collection(self, subject_id: int) -> dict[int, str]:
        rows = [
            row
            async for row in self._paged(f"/users/-/collections/{subject_id}/episodes")
        ]
        result: dict[int, str] = {}
        for row in rows:
            episode = row.get("episode")
            episode_id = episode.get("id") if isinstance(episode, dict) else row.get("episode_id", row.get("id"))
            if isinstance(episode_id, int):
                raw_status = row.get("type", row.get("status"))
                result[episode_id] = {
                    0: "NONE",
                    1: "WISH",
                    2: "WATCHED",
                    3: "DROPPED",
                }.get(raw_status, str(raw_status).upper() if raw_status is not None else "NONE")
        return result

    async def get_subject_relations(self, subject_id: int) -> list[BangumiRelation]:
        rows = await self._list(f"/subjects/{subject_id}/subjects")
        try:
            return [BangumiRelation.from_api(row) for row in rows]
        except ValueError as exc:
            raise BangumiResponseError("Bangumi 条目关系数据缺少必要字段") from exc

    async def test_connection(self, username: str | None = None) -> None:
        user = username or self.settings.username
        payload = await self._request_json(f"/users/{user}")
        if not isinstance(payload, dict):
            raise BangumiResponseError("Bangumi 用户响应格式无效")

    async def set_episode_collection(self, episode_id: int, watched: bool) -> None:
        client = self._client
        if client is None:
            client = self._new_http_client()
            self._client = client
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.put(
                    self._path(f"/users/-/collections/-/episodes/{episode_id}"),
                    json={"type": 2 if watched else 0},
                    headers={**self._headers(), "Content-Type": "application/json"},
                )
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError("Bangumi 观看状态回写失败") from exc
            if response.status_code in (401, 403):
                raise BangumiAuthError("Bangumi Token 无效或无权回写", status_code=response.status_code)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError("Bangumi 观看状态回写暂时不可用", status_code=response.status_code)
            if response.status_code >= 400:
                raise BangumiError(f"Bangumi 观看状态回写失败（HTTP {response.status_code}）", status_code=response.status_code)
            return
        raise BangumiTemporaryError("Bangumi 观看状态回写失败")

    async def set_subject_collection(self, subject_id: int, collection_type: str) -> None:
        type_value = {
            "WISH": 1,
            "COLLECTED": 2,
            "DOING": 3,
            "ON_HOLD": 4,
            "DROPPED": 5,
        }.get(collection_type.upper())
        if type_value is None:
            raise ValueError(f"未知 Bangumi 收藏状态：{collection_type}")
        client = self._client
        if client is None:
            client = self._new_http_client()
            self._client = client
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(
                    self._path(f"/users/-/collections/{subject_id}"),
                    json={"type": type_value},
                    headers={**self._headers(), "Content-Type": "application/json"},
                )
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError("Bangumi 收藏状态回写失败") from exc
            if response.status_code in (401, 403):
                raise BangumiAuthError("Bangumi Token 无效或无权回写", status_code=response.status_code)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise BangumiTemporaryError(
                    "Bangumi 收藏状态回写暂时不可用", status_code=response.status_code
                )
            if response.status_code >= 400:
                raise BangumiError(
                    f"Bangumi 收藏状态回写失败（HTTP {response.status_code}）",
                    status_code=response.status_code,
                )
            return
        raise BangumiTemporaryError("Bangumi 收藏状态回写失败")
