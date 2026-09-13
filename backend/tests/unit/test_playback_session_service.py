import asyncio
from types import SimpleNamespace

import pytest

from backend.app.modules.playback.session_service import PlaybackSessionService


class FakeStateService:
    def __init__(self) -> None:
        self.records: list[tuple[int, int, float, float | None, bool]] = []
        self.episodes = {
            1: (SimpleNamespace(id=1), SimpleNamespace(id=11, path="/library/one.mkv")),
            2: (SimpleNamespace(id=2), SimpleNamespace(id=12, path="/library/two.mkv")),
        }

    def playable_media(self, episode_id: int):
        if episode_id not in self.episodes:
            raise LookupError("episode_not_found")
        return self.episodes[episode_id]

    def begin(self, episode_id: int, media_file_id: int):
        return {
            "position_seconds": 812.4 if episode_id == 1 else 0,
            "duration_seconds": 1440.0,
            "watched": False,
        }

    def record(self, episode_id: int, media_file_id: int, position: float, duration: float | None, *, ended: bool):
        self.records.append((episode_id, media_file_id, position, duration, ended))
        return {"episode_id": episode_id, "position_seconds": position, "watched": ended}

    def next_playable(self, episode_id: int):
        return self.episodes.get(2) if episode_id == 1 else None

    def continue_watching(self):
        return [{"episode_id": 1}]

    def first_unwatched(self, subject_id: int):
        return {"episode_id": 1, "subject_id": subject_id}

    def mark_watched(self, episode_id: int, watched: bool):
        return {"episode_id": episode_id, "watched": watched}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_session_creates_resume_progress_and_invalidates_previous() -> None:
    states = FakeStateService()
    service = PlaybackSessionService(states)

    first = await service.create(1)
    assert first["initial_position_seconds"] == 812.4
    progress = await service.progress(first["session_id"], 900, 1440, ended=False)
    assert progress["position_seconds"] == 900
    assert progress["next_episode_id"] is None
    assert states.records == [(1, 11, 900, 1440, False)]

    second = await service.create(2, from_start=True)
    assert second["initial_position_seconds"] == 0
    with pytest.raises(LookupError, match="playback_session_not_found"):
        await service.progress(first["session_id"], 1000, 1440)

    closed = await service.close(second["session_id"])
    assert closed["status"] == "closed"


@pytest.mark.anyio
async def test_ended_session_reports_strict_next_playable_episode() -> None:
    service = PlaybackSessionService(FakeStateService())
    current = await service.create(1)

    progress = await service.progress(current["session_id"], 1440, 1440, ended=True)

    assert progress["watched"] is True
    assert progress["next_episode_id"] == 2


@pytest.mark.anyio
async def test_completed_episode_resumes_from_start_instead_of_eof() -> None:
    class CompletedStateService(FakeStateService):
        def begin(self, episode_id: int, media_file_id: int):
            return {
                "position_seconds": 1440.0,
                "duration_seconds": 1440.0,
                "watched": True,
            }

    service = PlaybackSessionService(CompletedStateService())

    resumed = await service.create(1)

    assert resumed["initial_position_seconds"] == 0


@pytest.mark.anyio
async def test_state_queries_and_writeback_remain_available() -> None:
    states = FakeStateService()
    writes: list[tuple[int, bool]] = []

    async def writeback(episode_id: int, watched: bool) -> None:
        writes.append((episode_id, watched))

    settings = SimpleNamespace(bangumi_writeback_enabled=True)
    service = PlaybackSessionService(states, lambda: settings, writeback)

    assert service.continue_watching() == [{"episode_id": 1}]
    assert service.first_unwatched(7) == {"episode_id": 1, "subject_id": 7}
    marked = await service.mark_watched(1, False)
    current = await service.create(1)
    await service.progress(current["session_id"], 1440, 1440, ended=True)
    await asyncio.sleep(0)

    assert marked["watched"] is False
    assert writes == [(1, False), (1, True)]


@pytest.mark.anyio
async def test_automatic_writeback_retries_after_a_transient_failure() -> None:
    states = FakeStateService()
    attempts = 0

    async def writeback(_episode_id: int, _watched: bool) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("proxy unavailable")

    settings = SimpleNamespace(bangumi_writeback_enabled=True)
    service = PlaybackSessionService(states, lambda: settings, writeback)
    current = await service.create(1)

    await service.progress(current["session_id"], 1440, 1440, ended=True)
    await asyncio.sleep(0)
    await service.progress(current["session_id"], 1440, 1440, ended=True)
    await asyncio.sleep(0)

    assert attempts == 2


@pytest.mark.anyio
async def test_progress_response_does_not_wait_for_bangumi_writeback() -> None:
    states = FakeStateService()
    writeback_started = asyncio.Event()
    release_writeback = asyncio.Event()

    async def writeback(_episode_id: int, _watched: bool) -> None:
        writeback_started.set()
        await release_writeback.wait()

    settings = SimpleNamespace(bangumi_writeback_enabled=True)
    service = PlaybackSessionService(states, lambda: settings, writeback)
    current = await service.create(1)

    progress = await asyncio.wait_for(
        service.progress(current["session_id"], 1440, 1440, ended=True),
        timeout=0.1,
    )

    assert progress["watched"] is True
    await asyncio.wait_for(writeback_started.wait(), timeout=0.1)
    release_writeback.set()
    await service.stop()
