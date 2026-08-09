import asyncio
from types import SimpleNamespace

import pytest

from backend.app.config import PlayerConfig
from backend.app.modules.playback.process_manager import PlaybackBusyError
from backend.app.modules.playback.service import PlaybackService


class FakeProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.done = asyncio.Event()

    async def wait(self) -> int:
        await self.done.wait()
        return 0

    def finish(self) -> None:
        self.returncode = 0
        self.done.set()


class FakeClient:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.handlers = []
        self.commands = []
        self.observed = []

    def add_event_handler(self, handler) -> None:
        self.handlers.append(handler)

    async def observe(self, observer_id: int, name: str) -> None:
        self.observed.append((observer_id, name))

    async def command(self, command) -> None:
        self.commands.append(command)

    async def emit(self, event) -> None:
        for handler in self.handlers:
            await handler(event)

    async def close(self) -> None:
        return None


class FakeManager:
    def __init__(self) -> None:
        self.launches = []
        self.managed = []

    async def launch(self, path: str, start_seconds: float):
        process = FakeProcess()
        client = FakeClient(process)
        managed = SimpleNamespace(process=process, client=client, ipc_path="fake")
        self.launches.append((path, start_seconds))
        self.managed.append(managed)
        return managed

    async def stop(self, managed) -> None:
        managed.process.finish()

    async def release(self, managed) -> None:
        await managed.client.close()


class FakeStates:
    def __init__(self) -> None:
        self.episodes = {
            1: SimpleNamespace(id=1, subject_id=10, sort_number=1),
            2: SimpleNamespace(id=2, subject_id=10, sort_number=2),
        }
        self.media = {
            1: SimpleNamespace(id=11, path="one.mkv"),
            2: SimpleNamespace(id=12, path="two.mkv"),
        }
        self.records = []

    def playable_media(self, episode_id):
        return self.episodes[episode_id], self.media[episode_id]

    def begin(self, episode_id, media_file_id):
        return {
            "position_seconds": 120 if episode_id == 1 else 0,
            "duration_seconds": 1000,
            "watched": False,
        }

    def record(self, episode_id, media_file_id, position, duration, *, ended=False):
        self.records.append((episode_id, position, duration, ended))
        return {"watched": ended, "episode_id": episode_id}

    def next_playable(self, episode_id):
        return (self.episodes[2], self.media[2]) if episode_id == 1 else None

    def mark_watched(self, episode_id, watched):
        return {"episode_id": episode_id, "watched": watched}

    def continue_watching(self):
        return []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_single_session_resume_events_and_abnormal_exit_are_saved() -> None:
    states, manager = FakeStates(), FakeManager()
    service = PlaybackService(states, manager, lambda: PlayerConfig(progress_save_interval_seconds=60))

    started = await service.start(1)
    assert started["position_seconds"] == 120
    assert manager.launches == [("one.mkv", 120)]
    with pytest.raises(PlaybackBusyError):
        await service.start(2)

    client = manager.managed[0].client
    await client.emit({"event": "property-change", "name": "time-pos", "data": 180})
    await client.emit({"event": "property-change", "name": "pause", "data": True})
    manager.managed[0].process.finish()
    await service._monitor_task

    assert any(record[1] == 180 for record in states.records)
    assert service.current()["status"] == "IDLE"


@pytest.mark.anyio
async def test_mpv_seek_saves_the_updated_position() -> None:
    states, manager = FakeStates(), FakeManager()
    service = PlaybackService(states, manager, lambda: PlayerConfig(progress_save_interval_seconds=60))
    await service.start(1)
    client = manager.managed[0].client

    await client.emit({"event": "property-change", "name": "time-pos", "data": 180})
    await client.emit({"event": "seek"})
    assert states.records == []
    await client.emit({"event": "property-change", "name": "time-pos", "data": 420})

    assert states.records[-1][1] == 420
    await service.stop()


@pytest.mark.anyio
async def test_concurrent_starts_create_only_one_controlled_session() -> None:
    states, manager = FakeStates(), FakeManager()
    service = PlaybackService(states, manager, lambda: PlayerConfig(progress_save_interval_seconds=60))

    results = await asyncio.gather(service.start(1), service.start(2), return_exceptions=True)

    assert len(manager.launches) == 1
    assert sum(isinstance(result, PlaybackBusyError) for result in results) == 1
    await service.stop()


@pytest.mark.anyio
async def test_from_start_and_normal_completion_can_launch_next_episode() -> None:
    states, manager = FakeStates(), FakeManager()
    service = PlaybackService(states, manager, lambda: PlayerConfig(progress_save_interval_seconds=60))

    await service.start(1, from_start=True)
    assert manager.launches[0] == ("one.mkv", 0)
    client = manager.managed[0].client
    await client.emit({"event": "property-change", "name": "duration", "data": 1000})
    await client.emit({"event": "property-change", "name": "time-pos", "data": 1000})
    await client.emit({"event": "end-file", "reason": "eof"})
    manager.managed[0].process.finish()
    await service._monitor_task

    assert any(record[3] is True for record in states.records)
    next_state = await service.play_next()
    assert next_state["episode_id"] == 2
    assert manager.launches[-1] == ("two.mkv", 0)
    await service.stop()


@pytest.mark.anyio
async def test_periodic_save_recovers_after_transient_failure() -> None:
    class FlakyStates(FakeStates):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        def record(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("temporary database error")
            return super().record(*args, **kwargs)

    states, manager = FlakyStates(), FakeManager()
    config = SimpleNamespace(
        progress_save_interval_seconds=0.01,
        auto_play_next=False,
        bangumi_writeback_enabled=False,
    )
    service = PlaybackService(states, manager, lambda: config)

    await service.start(1)
    await asyncio.sleep(0.04)

    assert states.attempts >= 2
    assert states.records
    await service.stop()


@pytest.mark.anyio
async def test_stop_releases_player_when_progress_save_fails() -> None:
    class FailingStates(FakeStates):
        def record(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

    states, manager = FailingStates(), FakeManager()
    service = PlaybackService(states, manager, lambda: PlayerConfig(progress_save_interval_seconds=60))

    await service.start(1)
    stopped = await service.stop()

    assert stopped == {"status": "IDLE", "episode_id": None}
    assert manager.managed[0].process.returncode == 0
    assert service.active is None


@pytest.mark.anyio
async def test_manual_next_does_not_race_with_auto_advance() -> None:
    states, manager = FakeStates(), FakeManager()
    service = PlaybackService(
        states,
        manager,
        lambda: PlayerConfig(progress_save_interval_seconds=60, auto_play_next=True),
    )

    await service.start(1)
    await manager.managed[0].client.emit({"event": "end-file", "reason": "eof"})
    result = await service.play_next()

    assert result["episode_id"] == 2
    assert manager.launches == [("one.mkv", 120), ("two.mkv", 0)]
    await service.stop()
