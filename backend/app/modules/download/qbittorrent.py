from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from backend.app.config import QBittorrentConfig


class QBittorrentError(RuntimeError):
    pass


class QBittorrentAdapter:
    """Minimal qBittorrent WebUI API adapter with a reusable authenticated session."""

    def __init__(
        self,
        settings_provider: Callable[[], QBittorrentConfig],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings_provider = settings_provider
        self.transport = transport
        self._client: httpx.AsyncClient | None = None
        self._base_url = ""
        self._authenticated = False
        self._auth_lock = asyncio.Lock()
        self._uses_stop_start: bool | None = None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None
        self._authenticated = False

    async def login(self, *, force: bool = False) -> None:
        settings = self.settings_provider()
        if not settings.username or not settings.password.get_secret_value():
            raise QBittorrentError("qBittorrent 尚未配置用户名或密码")
        async with self._auth_lock:
            if self._authenticated and not force:
                return
            base_url = settings.base_url.rstrip("/")
            if self._client is None or self._base_url != base_url:
                if self._client is not None:
                    await self._client.aclose()
                self._client = httpx.AsyncClient(
                    base_url=base_url,
                    timeout=settings.timeout,
                    transport=self.transport,
                    follow_redirects=False,
                    headers={"Referer": f"{base_url}/"},
                )
                self._base_url = base_url
            try:
                response = await self._client.post(
                    "/api/v2/auth/login",
                    data={
                        "username": settings.username,
                        "password": settings.password.get_secret_value(),
                    },
                )
            except httpx.HTTPError as exc:
                raise QBittorrentError(f"无法连接 qBittorrent：{exc}") from exc
            if response.status_code == 403:
                raise QBittorrentError("qBittorrent 拒绝登录，当前 IP 可能已被临时封禁")
            if not (
                response.status_code == 204
                or (response.status_code == 200 and response.text.strip().startswith("Ok"))
            ):
                raise QBittorrentError("qBittorrent 用户名或密码错误")
            self._authenticated = True

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> httpx.Response:
        await self.login()
        assert self._client is not None
        try:
            response = await self._client.request(method, f"/api/v2/{endpoint}", **kwargs)
            if response.status_code == 403:
                self._authenticated = False
                await self.login(force=True)
                response = await self._client.request(method, f"/api/v2/{endpoint}", **kwargs)
        except httpx.HTTPError as exc:
            raise QBittorrentError(f"qBittorrent 请求失败：{exc}") from exc
        return response

    @staticmethod
    def _require_success(response: httpx.Response, action: str) -> None:
        if response.status_code >= 300:
            raise QBittorrentError(
                f"qBittorrent {action}失败：HTTP {response.status_code} {response.text[:200]}"
            )

    async def version(self) -> str:
        response = await self._request("GET", "app/version")
        self._require_success(response, "版本查询")
        return response.text.strip()

    async def add(
        self,
        magnet: str,
        *,
        save_path: str,
        category: str,
        tags: list[str],
        torrent_hash: str,
    ) -> None:
        created = await self._request(
            "POST", "torrents/createCategory", data={"category": category, "savePath": ""}
        )
        if created.status_code not in (200, 204, 409):
            self._require_success(created, "分类创建")
        data = {
            "urls": magnet,
            "savepath": save_path,
            "category": category,
            "tags": ",".join(tags),
            "paused": "false",
            "stopped": "false",
            "autoTMM": "false",
        }
        response = await self._request("POST", "torrents/add", data=data)
        if response.status_code in (200, 202):
            body = response.text.strip()
            if not body or body.startswith("Ok"):
                return
            try:
                result = response.json()
            except ValueError:
                result = None
            if isinstance(result, dict) and (result.get("success_count") or result.get("pending_count")):
                return
        if await self.status(torrent_hash) is not None:
            return
        raise QBittorrentError(
            f"qBittorrent 拒绝添加 magnet：HTTP {response.status_code} {response.text[:200]}"
        )

    async def status(self, torrent_hash: str) -> dict[str, Any] | None:
        response = await self._request("GET", "torrents/info", params={"hashes": torrent_hash})
        self._require_success(response, "状态查询")
        try:
            items = response.json()
        except ValueError as exc:
            raise QBittorrentError("qBittorrent 返回了无效的状态数据") from exc
        if not isinstance(items, list):
            raise QBittorrentError("qBittorrent 返回了无效的状态数据")
        return next(
            (item for item in items if str(item.get("hash", "")).lower() == torrent_hash.lower()),
            None,
        )

    async def files(self, torrent_hash: str) -> list[dict[str, Any]]:
        response = await self._request("GET", "torrents/files", params={"hash": torrent_hash})
        self._require_success(response, "文件查询")
        try:
            items = response.json()
        except ValueError as exc:
            raise QBittorrentError("qBittorrent 返回了无效的文件列表") from exc
        if not isinstance(items, list):
            raise QBittorrentError("qBittorrent 返回了无效的文件列表")
        return items

    async def _start_stop(self, torrent_hash: str, modern: str, legacy: str) -> None:
        first, second = (modern, legacy) if self._uses_stop_start is not False else (legacy, modern)
        response = await self._request("POST", f"torrents/{first}", data={"hashes": torrent_hash})
        used = first
        if response.status_code == 404:
            response = await self._request("POST", f"torrents/{second}", data={"hashes": torrent_hash})
            used = second
        self._require_success(response, used)
        self._uses_stop_start = used == modern

    async def pause(self, torrent_hash: str) -> None:
        await self._start_stop(torrent_hash, "stop", "pause")

    async def resume(self, torrent_hash: str) -> None:
        await self._start_stop(torrent_hash, "start", "resume")

    async def priority(self, torrent_hash: str, file_ids: list[int], priority: int) -> None:
        response = await self._request(
            "POST",
            "torrents/filePrio",
            data={"hash": torrent_hash, "id": "|".join(map(str, file_ids)), "priority": priority},
        )
        self._require_success(response, "优先级设置")

    async def category(self, torrent_hash: str, category: str) -> None:
        response = await self._request(
            "POST", "torrents/setCategory", data={"hashes": torrent_hash, "category": category}
        )
        if response.status_code == 409:
            created = await self._request(
                "POST", "torrents/createCategory", data={"category": category, "savePath": ""}
            )
            if created.status_code not in (200, 204, 409):
                self._require_success(created, "分类创建")
            response = await self._request(
                "POST", "torrents/setCategory", data={"hashes": torrent_hash, "category": category}
            )
        self._require_success(response, "分类设置")

    async def tag(self, torrent_hash: str, tags: list[str]) -> None:
        response = await self._request(
            "POST", "torrents/addTags", data={"hashes": torrent_hash, "tags": ",".join(tags)}
        )
        self._require_success(response, "标签设置")

    async def delete(self, torrent_hash: str, *, delete_files: bool = False) -> None:
        response = await self._request(
            "POST",
            "torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": str(delete_files).lower()},
        )
        self._require_success(response, "任务删除")
