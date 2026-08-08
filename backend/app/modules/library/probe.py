from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ProbeResult:
    duration_seconds: float | None = None
    video_codec: str | None = None
    resolution: str | None = None
    audio_languages: list[str] | None = None
    subtitle_languages: list[str] | None = None


def probe_media(path: Path, executable: str, enabled: bool = True) -> ProbeResult:
    resolved = shutil.which(executable)
    if not enabled or resolved is None:
        return ProbeResult(audio_languages=[], subtitle_languages=[])
    try:
        result = subprocess.run(
            [resolved, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height:stream_tags=language", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode != 0:
            return ProbeResult(audio_languages=[], subtitle_languages=[])
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return ProbeResult(audio_languages=[], subtitle_languages=[])
    video = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), {})
    audio = sorted({stream.get("tags", {}).get("language") for stream in payload.get("streams", []) if stream.get("codec_type") == "audio" and stream.get("tags", {}).get("language")})
    subtitles = sorted({stream.get("tags", {}).get("language") for stream in payload.get("streams", []) if stream.get("codec_type") == "subtitle" and stream.get("tags", {}).get("language")})
    duration = payload.get("format", {}).get("duration")
    width, height = video.get("width"), video.get("height")
    return ProbeResult(
        duration_seconds=float(duration) if duration is not None else None,
        video_codec=video.get("codec_name"),
        resolution=f"{width}x{height}" if width and height else None,
        audio_languages=audio,
        subtitle_languages=subtitles,
    )
