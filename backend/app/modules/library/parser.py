from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


RELEASE_TAGS = {
    "1080p", "1080i", "720p", "2160p", "4k", "8bit", "10bit", "hi10p",
    "web", "webdl", "webrip", "bdrip", "bluray", "hdtv", "remux",
    "x264", "x265", "h264", "h265", "hevc", "avc", "av1", "aac", "flac",
    "mp4", "mkv", "chs", "cht", "sc", "tc", "gb", "big5",
}
PARSER_VERSION = 5
GROUP_PATTERN = re.compile(r"^\[([^]]+)]")
BRACKET_PATTERN = re.compile(r"[\[【(（]([^\]】)）]+)[\]】)）]")
RANGE_PATTERN = re.compile(
    r"(?<![\w])(\d{1,4}(?:\.\d+)?)\s*[-~～]\s*(\d{1,4}(?:\.\d+)?)"
    r"(?=\s*(?:[\]】]|BATCH\b|COMPLETE\b|全集|全\d+话|$))",
    re.I,
)
SE_PATTERN = re.compile(r"\bS(\d{1,2})\s*E(\d{1,4}(?:\.\d+)?)\b", re.I)
SEASON_PATTERN = re.compile(r"\b(?:S|SEASON\s*)0*(\d{1,2})\b(?!\s*E\d)", re.I)
EP_PATTERN = re.compile(r"\b(?:EP?|第)\s*0*(\d{1,4}(?:\.\d+)?)\s*(?:话|話|集)?\b", re.I)
DASH_EP_PATTERN = re.compile(r"(?:^|\s)[-–—]\s*0*(\d{1,4}(?:\.\d+)?)(?:v\d+)?(?:\s|$)", re.I)
BRACKET_EP_PATTERN = re.compile(r"[\[【]\s*0*(\d{1,3}(?:\.\d+)?)(?:v\d+)?\s*[\]】]", re.I)
BARE_EP_PATTERN = re.compile(r"\s(\d{2,3})(?:v\d+)?(?=\s*[\[【])", re.I)


@dataclass(slots=True)
class ParsedFilename:
    original: str
    normalized_title: str
    release_group: str | None = None
    resolution: str | None = None
    codec: str | None = None
    season: int | None = None
    episode_start: float | None = None
    episode_end: float | None = None
    episode_type: str = "MAIN"
    is_batch: bool = False
    parser_version: int = PARSER_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[_\.]+", " ", value)
    value = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", " ", value)
    return " ".join(value.split())


def _is_release_metadata(value: str) -> bool:
    normalized = normalize_title(value)
    compact = normalized.replace(" ", "")
    if not compact:
        return True
    if compact in RELEASE_TAGS:
        return True
    if re.search(r"(?:480|576|720|1080|2160|4320)[pi]", compact, re.I):
        return True
    if re.search(r"(?:ma\d+p|\d{3,4}x\d{3,4}|x26[45]|h26[45]|hevc|avc|av1)", compact, re.I):
        return True
    if re.search(r"\d+(?:fps|hz)", compact, re.I):
        return True
    if re.fullmatch(r"[0-9a-f]{8}", compact, re.I):
        return True
    if re.fullmatch(r"(?:chs?|cht|jpn|eng|jpsc|baha|end|aacx?\d*|flac|assx?\d*)+", compact, re.I):
        return True
    return normalized.startswith(("检索 ", "search "))


def normalize_release_title(value: str, *, remove_leading_group: bool = True) -> str:
    """Strip common release metadata while retaining bracketed anime titles."""
    title = unicodedata.normalize("NFKC", value)
    group_match = GROUP_PATTERN.search(title) if remove_leading_group else None
    if group_match:
        title = title[group_match.end():]
    for pattern in (SE_PATTERN, SEASON_PATTERN, RANGE_PATTERN, EP_PATTERN, DASH_EP_PATTERN, BRACKET_EP_PATTERN, BARE_EP_PATTERN):
        title = pattern.sub(" ", title)
    title = BRACKET_PATTERN.sub(lambda match: " " if _is_release_metadata(match.group(1)) else f" {match.group(1)} ", title)
    for tag in RELEASE_TAGS:
        title = re.sub(rf"\b{re.escape(tag)}\b", " ", title, flags=re.I)
    return normalize_title(title)


