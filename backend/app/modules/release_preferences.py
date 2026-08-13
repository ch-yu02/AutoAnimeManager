from __future__ import annotations

import json
import re
from html import unescape

from backend.app.modules.library.parser import normalize_title, parse_filename


HAN_PATTERN = re.compile(r"[\u3400-\u9fff]")
GROUP_ALIASES = {
    "sakurato": "sakurato",
    "桜都字幕组": "sakurato",
    "樱都字幕组": "sakurato",
    "nekomoe kissaten": "nekomoe kissaten",
    "喵萌奶茶屋": "nekomoe kissaten",
    "studio greentea": "studio greentea",
    "绿茶字幕组": "studio greentea",
    "綠茶字幕組": "studio greentea",
    "kitaujisub": "kitaujisub",
    "北宇治字幕组": "kitaujisub",
    "北宇治字幕組": "kitaujisub",
}


def normalize_group(value: str | None) -> str:
    normalized = normalize_title(unescape(value or ""))
    return GROUP_ALIASES.get(normalized, normalized)


def group_keys(value: str | None) -> set[str]:
    parts = re.split(r"\s*(?:&|\+|/|／|×)\s*", unescape(value or ""))
    return {normalized for part in parts if (normalized := normalize_group(part))}


def is_ani_group(value: str | None) -> bool:
    return group_keys(value) == {"ani"}


def has_han_group(value: str | None) -> bool:
    return bool(value and HAN_PATTERN.search(value))


def preferred_subtitle(language: str | None) -> bool:
    return bool(language and "CHS" in language.upper().split("+"))


def automatic_preference_rank(group: str | None, language: str | None) -> int:
    """Rank built-in unattended-download preferences without rejecting manual choices."""
    normalized_language = (language or "").upper()
    score = 0
    if normalized_language == "CHS+JPN":
        score += 300
    elif preferred_subtitle(normalized_language):
        score += 200
    if has_han_group(group):
        score += 100
    return score


def is_preferred_fansub(group: str | None, language: str | None) -> bool:
    return not is_ani_group(group) and automatic_preference_rank(group, language) > 0


def media_release_group(parse_result: str, filename: str) -> str | None:
    try:
        parsed = json.loads(parse_result or "{}")
    except (json.JSONDecodeError, TypeError):
        parsed = {}
    group = parsed.get("release_group") if isinstance(parsed, dict) else None
    return str(group) if group else parse_filename(filename).release_group
