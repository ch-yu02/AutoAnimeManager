from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database.models import DownloadJob, DownloadJobEpisode, Episode, EpisodeFile, MediaFile, Subject
from backend.app.database.session import get_engine, session_scope
from backend.app.modules.download.service import DownloadService, DuplicateDownload


class FakeQBittorrent:
    def __init__(self, files: list[dict[str, object]], managed_files: list[Path] | None = None) -> None:
        self.file_list = files
        self.managed_files = managed_files or []
        self.added: list[dict[str, object]] = []
        self.deleted: list[dict[str, object]] = []
        self.paused = False

    async def add(self, magnet: str, **kwargs) -> None:
        self.added.append({"magnet": magnet, **kwargs})

    async def status(self, torrent_hash: str) -> dict[str, object]:
        return {"hash": torrent_hash, "progress": 1.0, "state": "uploading"}

    async def files(self, torrent_hash: str) -> list[dict[str, object]]:
        return self.file_list

    async def pause(self, torrent_hash: str) -> None:
        self.paused = True

    async def resume(self, torrent_hash: str) -> None:
        self.paused = False

    async def delete(self, torrent_hash: str, *, delete_files: bool = False) -> None:
        self.deleted.append({"torrent_hash": torrent_hash, "delete_files": delete_files})
        if delete_files:
            for path in self.managed_files:
                path.unlink(missing_ok=True)

    async def close(self) -> None:
        return None


def _reset() -> None:
    if get_engine.cache_info().currsize:
        # 导入器在线程池中使用 SQLite；测试切换临时数据库时不跨线程关闭连接。
        get_engine().dispose(close=False)
    get_engine.cache_clear()
    get_settings.cache_clear()


def _prepare(tmp_path: Path, monkeypatch) -> tuple[Path, Path, int, int]:
    library = tmp_path / "library"
    library.mkdir()
    subject_directory = library / "[bgm-42] 测试动画"
    subject_directory.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("AUTOANIME_STORAGE__LIBRARY_ROOTS", json.dumps([str(library)]))
    monkeypatch.setenv("AUTOANIME_STORAGE__FFPROBE_ENABLED", "false")
    _reset()
    root = Path(__file__).resolve().parents[3]
    command.upgrade(Config(str(root / "alembic.ini")), "head")
    with session_scope() as session:
        subject = Subject(bangumi_subject_id=42, name="Test Anime", name_cn="测试动画")
        session.add(subject)
        session.flush()
        first = Episode(
            bangumi_episode_id=4201, subject_id=subject.id, episode_type="MAIN",
            sort_number=1, display_number="1", name="Episode 1",
        )
        second = Episode(
            bangumi_episode_id=4202, subject_id=subject.id, episode_type="MAIN",
            sort_number=2, display_number="2", name="Episode 2",
        )
        session.add_all([first, second])
        session.flush()
        return subject_directory, library, first.id, second.id


async def _terminal(service: DownloadService, job_id: str) -> dict[str, object]:
    for _ in range(100):
        result = service.get(job_id)
        if result["state"] in {"IMPORTED", "FAILED"}:
            return result
        await asyncio.sleep(0.02)
    raise AssertionError("下载导入未在预期时间内完成")


@pytest.mark.anyio
async def test_completed_download_is_registered_in_place(tmp_path: Path, monkeypatch) -> None:
    download, library, episode_id, second_episode_id = _prepare(tmp_path, monkeypatch)
    source = download / "[Group] Test Anime - 01.mkv"
    source.write_bytes(b"video-data")
    adapter = FakeQBittorrent([{"name": source.name, "progress": 1, "priority": 1}])
    service = DownloadService(adapter=adapter)
    magnet = "0123456789ABCDEF0123456789ABCDEF01234567"

    created = await asyncio.wait_for(service.create(episode_id, magnet), timeout=5)
    result = await _terminal(service, str(created["id"]))

    assert result["state"] == "IMPORTED"
    with session_scope() as session:
        job = session.get(DownloadJob, result["id"])
        mapping = session.scalar(select(EpisodeFile).where(EpisodeFile.episode_id == episode_id))
        media = session.get(MediaFile, mapping.media_file_id) if mapping else None
        episode = session.get(Episode, episode_id)
        assert job is not None and job.imported_at is not None
        assert mapping is not None and mapping.mapping_source == "DOWNLOAD_JOB" and mapping.manually_locked
        assert media is not None and media.subject_mapping_source == "DOWNLOAD_JOB"
        assert episode is not None and episode.local_status == "READY"
        target = Path(media.path)
    assert target == source.resolve()
    assert json.loads((target.parent / "manifest.json").read_text(encoding="utf-8"))["subject_id"] == 42
    assert adapter.added[0]["tags"] == ["bgm-42", f"job-{result['id']}"]
    assert adapter.added[0]["magnet"] == "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"

    with pytest.raises(DuplicateDownload):
        await service.create(second_episode_id, magnet)

    await service.reconcile(str(result["id"]))
    assert service.get(str(result["id"]))["state"] == "IMPORTED"
    assert adapter.deleted == []
    await service.stop()
    _reset()


