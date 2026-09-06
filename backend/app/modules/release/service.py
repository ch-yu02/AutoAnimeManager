from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from backend.app.config import ReleaseSearchConfig, get_settings
from backend.app.database.models import (
    DownloadJob,
    Episode,
    EpisodeFile,
    MediaFile,
    ReleaseCandidate,
    ReleaseSearch,
    Subject,
)
from backend.app.database.session import session_scope
from backend.app.modules.download.service import DownloadService
from backend.app.modules.library.matcher import episode_number_candidates, subject_scope_numbers
from backend.app.modules.release.provider import ReleaseProvider, ReleaseProviderError
from backend.app.modules.release_preferences import (
    automatic_preference_rank,
    group_keys,
    is_ani_group,
    is_preferred_fansub,
    media_release_group,
)
from backend.app.modules.release.scorer import aliases_from_json, score_release


class ReleaseSearchNotFound(LookupError):
    pass


class ReleaseCandidateNotFound(LookupError):
    pass


class ReleaseNotDownloadable(RuntimeError):
    pass


class ReleaseSearchService:
    def __init__(
        self,
        provider: ReleaseProvider,
        download_service: DownloadService,
        settings_provider=get_settings,
    ) -> None:
        self.provider = provider
        self.download_service = download_service
        self.settings_provider = settings_provider

    async def search(self, episode_id: int) -> dict[str, object]:
        target = self._target(episode_id)
        config: ReleaseSearchConfig = self.settings_provider().release_search
        try:
            raw_releases = await self.provider.search(target["subject_names"], target["episode_number"])
        except ReleaseProviderError:
            raise
        existing_hashes = self._existing_hashes()
        scored = []
        seen_hashes: set[str] = set()
        for raw in raw_releases:
            result = score_release(
                raw,
                subject_names=target["subject_names"],
                episode_number=target["episode_number"],
                episode_numbers=target["episode_numbers"],
                subject_seasons=target["subject_seasons"],
                subject_parts=target["subject_parts"],
                config=config,
                existing_hashes=existing_hashes,
            )
            if result.magnet_hash and result.magnet_hash in seen_hashes:
                continue
            if result.magnet_hash:
                seen_hashes.add(result.magnet_hash)
            scored.append(result)
        scored.sort(key=lambda item: (item.score, item.parsed.raw.published_at or datetime.min.replace(tzinfo=UTC)), reverse=True)

        search_id = str(uuid.uuid4())
        with session_scope() as session:
            session.add(ReleaseSearch(
                id=search_id,
                episode_id=episode_id,
                provider=self.provider.name,
                query=str(target["query"]),
            ))
            for result in scored:
                parsed = result.parsed
                raw = parsed.raw
                session.add(ReleaseCandidate(
                    id=str(uuid.uuid4()),
                    search_id=search_id,
                    episode_id=episode_id,
                    provider=raw.provider or self.provider.name,
                    title=raw.title,
                    description=raw.description,
                    release_url=raw.release_url,
                    magnet_uri=raw.magnet_uri,
                    magnet_hash=result.magnet_hash,
                    published_at=raw.published_at,
                    author=raw.author,
                    category=raw.category,
                    normalized_title=parsed.normalized_title,
                    release_group=parsed.release_group,
                    season=parsed.season,
                    part=parsed.part,
                    episode_start=parsed.episode_start,
                    episode_end=parsed.episode_end,
                    subtitle_language=parsed.subtitle_language,
                    resolution=parsed.resolution,
                    codec=parsed.codec,
                    is_batch=parsed.is_batch,
                    size_bytes=parsed.size_bytes,
                    score=result.score,
                    decision=result.decision,
                    match_reasons=json.dumps(result.match_reasons, ensure_ascii=False),
                    reject_reasons=json.dumps(result.reject_reasons, ensure_ascii=False),
                    duplicate=result.duplicate,
                ))
        return self.get_search(search_id)

    def get_search(self, search_id: str) -> dict[str, object]:
        with session_scope() as session:
            search = session.get(ReleaseSearch, search_id)
            if search is None:
                raise ReleaseSearchNotFound("资源搜索记录不存在")
            episode = session.get(Episode, search.episode_id)
            candidates = list(session.scalars(
                select(ReleaseCandidate)
                .where(ReleaseCandidate.search_id == search.id)
                .order_by(
                    ReleaseCandidate.score.desc(),
                    ReleaseCandidate.published_at.desc(),
                    ReleaseCandidate.created_at,
                    ReleaseCandidate.id,
                )
            ))
            visible_candidates = [candidate for candidate in candidates if candidate.decision != "REJECT"]
            return {
                "id": search.id,
                "episode_id": search.episode_id,
                "provider": search.provider,
                "query": search.query,
                "created_at": search.created_at,
                "episode": {
                    "id": episode.id,
                    "display_number": episode.display_number,
                    "name": episode.name_cn or episode.name,
                } if episode else None,
                "candidates": [self._candidate_view(candidate) for candidate in visible_candidates],
                "rejected_count": len(candidates) - len(visible_candidates),
            }

    def auto_candidate(self, search_id: str) -> dict[str, object] | None:
        with session_scope() as session:
            search = session.get(ReleaseSearch, search_id)
            if search is None:
                raise ReleaseSearchNotFound("资源搜索记录不存在")
            episode = session.get(Episode, search.episode_id)
            if episode is None:
                return None
            candidates = list(session.scalars(
                select(ReleaseCandidate)
                .where(
                    ReleaseCandidate.search_id == search_id,
                    ReleaseCandidate.decision == "AUTO_ACCEPT",
                    ReleaseCandidate.duplicate.is_(False),
                    ReleaseCandidate.magnet_uri.is_not(None),
                    ReleaseCandidate.magnet_uri != "",
                )
            ))
            candidates = [
                candidate for candidate in candidates
                if self._meets_group_source_requirement(candidate)
            ]
            locked_groups = self._subject_release_groups(session, episode.subject_id)
            replacement_ids = self._ani_replacement_media_ids(session, episode)
            if locked_groups:
                candidates = [
                    candidate for candidate in candidates
                    if group_keys(candidate.release_group) & locked_groups
                ]
            elif replacement_ids:
                candidates = [
                    candidate for candidate in candidates
                    if is_preferred_fansub(candidate.release_group, candidate.subtitle_language)
                ]
            candidates.sort(
                key=lambda candidate: self._automatic_sort_key(
                    candidate,
                    prefer_ani=(
                        not locked_groups
                        and not replacement_ids
                        and not self._fansub_wait_elapsed(episode)
                    ),
                ),
                reverse=True,
            )
            candidate = candidates[0] if candidates else None
            return self._candidate_view(candidate) if candidate is not None else None

    def debug_auto_select(self, search_id: str) -> dict[str, object]:
        selected = self.auto_candidate(search_id)
        with session_scope() as session:
            candidates = list(session.scalars(
                select(ReleaseCandidate).where(ReleaseCandidate.search_id == search_id)
            ))
            for candidate in candidates:
                candidate.debug_selected_at = None
            if selected is not None:
                candidate = session.get(ReleaseCandidate, str(selected["id"]))
                if candidate is not None:
                    candidate.debug_selected_at = datetime.now(UTC)
        return self.get_search(search_id)

    async def download_candidate(
        self, candidate_id: str, *, automatic: bool = False
    ) -> dict[str, object]:
        with session_scope() as session:
            candidate = session.get(ReleaseCandidate, candidate_id)
            if candidate is None:
                raise ReleaseCandidateNotFound("资源候选不存在")
            if candidate.decision == "REJECT":
                raise ReleaseNotDownloadable("该候选已被判定为不匹配")
            if candidate.duplicate:
                raise ReleaseNotDownloadable("该候选已存在下载任务")
            if not candidate.magnet_uri:
                raise ReleaseNotDownloadable("该候选没有可用 magnet")
            episode_id = candidate.episode_id
            magnet_uri = candidate.magnet_uri
            episode = session.get(Episode, episode_id)
            replacement_ids = (
                self._ani_replacement_media_ids(session, episode)
                if automatic and episode is not None
                else []
            )
        if replacement_ids:
            download = await self.download_service.create(
                episode_id,
                magnet_uri,
                replacement_media_ids=replacement_ids,
            )
        else:
            download = await self.download_service.create(episode_id, magnet_uri)
        with session_scope() as session:
            candidate = session.get(ReleaseCandidate, candidate_id)
            if candidate is not None:
                candidate.selected_at = datetime.now(UTC)
                candidate.download_job_id = str(download["id"])
        return {"candidate_id": candidate_id, "download": download}

    @staticmethod
    def _target(episode_id: int) -> dict[str, object]:
        with session_scope() as session:
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise LookupError("Episode 不存在")
            subject = session.get(Subject, episode.subject_id)
            if subject is None:
                raise LookupError("Episode 对应条目不存在")
            episode_number = episode.sort_number
            if episode_number is None:
                try:
                    episode_number = float(episode.display_number)
                except ValueError:
                    episode_number = None
            names = [subject.name_cn, subject.name, *aliases_from_json(subject.aliases)]
            return {
                "query": subject.name_cn or subject.name,
                "episode_number": episode_number,
                "episode_numbers": episode_number_candidates(session, episode),
                "subject_names": names,
                "subject_seasons": subject_scope_numbers(subject, "season"),
                "subject_parts": subject_scope_numbers(subject, "part"),
            }

    @staticmethod
    def _existing_hashes() -> set[str]:
        with session_scope() as session:
            rows = session.execute(select(DownloadJob.magnet_hash, DownloadJob.torrent_hash))
            return {value for row in rows for value in row if value}

    @staticmethod
    def _subject_release_groups(session, subject_id: int) -> set[str]:
        groups: set[str] = set()
        for media in session.scalars(select(MediaFile).where(
                MediaFile.subject_id == subject_id,
                MediaFile.exists.is_(True),
                MediaFile.ignored.is_(False),
            )):
            raw_group = media_release_group(media.parse_result, media.filename)
            if not is_ani_group(raw_group):
                groups.update(group_keys(raw_group))
        return groups

    @staticmethod
    def _ani_replacement_media_ids(
        session, episode: Episode, *, today: date | None = None
    ) -> list[int]:
        if episode.air_date is None or episode.air_date > (today or date.today()) - timedelta(days=3):
            return []
        media = list(session.scalars(
            select(MediaFile)
            .join(EpisodeFile, EpisodeFile.media_file_id == MediaFile.id)
            .where(
                EpisodeFile.episode_id == episode.id,
                MediaFile.exists.is_(True),
                MediaFile.ignored.is_(False),
            )
        ))
        if not media or not all(
            is_ani_group(media_release_group(item.parse_result, item.filename)) for item in media
        ):
            return []
        return [item.id for item in media]

    @staticmethod
    def _fansub_wait_elapsed(episode: Episode, *, today: date | None = None) -> bool:
        return bool(
            episode.air_date is not None
            and episode.air_date <= (today or date.today()) - timedelta(days=3)
        )

    @staticmethod
    def _automatic_sort_key(
        candidate: ReleaseCandidate, *, prefer_ani: bool
    ) -> tuple[int, int, float, datetime]:
        published = candidate.published_at or datetime.min.replace(tzinfo=UTC)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        return (
            int(prefer_ani and is_ani_group(candidate.release_group)),
            automatic_preference_rank(candidate.release_group, candidate.subtitle_language),
            candidate.score,
            published,
        )

    @staticmethod
    def _meets_group_source_requirement(candidate: ReleaseCandidate) -> bool:
        if "黒ネズミたち" not in group_keys(candidate.release_group):
            return True
        return "baha" in candidate.title.casefold()

    @staticmethod
    def _candidate_view(candidate: ReleaseCandidate) -> dict[str, object]:
        return {
            "id": candidate.id,
            "search_id": candidate.search_id,
            "episode_id": candidate.episode_id,
            "provider": candidate.provider,
            "title": candidate.title,
            "description": candidate.description,
            "release_url": candidate.release_url,
            "magnet_uri": candidate.magnet_uri,
            "published_at": candidate.published_at,
            "author": candidate.author,
            "category": candidate.category,
            "parsed": {
                "normalized_title": candidate.normalized_title,
                "release_group": candidate.release_group,
                "season": candidate.season,
                "part": candidate.part,
                "episode_start": candidate.episode_start,
                "episode_end": candidate.episode_end,
                "subtitle_language": candidate.subtitle_language,
                "resolution": candidate.resolution,
                "codec": candidate.codec,
                "is_batch": candidate.is_batch,
                "size_bytes": candidate.size_bytes,
            },
            "score": candidate.score,
            "decision": candidate.decision,
            "match_reasons": _json_list(candidate.match_reasons),
            "reject_reasons": _json_list(candidate.reject_reasons),
            "duplicate": candidate.duplicate,
            "debug_selected_at": candidate.debug_selected_at,
            "selected_at": candidate.selected_at,
            "download_job_id": candidate.download_job_id,
            "downloadable": candidate.decision != "REJECT" and not candidate.duplicate and bool(candidate.magnet_uri),
        }


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed]
