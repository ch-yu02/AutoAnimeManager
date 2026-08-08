from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.database.models import Episode, EpisodeFile, MediaFile, Subject
from backend.app.modules.library.manifest import read_manifest
from backend.app.modules.library.parser import ParsedFilename, normalize_title


@dataclass(slots=True)
class MatchCandidate:
    subject: Subject
    confidence: float
    reasons: list[str]
    source: str


def _subject_titles(subject: Subject) -> set[str]:
    try:
        aliases = json.loads(subject.aliases)
    except (json.JSONDecodeError, TypeError):
        aliases = []
    values = [subject.name, subject.name_cn, *(aliases if isinstance(aliases, list) else [])]
    return {title for value in values if isinstance(value, str) and (title := normalize_title(value))}


def _scope_number(value: str, kind: str) -> int | None:
    patterns = {
        "season": [
            r"\bseason\s*(\d+)\b", r"\b(\d+)(?:st|nd|rd|th)\s+season\b",
            r"(?:第\s*)?(\d+)\s*(?:季|期)", r"(?:第\s*)?([二三四五六七八九十])\s*(?:季|期)",
            r"(?:第\s*)?(\d+)\s*シーズン", r"シーズン\s*(\d+)",
        ],
        "part": [r"\bpart\s*(\d+)\b", r"第\s*(\d+)\s*(?:部|篇)"],
    }
    chinese_numbers = {"二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    for pattern in patterns[kind]:
        match = re.search(pattern, value, re.I)
        if match:
            token = match.group(1)
            return int(token) if token.isdigit() else chinese_numbers.get(token)
    return None


def _scope_is_compatible(parsed: ParsedFilename, title: str) -> bool:
    file_season = parsed.season or _scope_number(parsed.normalized_title, "season")
    title_season = _scope_number(title, "season")
    if file_season and file_season > 1 and title_season != file_season:
        return False
    file_part = _scope_number(parsed.normalized_title, "part")
    title_part = _scope_number(title, "part")
    return not file_part or title_part == file_part


def _directory_bangumi_id(path: Path) -> int | None:
    for parent in path.parents:
        match = re.search(r"(?:\[|\(|\b)bgm[-_ ]?(\d+)(?:\]|\)|\b)", parent.name, re.I)
        if match:
            return int(match.group(1))
    return None


def _title_candidates(session: Session, path: Path, parsed: ParsedFilename) -> list[MatchCandidate]:
    parent_names = [normalize_title(parent.name) for parent in list(path.parents)[:3]]
    candidates: list[MatchCandidate] = []
    for subject in session.scalars(select(Subject)):
        best = 0.0
        reason = ""
        for title in _subject_titles(subject):
            if not _scope_is_compatible(parsed, title):
                continue
            if title in parent_names:
                best, reason = max(best, 0.96), "父目录标题完全匹配"
            if title and (parsed.normalized_title == title or title in parsed.normalized_title):
                best, reason = max(best, 0.93), "文件名包含条目标题"
            ratio = SequenceMatcher(None, title, parsed.normalized_title).ratio()
            if ratio >= 0.92 and ratio > best:
                best, reason = ratio, "规范化标题高度相似"
        if best:
            candidates.append(MatchCandidate(subject, best, [reason], "TITLE_EPISODE"))
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def _episode_for_number(session: Session, subject_id: int, parsed: ParsedFilename) -> Episode | None:
    if parsed.episode_start is None or parsed.episode_end is not None:
        return None
    desired_type = parsed.episode_type
    episodes = list(session.scalars(select(Episode).where(Episode.subject_id == subject_id)))
    compatible = [episode for episode in episodes if episode.episode_type == desired_type]
    if desired_type == "SPECIAL" and not compatible:
        compatible = [episode for episode in episodes if episode.episode_type != "MAIN"]
    for episode in compatible:
        if episode.sort_number is not None and abs(episode.sort_number - parsed.episode_start) < 0.001:
            return episode
        try:
            if abs(float(episode.display_number) - parsed.episode_start) < 0.001:
                return episode
        except ValueError:
            continue
    return None


def _replace_automatic_mapping(
    session: Session,
    media: MediaFile,
    subject: Subject,
    episodes: list[Episode],
    source: str,
    confidence: float,
    reasons: list[str],
    primary: bool = True,
) -> None:
    locked = list(session.scalars(select(EpisodeFile).where(EpisodeFile.media_file_id == media.id, EpisodeFile.manually_locked.is_(True))))
    if media.subject_manually_locked or locked:
        return
    session.execute(delete(EpisodeFile).where(EpisodeFile.media_file_id == media.id))
    media.subject_id = subject.id
    media.subject_mapping_source = source
    media.subject_confidence = confidence
    media.subject_reasons = json.dumps(reasons, ensure_ascii=False)
    media.review_reason = None
    for episode in episodes:
        session.add(EpisodeFile(
            episode_id=episode.id,
            media_file_id=media.id,
            mapping_source=source,
            confidence=confidence,
            reasons=json.dumps(reasons, ensure_ascii=False),
            is_primary=primary,
            manually_locked=False,
        ))


def match_media_file(session: Session, media: MediaFile, path: Path, parsed: ParsedFilename) -> bool:
    locked_mapping = session.scalar(
        select(EpisodeFile.id).where(
            EpisodeFile.media_file_id == media.id,
            EpisodeFile.manually_locked.is_(True),
        ).limit(1)
    )
    if media.ignored or media.subject_manually_locked or locked_mapping is not None:
        return bool(media.subject_id)

    # 文件发生变化时，旧的非锁定自动结果不再可信；失败分支必须留下未识别状态。
    session.execute(delete(EpisodeFile).where(EpisodeFile.media_file_id == media.id))
    media.subject_id = None
    media.subject_mapping_source = None
    media.subject_confidence = None
    media.subject_reasons = "[]"

    manifest_result = read_manifest(path)
    if manifest_result.error:
        media.review_reason = "MANIFEST_CONFLICT"
        media.subject_reasons = json.dumps([manifest_result.error], ensure_ascii=False)
        return False
    manifest = manifest_result.match
    if manifest:
        subject = session.scalar(select(Subject).where(Subject.bangumi_subject_id == manifest.subject_bangumi_id))
        episodes = list(session.scalars(select(Episode).where(Episode.bangumi_episode_id.in_(manifest.episode_bangumi_ids))))
        if subject and len(episodes) == len(manifest.episode_bangumi_ids) and all(ep.subject_id == subject.id for ep in episodes):
            _replace_automatic_mapping(session, media, subject, episodes, "MANIFEST", 1.0, ["manifest 明确指定条目与章节"], manifest.primary)
            return True
        media.review_reason = "MANIFEST_CONFLICT"
        return False

    directory_id = _directory_bangumi_id(path)
    if directory_id is not None:
        subject = session.scalar(select(Subject).where(Subject.bangumi_subject_id == directory_id))
        if subject:
            episode = _episode_for_number(session, subject.id, parsed)
            if episode:
                _replace_automatic_mapping(session, media, subject, [episode], "DIRECTORY_ID", 0.99, [f"目录指定 Bangumi #{directory_id}", "章节编号匹配"])
                return True
            media.subject_id = subject.id
            media.subject_mapping_source = "DIRECTORY_ID"
            media.subject_confidence = 0.99
            media.subject_reasons = json.dumps([f"目录指定 Bangumi #{directory_id}"], ensure_ascii=False)
            media.review_reason = "EPISODE_NOT_FOUND"
            return False

    if parsed.is_batch:
        media.review_reason = "BATCH_REQUIRES_REVIEW"
        return False
    if parsed.episode_start is None:
        media.review_reason = "EPISODE_NOT_PARSED"
        return False
    candidates = _title_candidates(session, path, parsed)
    if not candidates or candidates[0].confidence < 0.90:
        media.review_reason = "LOW_CONFIDENCE"
        return False
    if len(candidates) > 1 and candidates[0].confidence - candidates[1].confidence < 0.08:
        media.review_reason = "AMBIGUOUS_SUBJECT"
        media.subject_reasons = json.dumps(
            [f"候选：{candidate.subject.name_cn or candidate.subject.name} ({candidate.confidence:.2f})" for candidate in candidates[:3]],
            ensure_ascii=False,
        )
        return False
    winner = candidates[0]
    episode = _episode_for_number(session, winner.subject.id, parsed)
    if episode is None:
        media.review_reason = "EPISODE_NOT_FOUND"
        return False
    reasons = winner.reasons + ["章节编号与类型匹配"]
    _replace_automatic_mapping(session, media, winner.subject, [episode], winner.source, winner.confidence, reasons)
    return True


def refresh_episode_statuses(session: Session) -> None:
    episodes = list(session.scalars(select(Episode)))
    for episode in episodes:
        ready = session.scalar(
            select(EpisodeFile.id)
            .join(MediaFile, MediaFile.id == EpisodeFile.media_file_id)
            .where(EpisodeFile.episode_id == episode.id, MediaFile.exists.is_(True), MediaFile.ignored.is_(False))
            .limit(1)
        )
        episode.local_status = "READY" if ready is not None else "MISSING"
