from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import re
from urllib.parse import parse_qs, quote, urlparse
import xml.etree.ElementTree as ET

import httpx

from backend.app.config import ReleaseSourceConfig
from backend.app.modules.download.magnet import InvalidMagnet, normalize_magnet
from backend.app.modules.library.matcher import base_title, scope_number
from backend.app.modules.release.provider import ReleaseProviderError
from backend.app.modules.release.schemas import RawRelease


class KissSubRSSProvider:
    name = "kisssub_rss"

    def __init__(
        self,
        settings_provider,
        transport: httpx.AsyncBaseTransport | None = None,
        source: ReleaseSourceConfig | None = None,
    ) -> None:
        self.settings_provider = settings_provider
        self.transport = transport
        self.source = source
        if source is not None:
            self.name = source.name

    async def search(self, subject_names: list[str], episode_number: float | None) -> list[RawRelease]:
        config = self.settings_provider()
        source = self.source
        rss_url = source.rss_url if source is not None else config.rss_url
        rss_url_template = source.rss_url_template if source is not None else config.rss_url_template
        terms = _search_terms(subject_names, config.max_query_terms)
        urls = (
            [_rss_url(rss_url, rss_url_template, term) for term in terms]
            if rss_url_template
            else [rss_url]
        )
        if not urls:
            raise ReleaseProviderError("条目名称为空，无法生成专属 RSS URL")
        client_kwargs = {
            "timeout": config.timeout,
            "follow_redirects": True,
            "headers": {"User-Agent": "AutoAnime/0.1 release search"},
            # Only sources marked use_proxy inherit HTTP_PROXY/HTTPS_PROXY.
            "trust_env": source.use_proxy if source is not None else False,
        }
        if self.transport is not None:
            client_kwargs["transport"] = self.transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            async def fetch(url: str) -> list[RawRelease]:
                response = await client.get(url)
                response.raise_for_status()
                return parse_rss(response.content, config.max_results, provider=self.name)

            results = await asyncio.gather(*(fetch(url) for url in urls), return_exceptions=True)

        feeds: list[list[RawRelease]] = []
        errors: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                if isinstance(result, (httpx.HTTPError, OSError, ReleaseProviderError)):
                    errors.append(str(result))
                    continue
                raise result
            feeds.append(result)
        if not feeds and errors:
            raise ReleaseProviderError(f"{self.name} 请求失败：{errors[-1]}")
        unique: dict[str, RawRelease] = {}
        longest_feed = max((len(feed) for feed in feeds), default=0)
        for index in range(longest_feed):
            for feed in feeds:
                if index < len(feed):
                    release = feed[index]
                    unique.setdefault(release.source_id, release)
                    if len(unique) >= config.max_results:
                        return list(unique.values())
        return list(unique.values())


def _search_terms(subject_names: list[str], limit: int) -> list[str]:
    names = list(dict.fromkeys(name.strip() for name in subject_names if name.strip()))
    if not names:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for name in names:
        without_arc = _without_season_arc(name)
        for term in (name, without_arc, base_title(without_arc)):
            key = term.casefold().strip()
            if key and key not in seen:
                seen.add(key)
                terms.append(term.strip())
    return terms[:limit]


def _without_season_arc(value: str) -> str:
    """Drop a named arc suffix only when a season scope already disambiguates the title."""
    if scope_number(value, "season") is None:
        return value
    return re.sub(r"\s+[^\s]{1,24}(?:篇|編)\s*$", "", value).strip()


def _rss_url(fallback_url: str, template: str, subject_name: str) -> str:
    if not template:
        return fallback_url
    if "{query}" not in template:
        raise ReleaseProviderError("release_search.rss_url_template 必须包含 {query}")
    query = quote(subject_name.strip(), safe="")
    if not query:
        raise ReleaseProviderError("条目名称为空，无法生成专属 RSS URL")
    return template.replace("{query}", query)


def parse_rss(
    content: bytes,
    max_results: int = 100,
    *,
    provider: str | None = None,
) -> list[RawRelease]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ReleaseProviderError("RSS 返回的 XML 无法解析") from exc

    releases: list[RawRelease] = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        title = _child_text(item, "title")
        link = _child_text(item, "link") or _child_text(item, "guid")
        if not title or not link:
            continue
        enclosure = next(
            (child for child in item if _local_name(child.tag) == "enclosure"),
            None,
        )
        enclosure_url = enclosure.attrib.get("url", "") if enclosure is not None else ""
        releases.append(
            RawRelease(
                source_id=_child_text(item, "guid") or link,
                title=title,
                description=_child_text(item, "description"),
                release_url=link,
                magnet_uri=_magnet_from_enclosure(enclosure_url),
                published_at=_parse_date(_child_text(item, "pubDate")),
                author=_child_text(item, "author") or None,
                category=_child_text(item, "category") or None,
                provider=provider,
            )
        )
        if len(releases) >= max_results:
            break
    return releases


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(parent: ET.Element, name: str) -> str:
    for child in parent:
        if _local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _magnet_from_enclosure(value: str) -> str | None:
    if not value:
        return None
    if value.lower().startswith("magnet:"):
        try:
            return normalize_magnet(value)[0]
        except InvalidMagnet:
            return None
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    possible_hashes = query.get("hash", []) + query.get("btih", []) + query.get("infohash", [])
    if not possible_hashes:
        possible_hashes = [value]
    for candidate in possible_hashes:
        try:
            return normalize_magnet(candidate)[0]
        except InvalidMagnet:
            continue
    return None
