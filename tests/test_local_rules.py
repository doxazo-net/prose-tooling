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
