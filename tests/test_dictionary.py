"""Tests for the client-side dictionary allowlist.

The free LanguageTool server has no per-request custom dictionary, so
allowlisted words (project nouns, names) are filtered out of spelling matches
client-side, using the flagged substring from the reconstructed text.
"""

from prose_check import filter_allowlisted


def _spell(offset, length):
    return {
        "rule": {"id": "MORFOLOGIK_RULE_EN_US", "category": {"id": "TYPOS"}},
        "offset": offset,
        "length": length,
    }


def test_allowlisted_spelling_is_dropped():
    recon = "We use Immich daily."
    matches = [_spell(recon.index("Immich"), len("Immich"))]
    assert filter_allowlisted(matches, recon, {"immich"}) == []


def test_allowlist_is_case_insensitive():
    recon = "Deploy with OrbStack now."
    matches = [_spell(recon.index("OrbStack"), len("OrbStack"))]
    assert filter_allowlisted(matches, recon, {"orbstack"}) == []


def test_non_allowlisted_spelling_survives():
    recon = "This has a mispeling."
    matches = [_spell(recon.index("mispeling"), len("mispeling"))]
    assert len(filter_allowlisted(matches, recon, {"immich"})) == 1


def test_non_spelling_match_is_never_filtered():
    recon = "We use Immich daily."
    grammar = {
        "rule": {"id": "SERIAL_COMMA_ON", "category": {"id": "STYLE"}},
        "offset": recon.index("Immich"),
        "length": len("Immich"),
    }
    assert filter_allowlisted([grammar], recon, {"immich"}) == [grammar]
