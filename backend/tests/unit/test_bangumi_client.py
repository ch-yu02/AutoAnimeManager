import httpx
import pytest

from backend.app.config import BangumiConfig
from backend.app.modules.bangumi.client import BangumiClient
from backend.app.modules.bangumi.errors import (
    BangumiAuthError,
    BangumiRateLimitError,
    BangumiTemporaryError,
)
from backend.app.modules.bangumi.schemas import BangumiEpisode, BangumiSubject


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [(0, "MAIN"), (1, "SPECIAL"), (2, "OP"), (3, "ED"), (4, "PV"), (5, "OTHER"), (6, "OTHER")],
)
def test_episode_types_are_normalized(raw_type: int, expected: str) -> None:
    episode = BangumiEpisode.from_api({"id": 1, "type": raw_type, "sort": 1})
    assert episode.episode_type == expected


def test_subject_aliases_are_read_from_infobox() -> None:
    subject = BangumiSubject.from_api({
        "id": 1,
        "name": "作品",
        "infobox": [
            {"key": "英文名", "value": "Example Anime"},
            {"key": "别名", "value": [{"v": "Example Romanized"}]},
        ],
    })

    assert subject.aliases == ("Example Anime", "Example Romanized")


@pytest.mark.anyio
async def test_collections_are_paginated_and_episode_types_are_normalized() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        offset = int(request.url.params["offset"])
        if offset == 0:
            return httpx.Response(
                200,
                json={
                    "data": [{"subject_id": 1, "type": 2}, {"subject_id": 2, "type": 1}],
                    "total": 3,
                },
            )
        return httpx.Response(200, json={"data": [{"subject_id": 3, "type": 3}], "total": 3})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://example.test")
    client = BangumiClient(
        BangumiConfig(username="user", access_token="secret", page_size=2),
        http_client=http_client,
    )
    collections = await client.get_user_collections()

    assert [item.subject_id for item in collections] == [1, 2, 3]
    assert [item.collection_type for item in collections] == ["COLLECTED", "WISH", "DOING"]
    assert len(calls) == 2
    assert all(request.headers["authorization"] == "Bearer secret" for request in calls)
    await http_client.aclose()


@pytest.mark.anyio
async def test_episode_collections_and_relations_follow_official_shapes() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/episodes"):
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                    "data": [
                        {
                            "episode": {"id": 88},
                            "type": 2,
                            "updated_at": 0,
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json=[{"id": 2, "type": 2, "name": "Second", "name_cn": "第二季", "relation": "续集"}],
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.test"
    )
    client = BangumiClient(
        BangumiConfig(username="user", access_token="secret", page_size=1),
        http_client=http_client,
    )

    statuses = await client.get_episode_collection(1)
    relations = await client.get_subject_relations(1)

    assert statuses == {88: "WATCHED"}
    assert relations[0].related_subject_id == 2
    assert calls.count("/v0/subjects/1/subjects") == 1
    await http_client.aclose()


@pytest.mark.anyio
async def test_successful_get_requests_are_cached() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"id": 1})

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.test"
    )
    client = BangumiClient(
        BangumiConfig(username="user", access_token="secret", cache_ttl_seconds=30),
        http_client=http_client,
    )
    await client.test_connection()
    await client.test_connection()

    assert calls == 1
    await http_client.aclose()


@pytest.mark.anyio
async def test_auth_and_rate_limit_errors_are_classified_without_raw_response() -> None:
    auth_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="secret-token")),
        base_url="https://example.test",
    )
    client = BangumiClient(BangumiConfig(username="user", access_token="secret-token"), http_client=auth_client)
    with pytest.raises(BangumiAuthError) as error:
        await client.test_connection()
    assert error.value.code == "authentication_failed"
    assert "secret-token" not in str(error.value)
    await auth_client.aclose()

    rate_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(429)),
        base_url="https://example.test",
    )
    client = BangumiClient(
        BangumiConfig(username="user", access_token="secret-token"),
        http_client=rate_client,
        max_retries=1,
        retry_delay=0,
    )
    with pytest.raises(BangumiRateLimitError):
        await client.test_connection()
    await rate_client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
async def test_server_errors_are_temporary(status_code: int) -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code)),
        base_url="https://example.test",
    )
    client = BangumiClient(
        BangumiConfig(username="user", access_token="secret"),
        http_client=http_client,
        max_retries=0,
    )
    with pytest.raises(BangumiTemporaryError):
        await client.test_connection()
    await http_client.aclose()


@pytest.mark.anyio
async def test_episode_watch_state_writeback_uses_official_endpoint() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.bgm.tv"
    )
    client = BangumiClient(BangumiConfig(access_token="token"), http_client=http_client)
    await client.set_episode_collection(123, True)

    assert captured[0].method == "PUT"
    assert captured[0].url.path == "/v0/users/-/collections/-/episodes/123"
    assert captured[0].read() == b'{"type":2}'
    await http_client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("collection_type", "type_value"),
    [
        ("WISH", 1),
        ("COLLECTED", 2),
        ("DOING", 3),
        ("ON_HOLD", 4),
        ("DROPPED", 5),
    ],
)
async def test_subject_collection_writeback_uses_official_endpoint(
    collection_type: str, type_value: int
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.bgm.tv"
    )
    client = BangumiClient(BangumiConfig(access_token="token"), http_client=http_client)

    await client.set_subject_collection(123, collection_type)

    assert captured[0].method == "POST"
    assert captured[0].url.path == "/v0/users/-/collections/123"
    assert captured[0].read() == f'{{"type":{type_value}}}'.encode()
    await http_client.aclose()
