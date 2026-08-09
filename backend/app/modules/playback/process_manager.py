from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import PlayerConfig
from backend.app.modules.playback.mpv_client import MpvJsonIpcClient


class PlaybackBusyError(RuntimeError):
    pass


class MpvUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class ManagedMpv:
    process: asyncio.subprocess.Process
    client: MpvJsonIpcClient
    ipc_path: str


class MpvProcessManager:
    def __init__(self, settings_provider) -> None:
        self.settings_provider = settings_provider
        self.active: ManagedMpv | None = None
        self._lock = asyncio.Lock()

    def _ipc_path(self) -> str:
        name = f"autoanime-mpv-{uuid.uuid4().hex}"
        if os.name == "nt":
            return rf"\\.\pipe\{name}"
        return str(Path(tempfile.gettempdir()) / f"{name}.sock")

    async def launch(self, media_path: str, start_seconds: float = 0) -> ManagedMpv:
        async with self._lock:
            if self.active is not None and self.active.process.returncode is None:
                raise PlaybackBusyError("已有受控 MPV 会话")
            config: PlayerConfig = self.settings_provider()
            candidate = Path(config.mpv_path).expanduser()
            executable = str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else shutil.which(config.mpv_path)
            if executable is None:
                raise MpvUnavailableError(f"找不到 MPV：{config.mpv_path}")
            ipc_path = self._ipc_path()
            arguments = [
                executable, media_path, f"--input-ipc-server={ipc_path}",
                "--force-window=yes", "--save-position-on-quit=no", "--resume-playback=no",
            ]
            if start_seconds > 0:
                arguments.append(f"--start={start_seconds:.3f}")
            process = await asyncio.create_subprocess_exec(
                *arguments,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            client = MpvJsonIpcClient(ipc_path)
            try:
                await client.connect()
            except Exception:
                if process.returncode is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                await process.wait()
                await client.close()
                raise
            self.active = ManagedMpv(process, client, ipc_path)
            return self.active

    async def stop(self, managed: ManagedMpv) -> None:
        if managed.process.returncode is None:
            try:
                await managed.client.command(["quit"])
                await asyncio.wait_for(managed.process.wait(), 3)
            except Exception:
                if managed.process.returncode is None:
                    try:
                        managed.process.terminate()
                    except ProcessLookupError:
                        pass
                await managed.process.wait()

    async def release(self, managed: ManagedMpv) -> None:
        try:
            await managed.client.close()
        finally:
            async with self._lock:
                if self.active is managed:
                    self.active = None
