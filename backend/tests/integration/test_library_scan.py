import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import AppSettings, get_settings
from backend.app.database.models import Episode, EpisodeFile, LibraryScanRun, MediaFile, Subject
from backend.app.database.session import get_engine, session_scope
from backend.app.modules.library.scanner import LibraryScanner


def _reset_caches() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _migrate() -> None:
    root = Path(__file__).resolve().parents[3]
    command.upgrade(Config(str(root / "alembic.ini")), "head")


def _setup(tmp_path: Path, monkeypatch) -> tuple[Path, LibraryScanner]:
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'library.db'}")
    _reset_caches()
    _migrate()
    settings = AppSettings(
        database={"url": f"sqlite:///{tmp_path / 'library.db'}"},
        storage={"library_roots": [library], "ffprobe_enabled": False},
    )
    return library, LibraryScanner(lambda: settings)


def _metadata() -> tuple[int, int]:
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=100, name="Test Anime", name_cn="测试动画", collection_type="DOING")
        session.add(subject)
        session.flush()
        episode = Episode(
            bangumi_episode_id=1001, subject_id=subject.id, episode_type="MAIN",
            sort_number=1, display_number="1", name="Episode 1", name_cn="第一集",
        )
        session.add(episode)
        session.flush()
        return subject.id, episode.id


