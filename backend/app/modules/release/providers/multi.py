from __future__ import annotations

import asyncio
import logging

import httpx

from backend.app.modules.release.provider import ReleaseProvider, ReleaseProviderError
from backend.app.modules.release.providers.kisssub import KissSubRSSProvider
from backend.app.modules.release.schemas import RawRelease


logger = logging.getLogger(__name__)


class MultiRSSProvider:
    name = "multi_rss"

    def __init__(
        self,
        settings_provider,
        transport: httpx.AsyncBaseTransport | None = None,
        providers: list[ReleaseProvider] | None = None,
    ) -> None:
        self.settings_provider = settings_provider
        self.transport = transport
        self._fixed_providers = providers

    def _providers(self) -> list[ReleaseProvider]:
        if self._fixed_providers is not None:
            return self._fixed_providers
        config = self.settings_provider()
        providers: list[ReleaseProvider] = []
        for configured_source in config.sources:
            if not configured_source.enabled:
                continue
            source = configured_source
            # Preserve custom KissSub URLs from config files created before
            # release_search.sources existed.
            if source.name == "kisssub_rss":
                source = source.model_copy(update={
                    "rss_url": config.rss_url,
                    "rss_url_template": config.rss_url_template,
                })
            providers.append(KissSubRSSProvider(self.settings_provider, self.transport, source))
        return providers

    async def search(self, subject_names: list[str], episode_number: float | None) -> list[RawRelease]:
        providers = self._providers()
        if not providers:
            raise ReleaseProviderError("没有启用资源搜索来源")
        results = await asyncio.gather(
            *(provider.search(subject_names, episode_number) for provider in providers),
            return_exceptions=True,
        )
        feeds: list[list[RawRelease]] = []
        errors: list[str] = []
        for provider, result in zip(providers, results, strict=True):
            if isinstance(result, BaseException):
                if isinstance(result, (ReleaseProviderError, httpx.HTTPError, OSError)):
                    logger.warning("Release source %s unavailable: %s", provider.name, result)
                    errors.append(f"{provider.name}: {result}")
                    continue
                raise result
            feeds.append(result)
        if not feeds:
            raise ReleaseProviderError("所有资源来源均不可用：" + "; ".join(errors))
        return _interleave_unique(feeds, self.settings_provider().max_results)


def _interleave_unique(feeds: list[list[RawRelease]], limit: int) -> list[RawRelease]:
    unique: dict[str, RawRelease] = {}
    longest_feed = max((len(feed) for feed in feeds), default=0)
    for index in range(longest_feed):
        for feed in feeds:
            if index >= len(feed):
                continue
            release = feed[index]
            key = release.magnet_uri or release.release_url or f"{release.provider}:{release.source_id}"
            unique.setdefault(key, release)
            if len(unique) >= limit:
                return list(unique.values())
    return list(unique.values())
