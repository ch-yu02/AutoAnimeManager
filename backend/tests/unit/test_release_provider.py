from types import SimpleNamespace

import httpx
import pytest

from backend.app.config import ReleaseSearchConfig
from backend.app.modules.release.parser import parse_release
from backend.app.modules.release.providers.kisssub import KissSubRSSProvider
from backend.app.modules.release.schemas import RawRelease


RSS = '''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item>
<title><![CDATA[[TestGroup] 测试动画 / Test Anime - 06 (CR 1920x1080 HEVC AAC MKV)]]></title>
<link>http://www.kisssub.org/show-test.html</link>
<guid>http://www.kisssub.org/show-test.html</guid>
<description><![CDATA[File size : 1.5 GiB]]></description>
<author>TestGroup</author><pubDate>Sun, 09 Aug 2026 21:20:03 +0800</pubDate>
<category>动画</category>
<enclosure url="http://v2.uploadbt.com/?r=down&amp;hash=0123456789abcdef0123456789abcdef01234567" type="application/x-bittorrent" />
</item>
</channel></rss>'''.encode()


@pytest.mark.anyio
async def test_kisssub_provider_parses_rss_enclosure_and_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rss.xml"
        return httpx.Response(200, content=RSS)

    provider = KissSubRSSProvider(
        lambda: ReleaseSearchConfig(rss_url="https://rss.test/rss.xml", rss_url_template=""),
        transport=httpx.MockTransport(handler),
    )
    releases = await provider.search(["测试动画"], 6)

    assert len(releases) == 1
    assert releases[0].magnet_uri == "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    parsed = parse_release(releases[0])
    assert parsed.episode_start == 6
    assert parsed.resolution == "1080p"
    assert parsed.codec == "HEVC"
    assert parsed.size_bytes == int(1.5 * 1024**3)


def test_release_parser_reads_part_and_combined_chinese_subtitles() -> None:
    release = parse_release(RawRelease(
        source_id="part-2",
        title="[Group] Test Anime Part 2 - 06 [1080p][CHS&CHT]",
        description="",
        release_url="https://example.test/part-2",
        magnet_uri=None,
        published_at=None,
        author=None,
        category=None,
    ))

    assert release.part == 2
    assert release.subtitle_language == "CHS+CHT"


def test_release_parser_reads_simplified_japanese_bilingual_subtitles() -> None:
    release = parse_release(RawRelease(
        source_id="chs-jpn",
        title="[北宇治字幕组] Test Anime - 06 [1080p][CHS&JPN]",
        description="简日双语字幕",
        release_url="https://example.test/chs-jpn",
        magnet_uri=None,
        published_at=None,
        author=None,
        category=None,
    ))

    assert release.release_group == "北宇治字幕组"
    assert release.subtitle_language == "CHS+JPN"


@pytest.mark.anyio
async def test_kisssub_provider_builds_subject_specific_rss_url() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, content=RSS)

    provider = KissSubRSSProvider(
        lambda: ReleaseSearchConfig(rss_url_template="https://rss.test/rss-{query}.xml"),
        transport=httpx.MockTransport(handler),
    )
    await provider.search(["测试 动画"], 6)

    assert requested_urls == ["https://rss.test/rss-%E6%B5%8B%E8%AF%95%20%E5%8A%A8%E7%94%BB.xml"]


@pytest.mark.anyio
async def test_kisssub_provider_falls_back_to_aliases_and_deduplicates() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if "Primary" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=RSS)

    provider = KissSubRSSProvider(
        lambda: ReleaseSearchConfig(
            rss_url_template="https://rss.test/rss-{query}.xml",
            max_query_terms=3,
        ),
        transport=httpx.MockTransport(handler),
    )
    releases = await provider.search(["Primary Name", "中文别名", "Test Anime"], 6)

    assert len(requested_paths) == 3
    assert len(releases) == 1


@pytest.mark.anyio
async def test_kisssub_provider_keeps_seasonless_primary_title_within_query_limit() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, content=RSS)

    provider = KissSubRSSProvider(
        lambda: ReleaseSearchConfig(
            rss_url_template="https://rss.test/rss-{query}.xml",
            max_query_terms=3,
        ),
        transport=httpx.MockTransport(handler),
    )
    await provider.search([
        "超超超超超喜欢你的100个女朋友 第三季",
        "君のことが大大大大大好きな100人の彼女 第3期",
        "Kimi no Koto ga Dai Dai Dai Dai Daisuki na 100-nin no Kanojo 3",
    ], 25)

    assert requested_paths[0] == "/rss-超超超超超喜欢你的100个女朋友 第三季.xml"
    assert requested_paths[1] == "/rss-超超超超超喜欢你的100个女朋友.xml"
