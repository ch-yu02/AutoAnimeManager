from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database.models import DownloadJob, DownloadJobEpisode, Episode, EpisodeFile, MediaFile, Subject, TaskRun
from backend.app.database.session import get_engine, session_scope
from backend.app.modules.download.service import DownloadService, DuplicateDownload
from backend.app.modules.release.schemas import RawRelease
from backend.app.modules.release.service import ReleaseSearchService
from backend.app.modules.scheduler import AutoDownloadScheduler, DemandPlanner, SchedulerService


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


class FakeReleaseProvider:
    name = "fake"

    def __init__(self, magnet: str) -> None:
        self.magnet = magnet

    async def search(self, subject_names, episode_number):
        return [RawRelease(
            source_id="phase4-release",
            title="[TestGroup] 测试动画 - 01 [1080p][HEVC]",
            description="",
            release_url="https://example.test/phase4",
            magnet_uri=self.magnet,
            published_at=None,
            author="TestGroup",
            category="动画",
        )]


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
        assert episode.successfully_imported_at is not None
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
async def test_reconcile_all_times_out_one_job_without_blocking_others(
    tmp_path: Path, monkeypatch
) -> None:
    download, _, episode_id, second_episode_id = _prepare(tmp_path, monkeypatch)
    hanging_hash = "1" * 40
    healthy_hash = "2" * 40
    with session_scope() as session:
        first = session.get(Episode, episode_id)
        assert first is not None
        for job_id, torrent_hash, target_episode in (
            ("hanging-job", hanging_hash, episode_id),
            ("healthy-job", healthy_hash, second_episode_id),
        ):
            session.add(DownloadJob(
                id=job_id,
                magnet_uri="magnet:?xt=urn:btih:" + torrent_hash,
                magnet_hash=torrent_hash,
                torrent_hash=torrent_hash,
                subject_id=first.subject_id,
                save_path=str(download),
                state="DOWNLOADING",
            ))
            session.flush()
            session.add(DownloadJobEpisode(job_id=job_id, episode_id=target_episode))

    class PartiallyHangingQBittorrent(FakeQBittorrent):
        async def status(self, torrent_hash: str) -> dict[str, object]:
            if torrent_hash == hanging_hash:
                await asyncio.Event().wait()
            return {"hash": torrent_hash, "progress": 0.5, "state": "downloading"}

    service = DownloadService(
        adapter=PartiallyHangingQBittorrent([]),
        reconcile_timeout_seconds=0.05,
        sync_concurrency=2,
    )
    started = time.monotonic()

    result = await service.reconcile_all()

    assert time.monotonic() - started < 0.5
    assert result == {"processed": 2, "failed": 1}
    assert service.get("hanging-job")["state"] == "STALLED"
    assert "同步超时" in str(service.get("hanging-job")["error"])
    assert service.get("healthy-job")["state"] == "DOWNLOADING"
    assert service.get("healthy-job")["progress"] == 0.5
    await service.stop()
    _reset()


@pytest.mark.anyio
async def test_successful_replacement_deletes_old_ani_media_but_retains_job_history(
    tmp_path: Path, monkeypatch
) -> None:
    download, _, episode_id, _ = _prepare(tmp_path, monkeypatch)
    old_path = download / "[ANi] 测试动画 - 01.mkv"
    old_path.write_bytes(b"ani-video")
    replacement = download / "[字幕组] 测试动画 - 01 [CHS].mkv"
    replacement.write_bytes(b"fansub-video")
    old_hash = "8" * 40
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        media = MediaFile(
            path=str(old_path), filename=old_path.name, file_size=old_path.stat().st_size,
            mtime_ns=old_path.stat().st_mtime_ns, exists=True, ignored=False,
            subject_id=episode.subject_id, parse_result='{"release_group":"ANi"}',
            last_scanned_at=datetime.now(UTC),
        )
        session.add(media)
        session.flush()
        session.add(EpisodeFile(
            episode_id=episode.id, media_file_id=media.id, mapping_source="DOWNLOAD_JOB",
            confidence=1, is_primary=True,
        ))
        old_job = DownloadJob(
            id="old-ani-job", magnet_uri="magnet:?xt=urn:btih:" + old_hash,
            magnet_hash=old_hash, torrent_hash=old_hash, subject_id=episode.subject_id,
            save_path=str(download), state="IMPORTED", progress=1,
        )
        session.add(old_job)
        session.flush()
        session.add(DownloadJobEpisode(job_id=old_job.id, episode_id=episode.id))
        media_id = media.id
    adapter = FakeQBittorrent([
        {"name": replacement.name, "progress": 1, "priority": 1},
    ])
    service = DownloadService(adapter=adapter)

    created = await service.create(
        episode_id,
        "9" * 40,
        replacement_media_ids=[media_id],
    )
    result = await _terminal(service, str(created["id"]))
    await asyncio.sleep(0.05)

    assert result["state"] == "IMPORTED"
    assert not old_path.exists()
    assert replacement.exists()
    assert {item["torrent_hash"] for item in adapter.deleted} == {old_hash}
    assert all(item["delete_files"] is False for item in adapter.deleted)
    with session_scope() as session:
        assert session.get(DownloadJob, "old-ani-job") is not None
        old_link = session.scalar(select(DownloadJobEpisode).where(
            DownloadJobEpisode.job_id == "old-ani-job",
            DownloadJobEpisode.episode_id == episode_id,
        ))
        assert old_link is not None
        assert session.get(MediaFile, media_id) is None
        mapping = session.scalar(select(EpisodeFile).where(EpisodeFile.episode_id == episode_id))
        assert mapping is not None
        current = session.get(MediaFile, mapping.media_file_id)
        assert current is not None and current.filename == replacement.name
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


@pytest.mark.anyio
async def test_phase4_wanted_to_search_download_import_ready_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOANIME_SCHEDULER__AUTO_DOWNLOAD_ENABLED", "true")
    download, _, episode_id, _ = _prepare(tmp_path, monkeypatch)
    source = download / "[TestGroup] 测试动画 - 01 [1080p][HEVC].mkv"
    source.write_bytes(b"phase-four-video")
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        assert episode is not None
        episode.air_date = date.today()
        subject = session.get(Subject, episode.subject_id)
        assert subject is not None
        subject.collection_type = "DOING"

    magnet = "3456789abcdef0123456789abcdef0123456789a"
    adapter = FakeQBittorrent([{"name": source.name, "progress": 1, "priority": 1}])
    downloads = DownloadService(adapter=adapter)
    releases = ReleaseSearchService(FakeReleaseProvider(magnet), downloads, get_settings)
    workflow = AutoDownloadScheduler(releases, DemandPlanner())
    scheduler = SchedulerService()
    scheduler.register("ReleaseSearch", lambda: 300, workflow.run_once)

    run = await scheduler.run_task("ReleaseSearch")
    jobs = downloads.list()
    assert len(jobs) == 1
    result = await _terminal(downloads, str(jobs[0]["id"]))

    assert run["status"] == "SUCCESS"
    assert run["result"]["downloaded"] == 1
    assert result["state"] == "IMPORTED"
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        task_run = session.get(TaskRun, str(run["id"]))
        assert episode is not None and episode.local_status == "READY"
        assert episode.successfully_imported_at is not None
        assert task_run is not None and task_run.status == "SUCCESS"
    await downloads.stop()
    _reset()
