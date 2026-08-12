from backend.app.config import ReleaseSearchConfig
from backend.app.modules.release.schemas import RawRelease
from backend.app.modules.release.scorer import score_release


def _release(title: str, magnet: str | None = "0123456789abcdef0123456789abcdef01234567") -> RawRelease:
    return RawRelease(
        source_id=title,
        title=title,
        description="",
        release_url="https://example.test/release",
        magnet_uri=f"magnet:?xt=urn:btih:{magnet}" if magnet else None,
        published_at=None,
        author="TestGroup",
        category="动画",
    )


def test_scorer_accepts_matching_episode_and_records_reasons() -> None:
    result = score_release(
        _release("[TestGroup] 测试动画 - 06 [1080p][HEVC][简繁]"),
        subject_names=["测试动画", "Test Anime"],
        episode_number=6,
        config=ReleaseSearchConfig(preferred_resolution="1080p", preferred_codec="HEVC"),
        existing_hashes=set(),
    )

    assert result.decision == "AUTO_ACCEPT"
    assert result.score >= 80
    assert "条目标题匹配" in result.match_reasons
    assert "Episode 编号匹配" in result.match_reasons
    assert result.parsed.subtitle_language == "CHS+CHT"


def test_scorer_rejects_wrong_episode_and_duplicate() -> None:
    magnet = "0123456789abcdef0123456789abcdef01234567"
    result = score_release(
        _release("[TestGroup] 测试动画 - 05 [1080p]", magnet),
        subject_names=["测试动画"],
        episode_number=6,
        config=ReleaseSearchConfig(),
        existing_hashes={magnet},
    )

    assert result.decision == "REJECT"
    assert result.duplicate is True
    assert any("Episode 不匹配" in reason for reason in result.reject_reasons)
    assert "资源已存在下载任务" in result.reject_reasons


def test_scorer_accepts_sequel_reset_and_continuous_episode_numbers() -> None:
    common = {
        "subject_names": ["Test Anime 2nd Season", "Test Anime"],
        "episode_number": 6,
        "episode_numbers": {6.0: "季度内集数顺序匹配", 18.0: "按前作累计集数换算匹配"},
        "subject_seasons": {2},
        "config": ReleaseSearchConfig(preferred_resolution="1080p"),
        "existing_hashes": set(),
    }

    reset = score_release(_release("[Group] Test Anime S2 - 06 [1080p]"), **common)
    continuous = score_release(
        _release("[Group] Test Anime S2 - 18 [1080p]", "89abcdef0123456789abcdef0123456789abcdef"),
        **common,
    )

    assert reset.decision == "AUTO_ACCEPT"
    assert "季度内集数顺序匹配" in reset.match_reasons
    assert "季度匹配" in reset.match_reasons
    assert continuous.decision == "AUTO_ACCEPT"
    assert "按前作累计集数换算匹配" in continuous.match_reasons


def test_scorer_rejects_cross_season_candidate() -> None:
    result = score_release(
        _release("[Group] Test Anime S2 - 06 [1080p]"),
        subject_names=["Test Anime"],
        episode_number=6,
        subject_seasons={1},
        config=ReleaseSearchConfig(),
        existing_hashes=set(),
    )

    assert result.decision == "REJECT"
    assert any("季度不匹配" in reason for reason in result.reject_reasons)


def test_scorer_respects_part_scope() -> None:
    result = score_release(
        _release("[Group] Test Anime Part 2 - 06 [1080p]"),
        subject_names=["Test Anime Part 1"],
        episode_number=6,
        subject_parts={1},
        config=ReleaseSearchConfig(),
        existing_hashes=set(),
    )

    assert result.parsed.part == 2
    assert result.decision == "REJECT"
    assert any("Part不匹配" in reason for reason in result.reject_reasons)
