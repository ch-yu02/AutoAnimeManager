from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, BinaryIO


EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
logger = logging.getLogger(__name__)


class MpvIpcError(RuntimeError):
    pass


class MpvJsonIpcClient:
    """Persistent MPV JSON IPC connection using newline-delimited messages."""

    def __init__(self, ipc_path: str) -> None:
        self.ipc_path = ipc_path
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.pipe: BinaryIO | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._handlers: list[EventHandler] = []
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._request_id = 0
        self._write_lock = asyncio.Lock()

    async def connect(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            try:
                if os.name == "nt":
                    self.pipe = await asyncio.to_thread(open, self.ipc_path, "r+b", buffering=0)
                else:
                    self.reader, self.writer = await asyncio.open_unix_connection(self.ipc_path)
                self._reader_task = asyncio.create_task(self._read_loop())
                return
            except OSError as exc:
                last_error = exc
                await asyncio.sleep(0.05)
        raise MpvIpcError(f"无法连接 MPV IPC：{last_error or self.ipc_path}")

    def add_event_handler(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def command(self, command: list[object], timeout: float = 3.0) -> Any:
        self._request_id += 1
        request_id = self._request_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        payload = json.dumps({"command": command, "request_id": request_id}, separators=(",", ":")) + "\n"
        try:
            async with self._write_lock:
                if self.writer is not None:
                    self.writer.write(payload.encode("utf-8"))
                    await self.writer.drain()
                elif self.pipe is not None:
                    await asyncio.to_thread(self.pipe.write, payload.encode("utf-8"))
                else:
                    raise MpvIpcError("MPV IPC 尚未连接")
            response = await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)
        if response.get("error") != "success":
            raise MpvIpcError(f"MPV 命令失败：{response.get('error', 'unknown')}")
        return response.get("data")

    async def observe(self, observer_id: int, property_name: str) -> None:
        await self.command(["observe_property", observer_id, property_name])

    async def _readline(self) -> bytes:
        if self.reader is not None:
            return await self.reader.readline()
        if self.pipe is not None:
            return await asyncio.to_thread(self.pipe.readline)
        return b""

    async def _read_loop(self) -> None:
        try:
            while line := await self._readline():
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                request_id = message.get("request_id")
                if isinstance(request_id, int) and request_id in self._pending:
                    future = self._pending[request_id]
                    if not future.done():
                        future.set_result(message)
                    continue
                if "event" in message:
                    for handler in list(self._handlers):
                        try:
                            await handler(message)
                        except Exception:
                            logger.exception("处理 MPV IPC 事件失败", extra={"event": message.get("event")})
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(MpvIpcError("MPV IPC 已断开"))

    async def close(self) -> None:
        task = self._reader_task
        self._reader_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
        if self.pipe is not None:
            await asyncio.to_thread(self.pipe.close)
            self.pipe = None
        if os.name != "nt":
            Path(self.ipc_path).unlink(missing_ok=True)
