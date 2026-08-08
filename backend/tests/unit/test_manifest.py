import json

from backend.app.modules.library.manifest import read_manifest, write_manifest


def test_manifest_reads_legacy_phase_two_format(tmp_path) -> None:
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"video")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "version": 1,
        "bangumi_subject_id": 10,
        "files": [{"path": video.name, "bangumi_episode_ids": [101, 102], "primary": False}],
    }), encoding="utf-8")

    result = read_manifest(video)

    assert result.error is None
    assert result.match is not None
    assert result.match.subject_bangumi_id == 10
    assert result.match.episode_bangumi_ids == [101, 102]
    assert result.match.primary is False


def test_manifest_writes_documented_format(tmp_path) -> None:
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"video")

    write_manifest(video, 10, [101, 102], True)
    payload = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert payload["subject_id"] == 10
    assert {entry["episode_id"] for entry in payload["files"]} == {101, 102}
    assert all(entry["filename"] == video.name for entry in payload["files"])