def _episode_type(stem: str) -> str:
    upper = unicodedata.normalize("NFKC", stem).upper()
    if re.search(
        r"(?:^|[^A-Z])(MENU|PREVIEW|AUDIO[ ._-]*DRAMA|PICTURE[ ._-]*DRAMA|"
        r"EXPLOSION|TOKUTEN|BONUS|IV\d+)(?:[^A-Z]|$)|特典|菜单|預告|预告",
        upper,
    ):
        return "EXTRA"
    if re.search(r"(?:^|[^A-Z])(NCOP|NC OP|OP)(?:\d+)?(?:[^A-Z]|$)", upper):
        return "OP"
    if re.search(r"(?:^|[^A-Z])(NCED|NC ED|ED)(?:\d+)?(?:[^A-Z]|$)", upper):
        return "ED"
    if re.search(r"(?:^|[^A-Z])(PV|CM)(?:\d+)?(?:[^A-Z]|$)", upper):
        return "PV"
    if re.search(r"(?:^|[^A-Z])(OVA|OAD|SP|SPECIAL)(?:\d+)?(?:[^A-Z]|$)", upper):
        return "SPECIAL"
    return "MAIN"


def parse_filename(path: str | Path) -> ParsedFilename:
    stem = Path(path).stem
    group_match = GROUP_PATTERN.search(stem)
    group = group_match.group(1).strip() if group_match else None
    resolution_match = re.search(r"\b(2160|1080|720|576|480)[pi]\b", stem, re.I)
    codec_match = re.search(r"\b(AV1|HEVC|H[ ._-]?265|X265|AVC|H[ ._-]?264|X264)\b", stem, re.I)
    season: int | None = None
    start: float | None = None
    end: float | None = None
    se_match = SE_PATTERN.search(stem)
    if se_match:
        season, start = int(se_match.group(1)), float(se_match.group(2))
    else:
        season_match = SEASON_PATTERN.search(stem)
        if season_match:
            season = int(season_match.group(1))
        range_match = RANGE_PATTERN.search(stem)
        if range_match:
            start, end = float(range_match.group(1)), float(range_match.group(2))
        else:
            match = (
                EP_PATTERN.search(stem) or DASH_EP_PATTERN.search(stem)
                or BRACKET_EP_PATTERN.search(stem) or BARE_EP_PATTERN.search(stem)
            )
            if match:
                start = float(match.group(1))

    episode_type = _episode_type(stem)
    special_number = re.search(r"\b(?:OVA|OAD|SP|SPECIAL|NCOP|NCED|OP|ED|PV)\s*0*(\d{1,3})\b", stem, re.I)
    if episode_type != "MAIN" and special_number:
        start = float(special_number.group(1))

    title = normalize_release_title(stem)
    if episode_type not in {"MAIN", "EXTRA"}:
        title = re.sub(r"\b(?:OVA|OAD|SP|SPECIAL|NCOP|NCED|OP|ED|PV|CM)\s*\d*\b", " ", title, flags=re.I)
    return ParsedFilename(
        original=Path(path).name,
        normalized_title=normalize_title(title),
        release_group=group,
        resolution=f"{resolution_match.group(1)}p" if resolution_match else None,
        codec=codec_match.group(1).upper().replace(" ", "").replace(".", "").replace("_", "").replace("-", "") if codec_match else None,
        season=season,
        episode_start=start,
        episode_end=end,
        episode_type=episode_type,
        is_batch=end is not None or bool(re.search(r"\b(?:BATCH|COMPLETE|全集|全\d+话)\b", stem, re.I)),
    )
