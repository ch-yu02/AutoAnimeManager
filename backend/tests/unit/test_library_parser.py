from backend.app.modules.library.parser import normalize_release_title, normalize_title, parse_filename


def test_release_name_parses_group_episode_and_technical_tags() -> None:
    parsed = parse_filename("[Lilith-Raws] Kakkou no Iinazuke - 07 [Baha][WEB-DL][1080p][HEVC].mkv")

    assert parsed.release_group == "Lilith-Raws"
    assert parsed.episode_start == 7
    assert parsed.episode_end is None
    assert parsed.resolution == "1080p"
    assert parsed.codec == "HEVC"
    assert "kakkou no iinazuke" in parsed.normalized_title


def test_season_range_and_special_types_are_explicit() -> None:
    season = parse_filename("Anime 2nd Season S02E03.mkv")
    batch = parse_filename("Anime 01-12 Batch.mkv")
    special = parse_filename("Anime OVA 02 1080p.mkv")
    opening = parse_filename("Anime NCOP1.mkv")

    assert (season.season, season.episode_start) == (2, 3)
    assert (batch.episode_start, batch.episode_end, batch.is_batch) == (1, 12, True)
    assert (special.episode_type, special.episode_start) == ("SPECIAL", 2)
    assert opening.episode_type == "OP"


def test_normalization_keeps_season_markers_to_avoid_cross_season_merge() -> None:
    assert normalize_title("Anime") != normalize_title("Anime 2nd Season")


def test_bracketed_release_title_and_versioned_episode_are_cleaned() -> None:
    parsed = parse_filename("[Group][Ruri no Houseki][01v2][1080p][JPSC].mp4")

    assert parsed.episode_start == 1
    assert parsed.normalized_title == "ruri no houseki"
    assert normalize_release_title("[Group] Ruri no Houseki [Ma10p_1080p][x265_flac]") == "ruri no houseki"


def test_numeric_bonus_content_is_not_classified_as_main_episode() -> None:
    for filename in (
        "[Group][Anime][Menu][01][1080p].mkv",
        "[Group][Anime Audio Drama][01.3][720p].mp4",
        "[Group][Anime][Explosion][12][1080p].mkv",
        "[Group][Anime][Tokuten][02][1080p].mkv",
    ):
        assert parse_filename(filename).episode_type == "EXTRA"


def test_title_number_and_season_are_not_misread_as_batch_range() -> None:
    season = parse_filename("Romance Anime Season 2 - 13 [1080p].mp4")
    numbered_title = parse_filename("THE PROJECT U149 - 04v2 [1080p].mkv")

    assert (season.episode_start, season.is_batch) == (13, False)
    assert (numbered_title.episode_start, numbered_title.is_batch) == (4, False)


def test_standalone_short_season_marker_is_parsed_and_removed_from_title() -> None:
    parsed = parse_filename(
        "[KitaujiSub] Mushoku Tensei - S2 [08][WebRip][HEVC_AAC][CHS&CHT].mkv"
    )

    assert parsed.season == 2
    assert parsed.episode_start == 8
    assert parsed.normalized_title == "mushoku tensei"


def test_bare_padded_episode_and_fps_metadata_are_cleaned() -> None:
    bare = parse_filename("[Beatrice-Raws] Houseki no Kuni 01 [BDRip 1920x1080 x264 FLAC].mkv")
    fps = parse_filename("[Sakurato] Mushoku Tensei S2 [16][AVC 1080P][CHS@60FPS].mp4")

    assert (bare.episode_start, bare.normalized_title) == (1, "houseki no kuni")
    assert fps.normalized_title == "mushoku tensei"
