from __future__ import annotations

import difflib
import json
import re

from backend.app.config import ReleaseSearchConfig
from backend.app.modules.download.magnet import InvalidMagnet, magnet_info_hash
from backend.app.modules.library.matcher import base_title
from backend.app.modules.library.parser import normalize_title
from backend.app.modules.release.parser import parse_release
from backend.app.modules.release.schemas import ParsedRelease, RawRelease, ScoredRelease


def score_release(
    raw: RawRelease,
    *,
    subject_names: list[str],
    episode_number: float | None,
    episode_numbers: dict[float, str] | None = None,
    subject_seasons: set[int] | None = None,
    subject_parts: set[int] | None = None,
    config: ReleaseSearchConfig,
    existing_hashes: set[str],
) -> ScoredRelease:
    parsed = parse_release(raw)
    reasons: list[str] = []
    rejects: list[str] = []
    score = 0.0

    title_score = _title_score(parsed.normalized_title, subject_names)
    if title_score >= 45:
        score += title_score
        reasons.append("条目标题匹配")
    elif title_score >= 30:
        score += title_score
        reasons.append("条目标题近似匹配，需要人工确认")
    else:
        rejects.append("条目标题不匹配")

    number_candidates = episode_numbers or (
        {episode_number: "Episode 编号匹配"} if episode_number is not None else {}
    )
    matched_number = next((
        (number, reason) for number, reason in number_candidates.items()
        if parsed.episode_start is not None
        and (
            abs(parsed.episode_start - number) < 0.001
            or (
                parsed.episode_end is not None
                and parsed.episode_start <= number <= parsed.episode_end
            )
        )
    ), None)
    if not number_candidates:
        rejects.append("目标 Episode 缺少集数")
    elif parsed.episode_start is None:
        rejects.append("资源标题无法解析集数")
    elif matched_number is not None:
        score += 25 if parsed.episode_end is not None else 30
        reasons.append(matched_number[1])
    else:
        expected = "/".join(f"{number:g}" for number in number_candidates)
        rejects.append(f"Episode 不匹配（资源为 {parsed.episode_start:g}，目标候选为 {expected}）")

    score += _scope_score("季度", parsed.season, subject_seasons or set(), reasons, rejects)
    score += _scope_score("Part", parsed.part, subject_parts or set(), reasons, rejects)

    score += _preference_score(parsed, config, reasons)
    if parsed.is_batch and not config.allow_batch:
        score -= 8
        reasons.append("批量资源需要人工确认")

    magnet_hash: str | None = None
    if raw.magnet_uri is None:
        rejects.append("没有可用 magnet")
    else:
        try:
            magnet_hash = magnet_info_hash(raw.magnet_uri)
        except InvalidMagnet:
            rejects.append("magnet 无法解析")
        else:
            if magnet_hash in existing_hashes:
                rejects.append("资源已存在下载任务")

    duplicate = magnet_hash is not None and magnet_hash in existing_hashes
    score = max(0.0, min(100.0, score))
    if rejects:
        decision = "REJECT"
    elif score >= 80:
        decision = "AUTO_ACCEPT"
    elif score >= 40:
        decision = "MANUAL_REVIEW"
    else:
        decision = "REJECT"
    return ScoredRelease(parsed, magnet_hash, score, decision, reasons, rejects, duplicate)


def _title_score(candidate: str, names: list[str]) -> float:
    candidate = normalize_title(candidate)
    candidate_base = base_title(candidate)
    best = 0.0
    for name in names:
        normalized = normalize_title(name)
        normalized_base = base_title(normalized)
        if not normalized:
            continue
        if candidate == normalized:
            best = max(best, 55.0)
        elif normalized in candidate or candidate in normalized:
            best = max(best, 48.0)
        else:
            best = max(best, difflib.SequenceMatcher(None, candidate, normalized).ratio() * 45.0)
        if candidate_base and normalized_base:
            if candidate_base == normalized_base:
                best = max(best, 48.0)
            elif candidate_base in normalized_base or normalized_base in candidate_base:
                best = max(best, 44.0)
    return best


def _scope_score(
    label: str,
    release_value: int | None,
    subject_values: set[int],
    reasons: list[str],
    rejects: list[str],
) -> float:
    if release_value is not None:
        if subject_values and release_value not in subject_values:
            rejects.append(f"{label}不匹配（资源为 {release_value}）")
            return 0
        if release_value > 1 and not subject_values:
            rejects.append(f"资源标注 {label} {release_value}，目标条目没有对应作用域")
            return 0
        if release_value in subject_values:
            reasons.append(f"{label}匹配")
            return 5
    elif subject_values and any(value > 1 for value in subject_values):
        reasons.append(f"资源未标注{label}，需要人工确认")
        return -15
    return 0


def _preference_score(parsed: ParsedRelease, config: ReleaseSearchConfig, reasons: list[str]) -> float:
    score = 0.0
    if config.preferred_groups:
        group = normalize_title(parsed.release_group or "")
        if any(normalize_title(item) in group or group in normalize_title(item) for item in config.preferred_groups):
            score += 10
            reasons.append("命中偏好字幕组")
    if config.preferred_language:
        if parsed.subtitle_language and _same_preference(parsed.subtitle_language, config.preferred_language):
            score += 8
            reasons.append("命中偏好语言")
    if config.preferred_resolution:
        if parsed.resolution and parsed.resolution.casefold() == config.preferred_resolution.casefold():
            score += 8
            reasons.append("命中偏好分辨率")
    if config.preferred_codec:
        if parsed.codec and parsed.codec.casefold() == config.preferred_codec.casefold():
            score += 8
            reasons.append("命中偏好编码")
    return score


def _same_preference(actual: str, preferred: str) -> bool:
    actual_parts = set(re.split(r"[+/, ]+", actual.casefold()))
    preferred_parts = set(re.split(r"[+/, ]+", preferred.casefold()))
    return bool(actual_parts & preferred_parts)


def aliases_from_json(value: str) -> list[str]:
    try:
        aliases = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in aliases if str(item).strip()]