def test_scan_matches_moves_and_marks_deleted_file_missing(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    _, episode_id = _metadata()
    original = library / "Test Anime S01E01.mkv"
    original.write_bytes(b"video-content")

    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        assert media is not None
        media_id = media.id
        assert media.review_reason is None
        assert media.partial_hash
        assert session.scalar(select(EpisodeFile).where(EpisodeFile.episode_id == episode_id)) is not None
        assert session.get(Episode, episode_id).local_status == "READY"

    moved = library / "Test Anime S01E01 moved.mkv"
    original.rename(moved)
    task_id = scanner.scan()
    with session_scope() as session:
        media = session.get(MediaFile, media_id)
        assert media is not None and media.path == str(moved.resolve())
        run = session.get(LibraryScanRun, task_id)
        assert run is not None and run.moved_count == 1

    moved.unlink()
    scanner.scan()
    with session_scope() as session:
        media = session.get(MediaFile, media_id)
        assert media is not None and media.exists is False and media.review_reason == "MISSING"
        assert session.get(Episode, episode_id).local_status == "MISSING"
    _reset_caches()


def test_manifest_mapping_and_manual_lock_survive_rescan(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    subject_id, episode_id = _metadata()
    video = library / "unknown-file.mkv"
    video.write_bytes(b"first")
    (library / "manifest.json").write_text(json.dumps({
        "version": 1, "subject_id": 100,
        "files": [{"filename": video.name, "episode_id": 1001, "primary": True}],
    }), encoding="utf-8")

    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        mapping = session.scalar(select(EpisodeFile))
        assert media is not None and media.subject_id == subject_id
        assert mapping is not None and mapping.episode_id == episode_id
        assert media.subject_mapping_source == "MANIFEST"
        media.subject_mapping_source = "MANUAL"
        media.subject_manually_locked = True
        mapping.mapping_source = "MANUAL"
        mapping.manually_locked = True

    (library / "manifest.json").unlink()
    video.write_bytes(b"changed")
    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        mapping = session.scalar(select(EpisodeFile))
        assert media is not None and media.subject_mapping_source == "MANUAL"
        assert mapping is not None and mapping.mapping_source == "MANUAL"
    _reset_caches()


def test_explicit_second_season_only_matches_scoped_subject(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    with session_scope() as session:
        for bangumi_id, name in [(1, "Same Anime"), (2, "Same Anime 2nd Season")]:
            subject = Subject(bangumi_subject_id=bangumi_id, name=name, collection_type="DOING")
            session.add(subject)
            session.flush()
            session.add(Episode(
                bangumi_episode_id=bangumi_id * 100, subject_id=subject.id,
                episode_type="MAIN", sort_number=1, display_number="1",
            ))
    (library / "Same Anime 2nd Season S02E01.mkv").write_bytes(b"video")

    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        assert media is not None
        subject = session.get(Subject, media.subject_id)
        assert subject is not None and subject.name == "Same Anime 2nd Season"
        assert media.review_reason is None
    _reset_caches()


@pytest.mark.parametrize("filename", ["Same Anime 2nd Season S02E01.mkv", "Same Anime 第2期 S02E01.mkv"])
def test_single_base_subject_does_not_absorb_second_season(tmp_path: Path, monkeypatch, filename: str) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=1, name="Same Anime", collection_type="DOING")
        session.add(subject)
        session.flush()
        session.add(Episode(
            bangumi_episode_id=100, subject_id=subject.id, episode_type="MAIN",
            sort_number=1, display_number="1",
        ))
    (library / filename).write_bytes(b"video")

    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        assert media is not None and media.subject_id is None
        assert media.review_reason == "LOW_CONFIDENCE"
    _reset_caches()


def test_changed_file_drops_stale_unlocked_automatic_mapping(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    _, episode_id = _metadata()
    original = library / "Test Anime S01E01.mkv"
    original.write_bytes(b"video")
    scanner.scan()

    unknown = library / "unknown-file.mkv"
    original.rename(unknown)
    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        assert media is not None and media.subject_id is None
        assert media.review_reason == "EPISODE_NOT_PARSED"
        assert session.scalar(select(EpisodeFile).where(EpisodeFile.episode_id == episode_id)) is None
        assert session.get(Episode, episode_id).local_status == "MISSING"
    _reset_caches()


def test_cross_inode_move_falls_back_to_partial_hash(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    _metadata()
    original = library / "Test Anime S01E01.mkv"
    original.write_bytes(b"video")
    scanner.scan()
    with session_scope() as session:
        media_id = session.scalar(select(MediaFile.id))

    moved = library / "Test Anime S01E01 copied.mkv"
    moved.write_bytes(original.read_bytes())
    original.unlink()
    scanner.scan()
    with session_scope() as session:
        files = list(session.scalars(select(MediaFile)))
        assert len(files) == 1 and files[0].id == media_id
        assert files[0].path == str(moved.resolve())
    _reset_caches()


def test_malformed_manifest_is_not_silently_ignored(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    _metadata()
    (library / "Test Anime S01E01.mkv").write_bytes(b"video")
    (library / "manifest.json").write_text("{broken", encoding="utf-8")

    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        assert media is not None and media.subject_id is None
        assert media.review_reason == "MANIFEST_CONFLICT"
    _reset_caches()


def test_hardlinks_are_identified_separately_from_content_conflicts(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    _metadata()
    first = library / "Test Anime S01E01.mkv"
    second = library / "Test Anime S01E01 hardlink.mkv"
    first.write_bytes(b"video")
    second.hardlink_to(first)

    scanner.scan()
    with session_scope() as session:
        media = list(session.scalars(select(MediaFile)))
        assert len(media) == 2
        assert {item.review_reason for item in media} == {"HARDLINK_DUPLICATE"}
        assert len({(item.device_id, item.inode) for item in media}) == 1
        assert all(item.full_hash for item in media)
    _reset_caches()


def test_unsupported_video_like_file_enters_review(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    (library / "legacy-video.flv").write_bytes(b"video")

    scanner.scan()
    with session_scope() as session:
        media = session.scalar(select(MediaFile))
        assert media is not None and media.review_reason == "UNSUPPORTED_FORMAT"
        assert media.partial_hash is None
    _reset_caches()


def test_duplicate_primary_files_get_full_hash_and_review(tmp_path: Path, monkeypatch) -> None:
    library, scanner = _setup(tmp_path, monkeypatch)
    _metadata()
    (library / "Test Anime S01E01.mkv").write_bytes(b"same-video")
    (library / "Test Anime S01E01 copy.mkv").write_bytes(b"same-video")

    scanner.scan()
    with session_scope() as session:
        media = list(session.scalars(select(MediaFile).order_by(MediaFile.id)))
        assert len(media) == 2
        assert all(item.full_hash for item in media)
        assert {item.review_reason for item in media} == {"PRIMARY_FILE_CONFLICT"}
    _reset_caches()
