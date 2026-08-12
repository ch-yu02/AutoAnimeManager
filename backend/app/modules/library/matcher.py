from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from backend.app.database.models import Episode, EpisodeFile, MediaFile, Subject, SubjectRelation
from backend.app.modules.library.manifest import read_manifest
from backend.app.modules.library.parser import ParsedFilename, normalize_release_title, normalize_title


@dataclass(slots=True)
class MatchCandidate:
    subject: Subject
    confidence: float
    reasons: list[str]
    source: str


@dataclass(slots=True)
class EpisodeMatch:
    episode: Episode
    priority: int
    reason: str


def subject_titles(subject: Subject) -> set[str]:
    try:
        aliases = json.loads(subject.aliases)
    except (json.JSONDecodeError, TypeError):
        aliases = []
    values = [subject.name, subject.name_cn, *(aliases if isinstance(aliases, list) else [])]
    return {title for value in values if isinstance(value, str) and (title := normalize_title(value))}


def scope_number(value: str, kind: str) -> int | None:
    patterns = {
        "season": [
            r"\bs\s*(\d+)\b",
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


def base_title(value: str) -> str:
    """Remove season/part qualifiers so short release titles can reach split subjects."""
    value = re.sub(r"\bs\s*\d+\b|\bseason\s*\d+\b|\b\d+(?:st|nd|rd|th)\s+season\b", " ", value, flags=re.I)
    value = re.sub(r"\bpart\s*\d+\b|(?:第\s*)?\d+\s*(?:季|期|部|篇)|(?:第\s*)?[二三四五六七八九十]\s*(?:季|期)", " ", value, flags=re.I)
    value = re.sub(r"\bthe\s+movie\b|\bmovie\b|\bfilm\b|劇場版|剧场版|映画|电影", " ", value, flags=re.I)
    return normalize_title(value)


def _scope_is_compatible(parsed: ParsedFilename, title: str) -> bool:
    file_season = parsed.season or scope_number(parsed.normalized_title, "season")
    title_season = scope_number(title, "season")
    if file_season and file_season > 1 and title_season != file_season:
        return False
    file_part = scope_number(parsed.normalized_title, "part")
    title_part = scope_number(title, "part")
    return not file_part or title_part == file_part


def trailing_scope(value: str) -> int | None:
    match = re.search(r"\s(\d{1,2})$", value)
    if not match:
        return None
    prefix = value[:match.start()].rstrip()
    if re.search(r"\b(?:part|cour)$", prefix, re.I):
        return None
    return int(match.group(1))


def subject_scope_numbers(subject: Subject, kind: str) -> set[int]:
    values: set[int] = set()
    for title in subject_titles(subject):
        explicit = scope_number(title, kind)
        if explicit is not None:
            values.add(explicit)
            continue
        if kind == "season":
            trailing = trailing_scope(title)
            if trailing is not None and trailing <= 10:
                values.add(trailing)
    return values


def _directory_bangumi_id(path: Path) -> int | None:
    for parent in path.parents:
        match = re.search(r"(?:\[|\(|\b)bgm[-_ ]?(\d+)(?:\]|\)|\b)", parent.name, re.I)
        if match:
            return int(match.group(1))
    return None


def _title_candidates(session: Session, path: Path, parsed: ParsedFilename) -> list[MatchCandidate]:
    parent_names = [normalize_release_title(parent.name) for parent in list(path.parents)[:3]]
    source_titles = [(parsed.normalized_title, "文件名"), *((name, "父目录") for name in parent_names if name)]
    candidates: list[MatchCandidate] = []
    for subject in session.scalars(select(Subject).where(or_(Subject.collection_type.is_not(None), Subject.keep_forever.is_(True)))):
        titles = subject_titles(subject)
        file_season = parsed.season or scope_number(parsed.normalized_title, "season")
        if file_season and file_season > 1 and not any(
            scope_number(title, "season") == file_season or trailing_scope(title) == file_season
            for title in titles
        ):
            continue
        best = 0.0
        reason = ""
        for title in titles:
            title_season = scope_number(title, "season")
            if title_season and file_season and title_season != file_season:
                continue
            for source_title, source_name in source_titles:
                if not source_title:
                    continue
                exact_confidence = 1.0 if source_name == "文件名" else 0.91
                contains_confidence = 0.90
                if source_title == title and exact_confidence > best:
                    best, reason = exact_confidence, f"{source_name}标题完全匹配"
                elif title in source_title and contains_confidence > best:
                    best, reason = contains_confidence, f"{source_name}包含条目标题"
                source_base, title_base = base_title(source_title), base_title(title)
                if file_season and trailing_scope(title_base) == file_season:
                    title_base = re.sub(rf"\s{file_season}$", "", title_base)
                if source_base == title_base and len(source_base) >= 8 and 0.99 > best:
                    best, reason = 0.99, f"{source_name}标题基名完全匹配"
                if (
                    min(len(source_base), len(title_base)) >= 8
                    and (source_base == title_base or source_base in title_base or title_base in source_base)
                    and contains_confidence > best
                ):
                    best, reason = contains_confidence, f"{source_name}标题基名匹配"
                ratio = SequenceMatcher(None, title, source_title).ratio()
                ratio_confidence = ratio if source_name == "文件名" else min(0.91, ratio)
                if ratio >= 0.92 and ratio_confidence > best:
                    best, reason = ratio_confidence, f"{source_name}规范化标题高度相似"
        if best:
            candidates.append(MatchCandidate(subject, best, [reason], "TITLE_EPISODE"))
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def _main_episode_count(session: Session, subject_id: int) -> int:
    return int(session.scalar(
        select(func.count(Episode.id)).where(Episode.subject_id == subject_id, Episode.episode_type == "MAIN")
    ) or 0)


def prequel_main_count(session: Session, subject_id: int, visited: set[int] | None = None) -> int:
    visited = set() if visited is None else visited
    if subject_id in visited:
        return 0
    visited.add(subject_id)
    relation = session.scalar(
        select(SubjectRelation).where(
            SubjectRelation.subject_id == subject_id,
            SubjectRelation.relation_type.in_(("前传", "PREQUEL", "prequel")),
        ).limit(1)
    )
    if relation is None:
        return 0
    return prequel_main_count(session, relation.related_subject_id, visited) + _main_episode_count(
        session, relation.related_subject_id
    )


def episode_number_candidates(session: Session, episode: Episode) -> dict[float, str]:
    candidates: dict[float, str] = {}

    def add(value: float | int | None, reason: str) -> None:
        if value is not None:
            candidates.setdefault(float(value), reason)

    add(episode.sort_number, "Bangumi Episode 编号匹配")
    try:
        add(float(episode.display_number), "Bangumi Episode 显示编号匹配")
    except ValueError:
        pass
    main_episodes = list(session.scalars(select(Episode).where(
        Episode.subject_id == episode.subject_id,
        Episode.episode_type == "MAIN",
    )))
    ordered = sorted(
        main_episodes,
        key=lambda item: (item.sort_number is None, item.sort_number or 0, item.id),
    )
    ordinal = next((index for index, item in enumerate(ordered, start=1) if item.id == episode.id), None)
    add(ordinal, "季度内集数顺序匹配")
    offset = prequel_main_count(session, episode.subject_id)
    if offset and ordinal is not None:
        add(offset + ordinal, "按前作累计集数换算匹配")
    return candidates


def _episode_match(session: Session, subject_id: int, parsed: ParsedFilename) -> EpisodeMatch | None:
    if parsed.episode_start is None or parsed.episode_end is not None:
        return None
    desired_type = parsed.episode_type
    episodes = list(session.scalars(select(Episode).where(Episode.subject_id == subject_id)))
    compatible = [episode for episode in episodes if episode.episode_type == desired_type]
    if desired_type == "SPECIAL" and not compatible:
        compatible = [episode for episode in episodes if episode.episode_type != "MAIN"]
    for episode in compatible:
        if episode.sort_number is not None and abs(episode.sort_number - parsed.episode_start) < 0.001:
            return EpisodeMatch(episode, 3, "章节编号与类型直接匹配")
        try:
            if abs(float(episode.display_number) - parsed.episode_start) < 0.001:
                return EpisodeMatch(episode, 3, "章节显示编号与类型直接匹配")
        except ValueError:
            continue

    if desired_type != "MAIN" or not parsed.episode_start.is_integer():
        return None
    ordered = sorted(compatible, key=lambda episode: (episode.sort_number is None, episode.sort_number or 0, episode.id))
    number = int(parsed.episode_start)
    # Explicit season/part scope supports groups that restart numbering from 1.
    if parsed.season is not None or scope_number(parsed.normalized_title, "part") is not None:
        if 1 <= number <= len(ordered):
            return EpisodeMatch(ordered[number - 1], 2, "按季度内集数顺序匹配")
    # Unscoped releases may continue numbering across sequel subjects.
    offset = prequel_main_count(session, subject_id)
    local_number = number - offset
    if offset > 0 and 1 <= local_number <= len(ordered):
        return EpisodeMatch(ordered[local_number - 1], 2, "按前作累计集数换算匹配")
    return None


def _episode_for_number(session: Session, subject_id: int, parsed: ParsedFilename) -> Episode | None:
    match = _episode_match(session, subject_id, parsed)
    return match.episode if match else None


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
    if session.scalar(select(Subject.id).limit(1)) is None:
        media.review_reason = "METADATA_NOT_READY"
        media.subject_reasons = json.dumps(["尚未同步 Bangumi 条目与章节元数据"], ensure_ascii=False)
        return False
    candidates = _title_candidates(session, path, parsed)
    if not candidates:
        media.review_reason = "EPISODE_NOT_PARSED" if parsed.episode_start is None else "SUBJECT_NOT_FOUND"
        media.subject_reasons = json.dumps(["已同步的 Bangumi 收藏中没有可靠的标题候选"], ensure_ascii=False)
        return False
    episode_matches: dict[int, EpisodeMatch] = {}
    if parsed.episode_type == "MAIN" and parsed.episode_start is not None and parsed.episode_end is None:
        episode_matches = {
            candidate.subject.id: match
            for candidate in candidates
            if (match := _episode_match(session, candidate.subject.id, parsed)) is not None
        }
        if episode_matches:
            best_priority = max(match.priority for match in episode_matches.values())
            candidates = [
                candidate for candidate in candidates
                if (match := episode_matches.get(candidate.subject.id)) is not None and match.priority == best_priority
            ]
    if candidates[0].confidence < 0.90:
        media.review_reason = "LOW_CONFIDENCE"
        return False
    exact_filename_winner = (
        candidates[0].confidence == 1.0
        and candidates[0].reasons == ["文件名标题完全匹配"]
        and candidates[1].confidence < 1.0
    ) if len(candidates) > 1 else False
    if len(candidates) > 1 and candidates[0].confidence - candidates[1].confidence < 0.08 and not exact_filename_winner:
        media.review_reason = "AMBIGUOUS_SUBJECT"
        media.subject_reasons = json.dumps(
            [f"候选：{candidate.subject.name_cn or candidate.subject.name} ({candidate.confidence:.2f})" for candidate in candidates[:3]],
            ensure_ascii=False,
        )
        return False
    winner = candidates[0]
    if parsed.episode_type == "EXTRA":
        media.subject_id = winner.subject.id
        media.subject_mapping_source = winner.source
        media.subject_confidence = winner.confidence
        media.subject_reasons = json.dumps(winner.reasons + ["识别为非正片附加内容"], ensure_ascii=False)
        media.review_reason = "EXTRA_REQUIRES_REVIEW"
        return False
    episode_match = episode_matches.get(winner.subject.id) or _episode_match(session, winner.subject.id, parsed)
    episode = episode_match.episode if episode_match else None
    inferred_single_episode = False
    if episode is None and parsed.episode_start is None and parsed.episode_type == "MAIN":
        main_episodes = list(session.scalars(
            select(Episode).where(Episode.subject_id == winner.subject.id, Episode.episode_type == "MAIN")
        ))
        if winner.subject.total_main_episodes == 1 and len(main_episodes) == 1:
            episode = main_episodes[0]
            inferred_single_episode = True
    if episode is None:
        media.subject_id = winner.subject.id
        media.subject_mapping_source = winner.source
        media.subject_confidence = winner.confidence
        media.subject_reasons = json.dumps(winner.reasons, ensure_ascii=False)
        media.review_reason = "EPISODE_NOT_PARSED" if parsed.episode_start is None else "EPISODE_NOT_FOUND"
        return False
    reasons = winner.reasons + (
        ["单章节条目自动映射到唯一 MAIN 章节"]
        if inferred_single_episode
        else [episode_match.reason if episode_match else "章节编号与类型匹配"]
    )
    confidence = min(winner.confidence, 0.92) if inferred_single_episode else winner.confidence
    _replace_automatic_mapping(session, media, winner.subject, [episode], winner.source, confidence, reasons)
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
