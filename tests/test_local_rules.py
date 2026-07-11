"""Tests for client-side local rules on a prose string."""

from prose_check import local_matches_text


def _ids(matches):
    return [m["rule"]["id"] for m in matches]


def test_flags_em_dash():
    assert "LOCAL_EM_DASH" in _ids(local_matches_text("This clause—an aside—ends."))


def test_flags_double_space_after_sentence():
    assert "LOCAL_DOUBLE_SPACE" in _ids(local_matches_text("Sentence one.  Sentence two."))


def test_clean_prose_has_no_local_matches():
    assert local_matches_text("A clean, tidy sentence here.") == []


def test_em_dash_offset_is_within_text():
    text = "Here is an aside—really."
    match = next(m for m in local_matches_text(text) if m["rule"]["id"] == "LOCAL_EM_DASH")
    assert text[match["offset"]] == "—"


def _british(matches):
    return [m for m in matches if m["rule"]["id"] == "LOCAL_BRITISH_SPELLING"]


def test_flags_british_spelling_languagetool_reports():
    # behaviour is flagged by LanguageTool but only advisory; we must catch it too.
    assert _british(local_matches_text("The behaviour was odd."))


def test_flags_british_spelling_languagetool_misses():
    # catalogue is accepted by LanguageTool's en-US dictionary -- the coverage gap.
    assert _british(local_matches_text("See the catalogue."))


def test_british_suggestion_is_american_spelling():
    match = _british(local_matches_text("The colour is nice."))[0]
    assert match["replacements"][0]["value"] == "color"


def test_british_offset_points_at_the_word():
    text = "We organise things."
    match = _british(local_matches_text(text))[0]
    assert text[match["offset"] : match["offset"] + match["length"]] == "organise"


def test_british_preserves_leading_capitalization():
    match = _british(local_matches_text("Colour matters."))[0]
    assert match["replacements"][0]["value"] == "Color"


def test_american_spelling_is_not_flagged():
    assert local_matches_text("The behavior and color of the catalog.") == []


def test_british_does_not_flag_substring_of_larger_word():
    # 'grey' is a substring of the standard-American 'greyhound'; whole-word match only.
    assert _british(local_matches_text("The greyhound ran fast.")) == []
    assert _british(local_matches_text("The grey sky."))  # but the bare word fires


def test_calibre_software_name_not_flagged():
    # 'Calibre' is the e-book software (product name), excluded via overrides;
    # it must not be flagged as the British spelling of 'caliber'.
    assert _british(local_matches_text("Calibre-Web syncs my calibre library.")) == []


def test_load_british_map_missing_file_raises(tmp_path):
    import pytest

    from prose_check import _load_british_map

    with pytest.raises(OSError):
        _load_british_map(tmp_path / "absent.txt")


def test_british_not_flagged_inside_identifier_token():
    # snake_case / digit-adjacent identifiers in prose are not whole words;
    # preserve the \b-on-\w semantics (no false-positive block on identifiers).
    assert _british(local_matches_text("The my_colour_var flag.")) == []
    assert _british(local_matches_text("Set colour2 here.")) == []
    assert _british(local_matches_text("The colour here."))  # bare word still fires


def test_load_british_map_empty_file_raises(tmp_path):
    import pytest

    from prose_check import _load_british_map

    p = tmp_path / "empty.txt"
    p.write_text("# only a comment, no pairs\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_british_map(p)
