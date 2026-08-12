from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from backend.app.config import QBittorrentConfig
from backend.app.modules.download.magnet import InvalidMagnet, magnet_info_hash, normalize_magnet
from backend.app.modules.download.qbittorrent import QBittorrentAdapter


def test_magnet_info_hash_accepts_hex_and_base32() -> None:
    hexadecimal = "0123456789abcdef0123456789abcdef01234567"
    assert magnet_info_hash(f"magnet:?xt=urn:btih:{hexadecimal.upper()}&dn=test") == hexadecimal
    assert magnet_info_hash("magnet:?xt=urn:btih:AERUKZ4JVPG66AJDIVTYTK6N54ASGRLH") == hexadecimal
    assert magnet_info_hash(hexadecimal.upper()) == hexadecimal
    assert normalize_magnet(hexadecimal.upper()) == (
        f"magnet:?xt=urn:btih:{hexadecimal}", hexadecimal,
    )
    with pytest.raises(InvalidMagnet):
        magnet_info_hash("https://example.test/not-a-magnet")


@pytest.mark.anyio
async def test_adapter_reuses_login_and_wraps_required_operations() -> None:
    torrent_hash = "0123456789abcdef0123456789abcdef01234567"
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith("/auth/login"):
            return httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=test; Path=/"})
        if path.endswith("/torrents/createCategory"):
            return httpx.Response(409)
        if path.endswith("/torrents/add"):
            return httpx.Response(200, text="Fails.")
        if path.endswith("/torrents/info"):
            return httpx.Response(200, json=[{"hash": torrent_hash, "progress": 0.5, "state": "downloading"}])
        if path.endswith("/torrents/files"):
            return httpx.Response(200, json=[{"name": "episode.mkv", "progress": 1, "priority": 1}])
        if path.endswith("/torrents/stop"):
            return httpx.Response(404)
        return httpx.Response(204)

    config = QBittorrentConfig(
        base_url="http://qb.test", username="user", password=SecretStr("password")
    )
    adapter = QBittorrentAdapter(lambda: config, transport=httpx.MockTransport(handler))
    await adapter.add(
        f"magnet:?xt=urn:btih:{torrent_hash}",
        save_path="/downloads",
        category="autoanime",
        tags=["bgm-1", "job-one"],
        torrent_hash=torrent_hash,
    )
    assert (await adapter.status(torrent_hash) or {})["progress"] == 0.5
    assert (await adapter.files(torrent_hash))[0]["name"] == "episode.mkv"
    await adapter.pause(torrent_hash)
    await adapter.resume(torrent_hash)
    await adapter.priority(torrent_hash, [0, 2], 7)
    await adapter.category(torrent_hash, "autoanime")
    await adapter.tag(torrent_hash, ["bgm-1"])
    await adapter.delete(torrent_hash, delete_files=False)
    await adapter.close()

    assert sum(path.endswith("/auth/login") for _, path in requests) == 1
    assert ("POST", "/api/v2/torrents/pause") in requests
    assert ("POST", "/api/v2/torrents/start") not in requests
    assert ("POST", "/api/v2/torrents/resume") in requests
