from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.config import PlayerConfig
from backend.app.modules.playback.web_stream import (
    WebPlaybackService,
    WebPlaybackSession,
    _resolve_start_seconds,
)


class FakeStates:
    def __init__(self) -> None:
        self.recorded = None

    def record(self, episode_id, media_file_id, position, duration, *, ended=False):
        self.recorded = (episode_id, media_file_id, position, duration, ended)
        return {"watched": ended}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_external_chinese_subtitle_is_selected_before_probe(tmp_path: Path) -> None:
    video = tmp_path / "Anime 01.mkv"
    video.write_bytes(b"")
    (tmp_path / "Anime 01.CHT.ass").write_text("", encoding="utf-8")
    preferred = tmp_path / "Anime 01.CHS.ass"
    preferred.write_text("", encoding="utf-8")
    service = WebPlaybackService(FakeStates(), lambda: PlayerConfig())

    subtitle_filter = await service._subtitle_filter(video)

    assert subtitle_filter is not None and str(preferred) in subtitle_filter


@pytest.mark.anyio
async def test_web_progress_adds_resume_offset() -> None:
    states = FakeStates()
    service = WebPlaybackService(states, lambda: PlayerConfig())
    service.active = WebPlaybackSession(
        id="session", episode_id=7, media_file_id=8, directory=Path("/tmp/not-used"),
        process=SimpleNamespace(returncode=0), start_seconds=0, initial_position_seconds=120,
        duration_seconds=1000,
    )

    await service.progress("session", 30, 880)

    assert states.recorded == (7, 8, 30, 1000, False)


def test_explicit_web_seek_can_move_before_resume_position() -> None:
    assert _resolve_start_seconds(600, 1200, from_start=False, position_seconds=120) == 120
    assert _resolve_start_seconds(600, 1200, from_start=False, position_seconds=900) == 900
    assert _resolve_start_seconds(600, 1200, from_start=True, position_seconds=None) == 0


def test_explicit_web_seek_is_bounded_by_media_duration() -> None:
    assert _resolve_start_seconds(0, 1200, from_start=False, position_seconds=1500) == 1199.9
