from pathlib import Path
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select

from backend.app.config import PlayerConfig, get_settings
from backend.app.database.models import Episode, EpisodeFile, MediaFile, PlaybackState, Subject
from backend.app.database.session import get_engine, session_scope
from backend.app.modules.playback.state_service import PlaybackStateService


def _reset_caches() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _setup(tmp_path: Path, monkeypatch) -> tuple[PlaybackStateService, int, int, int]:
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'playback.db'}")
    _reset_caches()
    root = Path(__file__).resolve().parents[3]
    command.upgrade(Config(str(root / "alembic.ini")), "head")
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"video")
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=1, name="Anime", collection_type="DOING")
        session.add(subject)
        session.flush()
        episodes = []
        for number in (1, 2):
            episode = Episode(
                bangumi_episode_id=100 + number, subject_id=subject.id, episode_type="MAIN",
                sort_number=number, display_number=str(number), watched=False,
            )
            session.add(episode)
            session.flush()
            episodes.append(episode.id)
        media = MediaFile(
            path=str(video), filename=video.name, file_size=5, mtime_ns=1,
            last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
        for episode_id in episodes:
            session.add(EpisodeFile(
                episode_id=episode_id, media_file_id=media.id, mapping_source="MANUAL",
                confidence=1, is_primary=True,
            ))
        return PlaybackStateService(lambda: PlayerConfig()), episodes[0], episodes[1], media.id


def test_progress_threshold_completion_and_manual_override(tmp_path: Path, monkeypatch) -> None:
    service, episode_id, _, media_id = _setup(tmp_path, monkeypatch)
    service.begin(episode_id, media_id)

    short = service.record(episode_id, media_id, 30, 1000)
    valid = service.record(episode_id, media_id, 100, 1000)
    completed = service.record(episode_id, media_id, 750, 1000)

    assert short["position_seconds"] == 0
    assert valid["position_seconds"] == 100
    assert completed["watched"] is True
    service.mark_watched(episode_id, False)
    after_end = service.record(episode_id, media_id, 1000, 1000, ended=True)
    assert after_end["watched"] is False
    assert after_end["watched_source"] == "MANUAL"
    _reset_caches()


def test_next_episode_and_history_survive_missing_media(tmp_path: Path, monkeypatch) -> None:
    service, first_id, second_id, media_id = _setup(tmp_path, monkeypatch)
    service.begin(first_id, media_id)
    service.record(first_id, media_id, 120, 1000)
    resumed = service.begin(first_id, media_id)

    assert resumed["position_seconds"] == 120

    next_item = service.next_playable(first_id)
    assert next_item is not None and next_item[0].id == second_id
    with session_scope() as session:
        session.get(MediaFile, media_id).exists = False

    history = service.continue_watching()
    assert len(history) == 1
    assert history[0]["position_seconds"] == 120
    assert history[0]["playable"] is False
    with session_scope() as session:
        assert session.scalar(select(PlaybackState).where(PlaybackState.episode_id == first_id)) is not None
    _reset_caches()


def test_next_episode_does_not_skip_missing_immediate_episode(tmp_path: Path, monkeypatch) -> None:
    service, first_id, second_id, media_id = _setup(tmp_path, monkeypatch)
    with session_scope() as session:
        subject_id = session.get(Episode, first_id).subject_id
        third = Episode(
            bangumi_episode_id=103, subject_id=subject_id, episode_type="MAIN",
            sort_number=3, display_number="3", watched=False,
        )
        session.add(third)
        session.flush()
        third_id = third.id
        session.execute(delete(EpisodeFile).where(EpisodeFile.episode_id == second_id))
        session.add(EpisodeFile(
            episode_id=third_id, media_file_id=media_id, mapping_source="MANUAL",
            confidence=1, is_primary=True,
        ))

    assert service.next_playable(first_id) is None
    next_after_missing = service.next_playable(second_id)
    assert next_after_missing is not None and next_after_missing[0].id == third_id
    _reset_caches()
