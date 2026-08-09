from __future__ import annotations

import re

from backend.app.modules.library.parser import parse_filename
from backend.app.modules.library.matcher import scope_number
from backend.app.modules.release.schemas import ParsedRelease, RawRelease


LANGUAGE_PATTERNS = (
    (re.compile(r"简繁|繁简|简体繁体|双语|(?:CHS|SC)\s*(?:&|\+|/|AND)\s*(?:CHT|TC)", re.I), "CHS+CHT"),
    (re.compile(r"简体|简中|(?<![A-Z])(?:CHS|SC)(?![A-Z])", re.I), "CHS"),
    (re.compile(r"繁体|繁中|(?<![A-Z])(?:CHT|TC)(?![A-Z])", re.I), "CHT"),
)
SIZE_PATTERN = re.compile(r"(?:file\s*size|size)\s*[:：]?\s*([\d.]+)\s*(KiB|MiB|GiB|KB|MB|GB)", re.I)


def parse_release(raw: RawRelease) -> ParsedRelease:
    # RSS titles commonly contain "中文名 / English Name"; Path-based library
    # parsing must not interpret that slash as a directory separator.
    parsed = parse_filename(raw.title.replace("/", "／").replace("\\", " "))
    text = f"{raw.title}\n{raw.description}"
    language = next(
        (value for pattern, value in LANGUAGE_PATTERNS if pattern.search(text)),
        None,
    )
    size_bytes = raw.size_bytes
    if size_bytes is None:
        match = SIZE_PATTERN.search(raw.description)
        if match:
            multiplier = {
                "kib": 1024,
                "mib": 1024**2,
                "gib": 1024**3,
                "kb": 1000,
                "mb": 1000**2,
                "gb": 1000**3,
            }[match.group(2).lower()]
            size_bytes = int(float(match.group(1)) * multiplier)
    is_batch = parsed.is_batch or bool(re.search(r"全集|全\d+话|全\d+集|BATCH|COMPLETE", text, re.I))
    return ParsedRelease(
        raw=raw,
        normalized_title=parsed.normalized_title,
        release_group=parsed.release_group,
        season=parsed.season,
        part=scope_number(raw.title, "part"),
        episode_start=parsed.episode_start,
        episode_end=parsed.episode_end,
        subtitle_language=language,
        resolution=parsed.resolution or _resolution_from_dimensions(raw.title),
        codec=_normalize_codec(parsed.codec),
        is_batch=is_batch,
        size_bytes=size_bytes,
    )


def _normalize_codec(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper().replace(".", "").replace("-", "")
    if normalized in {"H265", "X265", "HEVC"}:
        return "HEVC"
    if normalized in {"H264", "X264", "AVC"}:
        return "AVC"
    return normalized


def _resolution_from_dimensions(value: str) -> str | None:
    match = re.search(r"\b\d{3,5}\s*[x×]\s*(2160|1440|1080|720|576|480)\b", value, re.I)
    return f"{match.group(1)}p" if match else None
