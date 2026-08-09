import asyncio
import json
import os

import pytest

from backend.app.modules.playback.mpv_client import MpvJsonIpcClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.skipif(os.name == "nt", reason="Unix socket protocol fixture")
async def test_json_ipc_keeps_connection_and_dispatches_events(tmp_path, monkeypatch) -> None:
    received = []
    lines: asyncio.Queue[bytes] = asyncio.Queue()

    class FakeReader:
        async def readline(self) -> bytes:
            return await lines.get()

    class FakeWriter:
        def write(self, data: bytes) -> None:
            request = json.loads(data)
            received.append(request)
            lines.put_nowait((json.dumps({"request_id": request["request_id"], "error": "success"}) + "\n").encode())
            lines.put_nowait((json.dumps({"event": "property-change", "name": "time-pos", "data": 42.5}) + "\n").encode())

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            lines.put_nowait(b"")

        async def wait_closed(self) -> None:
            return None

    async def open_test_connection(_path):
        return FakeReader(), FakeWriter()

    monkeypatch.setattr(asyncio, "open_unix_connection", open_test_connection)
    client = MpvJsonIpcClient(str(tmp_path / "mpv.sock"))
    events = []
    client.add_event_handler(_fail)
    client.add_event_handler(lambda event: _append(events, event))
    await client.connect()
    await client.observe(1, "time-pos")
    await asyncio.sleep(0.02)

    assert received[0]["command"] == ["observe_property", 1, "time-pos"]
    assert events[0]["data"] == 42.5
    await client.close()


async def _append(items: list[dict], value: dict) -> None:
    items.append(value)


async def _fail(_value: dict) -> None:
    raise RuntimeError("event handler failed")
