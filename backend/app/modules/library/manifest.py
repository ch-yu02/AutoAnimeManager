from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


MANIFEST_NAME = "manifest.json"


@dataclass(slots=True)
class ManifestMatch:
    subject_bangumi_id: int
    episode_bangumi_ids: list[int]
    primary: bool = True


@dataclass(slots=True)
class ManifestReadResult:
    match: ManifestMatch | None = None
    error: str | None = None


def read_manifest(video_path: Path) -> ManifestReadResult:
    path = video_path.parent / MANIFEST_NAME
    if not path.is_file():
        return ManifestReadResult()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            return ManifestReadResult(error="manifest 顶层结构无效")
        subject_id = int(payload.get("subject_id", payload.get("bangumi_subject_id")))
        entries = [
            item for item in payload["files"]
            if isinstance(item, dict) and item.get("filename", item.get("path")) == video_path.name
        ]
        if not entries:
            return ManifestReadResult()
        episode_ids: list[int] = []
        for entry in entries:
            if "episode_id" in entry:
                episode_ids.append(int(entry["episode_id"]))
            else:
                episode_ids.extend(int(value) for value in entry.get("bangumi_episode_ids", []))
        if not episode_ids:
            return ManifestReadResult(error=f"manifest 中 {video_path.name} 缺少 episode_id")
        primary = any(bool(entry.get("primary", True)) for entry in entries)
        return ManifestReadResult(ManifestMatch(subject_id, list(dict.fromkeys(episode_ids)), primary))
    except (OSError, ValueError, TypeError, KeyError, StopIteration, json.JSONDecodeError):
        return ManifestReadResult(error="manifest 无法解析")


def write_manifest(video_path: Path, subject_bangumi_id: int, episode_bangumi_ids: list[int], primary: bool) -> None:
    path = video_path.parent / MANIFEST_NAME
    payload: dict[str, object] = {"version": 1, "subject_id": subject_bangumi_id, "files": []}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(current, dict) and current.get("version") in (None, 1):
                payload = current
        except (OSError, json.JSONDecodeError):
            pass
    payload.pop("bangumi_subject_id", None)
    payload["subject_id"] = subject_bangumi_id
    stored_files = payload.get("files", [])
    if not isinstance(stored_files, list):
        stored_files = []
    files = [
        item for item in stored_files
        if isinstance(item, dict) and item.get("filename", item.get("path")) != video_path.name
    ]
    files.extend(
        {"filename": video_path.name, "episode_id": episode_id, "primary": primary}
        for episode_id in episode_bangumi_ids
    )
    payload["files"] = sorted(files, key=lambda item: str(item.get("filename", item.get("path", ""))))
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".manifest.", delete=False) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
