"""Tests for client-side local rules.

Some house rules have no reliable free-server LanguageTool rule: em-dash usage
(no server rule exists) and one-space-after-sentence (not flagged by the free
server). These run client-side as deterministic regex rules, emitting matches
shaped like LanguageTool matches so the same offset/severity pipeline applies.
"""

from prose_check import build_annotation, local_matches, map_offset_to_line


def _ids(matches):
    return [m["rule"]["id"] for m in matches]


def test_flags_em_dash():
    matches = local_matches(build_annotation("This clause—an aside—ends.\n"))
    assert "LOCAL_EM_DASH" in _ids(matches)


def test_flags_double_space_after_sentence():
    matches = local_matches(build_annotation("Sentence one.  Sentence two.\n"))
    assert "LOCAL_DOUBLE_SPACE" in _ids(matches)


def test_clean_prose_has_no_local_matches():
    assert local_matches(build_annotation("A clean, tidy sentence here.\n")) == []


def test_paragraph_break_is_not_a_double_space_false_positive():
    # The reconstructed text joins blocks with "\n\n"; a period ending a
    # paragraph must NOT be read as a double space after the sentence.
    matches = local_matches(build_annotation("First para ends.\n\nSecond para.\n"))
    assert "LOCAL_DOUBLE_SPACE" not in _ids(matches)


def test_local_match_offset_maps_to_source_line():
    segs = build_annotation("Line one is fine.\n\nHere is an aside—really.\n")
    matches = local_matches(segs)
    em = next(m for m in matches if m["rule"]["id"] == "LOCAL_EM_DASH")
    assert map_offset_to_line(segs, em["offset"]) == 3