@pytest.mark.anyio
async def test_mismatched_download_enters_library_review(tmp_path: Path, monkeypatch) -> None:
    download, library, episode_id, _ = _prepare(tmp_path, monkeypatch)
    first = download / "Test Anime - 01.mkv"
    second = download / "Test Anime - 02.mkv"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    adapter = FakeQBittorrent([
        {"name": first.name, "progress": 1, "priority": 1},
        {"name": second.name, "progress": 1, "priority": 1},
    ])
    service = DownloadService(adapter=adapter)

    created = await asyncio.wait_for(service.create(
        episode_id, "magnet:?xt=urn:btih:89abcdef0123456789abcdef0123456789abcdef"
    ), timeout=5)
    result = await _terminal(service, str(created["id"]))

    assert result["state"] == "FAILED"
    assert "媒体库审核" in str(result["error"])
    with session_scope() as session:
        review_files = list(
            session.scalars(select(MediaFile).where(MediaFile.review_reason == "DOWNLOAD_EPISODE_COUNT_MISMATCH"))
        )
        assert len(review_files) == 2
        assert session.scalar(select(EpisodeFile).where(EpisodeFile.episode_id == episode_id)) is None
    assert {Path(item.path) for item in review_files} == {first.resolve(), second.resolve()}
    deleted = await service.delete(str(result["id"]), delete_files=False)
    assert deleted == {"id": result["id"], "deleted": True, "delete_files": False}
    assert service.list() == []
    with session_scope() as session:
        assert session.get(DownloadJob, result["id"]) is None
        assert session.scalar(
            select(DownloadJobEpisode).where(DownloadJobEpisode.episode_id == episode_id)
        ) is None
    recreated = await service.create(
        episode_id, "magnet:?xt=urn:btih:89abcdef0123456789abcdef0123456789abcdef"
    )
    assert recreated["id"] != result["id"]
    assert (await _terminal(service, str(recreated["id"])))["state"] == "FAILED"
    await service.stop()
    _reset()


@pytest.mark.anyio
@pytest.mark.parametrize("delete_files", [False, True])
async def test_imported_download_delete_modes(tmp_path: Path, monkeypatch, delete_files: bool) -> None:
    download, _, episode_id, _ = _prepare(tmp_path, monkeypatch)
    source = download / "Test Anime - 01.mkv"
    source.write_bytes(b"imported-video")
    torrent_hash = "1111111111111111111111111111111111111111"
    adapter = FakeQBittorrent(
        [{"name": source.name, "progress": 1, "priority": 1}],
        managed_files=[source],
    )
    service = DownloadService(adapter=adapter)

    created = await service.create(episode_id, torrent_hash)
    result = await _terminal(service, str(created["id"]))
    await service.delete(str(result["id"]), delete_files=delete_files)

    assert adapter.deleted == [{"torrent_hash": torrent_hash, "delete_files": delete_files}]
    assert source.exists() is (not delete_files)
    assert service.list() == []
    with session_scope() as session:
        media = session.scalar(select(MediaFile).where(MediaFile.path == str(source.resolve())))
        episode = session.get(Episode, episode_id)
        assert (media is not None) is (not delete_files)
        assert episode is not None
        assert episode.local_status == ("READY" if not delete_files else "MISSING")
    await service.stop()
    _reset()


@pytest.mark.anyio
@pytest.mark.parametrize("delete_files", [False, True])
async def test_failed_download_delete_modes(tmp_path: Path, monkeypatch, delete_files: bool) -> None:
    download, _, episode_id, _ = _prepare(tmp_path, monkeypatch)
    residual = download / "partial.mkv"
    residual.write_bytes(b"partial")
    torrent_hash = "2222222222222222222222222222222222222222"
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        job = DownloadJob(
            id="failed-job",
            magnet_uri=f"magnet:?xt=urn:btih:{torrent_hash}",
            magnet_hash=torrent_hash,
            torrent_hash=torrent_hash,
            subject_id=episode.subject_id,
            qbittorrent_task=torrent_hash,
            progress=0.5,
            state="FAILED",
            save_path=str(download),
        )
        session.add(job)
        session.add(DownloadJobEpisode(job_id=job.id, episode_id=episode_id))
    adapter = FakeQBittorrent([], managed_files=[residual])
    service = DownloadService(adapter=adapter)

    await service.delete("failed-job", delete_files=delete_files)

    assert adapter.deleted == [{"torrent_hash": torrent_hash, "delete_files": delete_files}]
    assert residual.exists() is (not delete_files)
    assert service.list() == []
    await service.stop()
    _reset()


@pytest.mark.anyio
async def test_created_job_is_recovered_after_restart(tmp_path: Path, monkeypatch) -> None:
    download, _, episode_id, _ = _prepare(tmp_path, monkeypatch)
    source = download / "Test Anime - 01.mkv"
    source.write_bytes(b"restart-video")
    torrent_hash = "fedcba9876543210fedcba9876543210fedcba98"
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        job = DownloadJob(
            id="restart-job",
            magnet_uri=f"magnet:?xt=urn:btih:{torrent_hash}",
            magnet_hash=torrent_hash,
            torrent_hash=torrent_hash,
            subject_id=episode.subject_id,
            qbittorrent_task=torrent_hash,
            progress=0,
            state="CREATED",
            save_path=str(download),
        )
        session.add(job)
        session.add(DownloadJobEpisode(job_id=job.id, episode_id=episode_id))
    adapter = FakeQBittorrent([{"name": source.name, "progress": 1, "priority": 1}])
    service = DownloadService(adapter=adapter)

    await service.reconcile_all()
    result = await _terminal(service, "restart-job")

    assert result["state"] == "IMPORTED"
    assert len(adapter.added) == 1
    await service.stop()
    _reset()
