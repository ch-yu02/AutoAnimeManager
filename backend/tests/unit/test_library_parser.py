from backend.app.modules.library.parser import normalize_title, parse_filename


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
