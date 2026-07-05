"""Tests for partitioning LanguageTool matches into blocking vs advisory.

The central severity map (config/<lang>/severity.toml) lists the rule IDs and
category IDs that fail a commit. Everything else is advisory (printed, exit 0).
"""

from prose_check import partition_matches


def _match(rule_id, category_id="MISC"):
    return {"rule": {"id": rule_id, "category": {"id": category_id}}}


def test_blocks_on_rule_id():
    matches = [_match("SERIAL_COMMA"), _match("PASSIVE_VOICE", "STYLE")]
    blocking, advisory = partition_matches(matches, {"SERIAL_COMMA"})
    assert [m["rule"]["id"] for m in blocking] == ["SERIAL_COMMA"]
    assert [m["rule"]["id"] for m in advisory] == ["PASSIVE_VOICE"]


def test_blocks_on_category_id():
    matches = [_match("MORFOLOGIK_RULE_EN_US", "TYPOS")]
    blocking, advisory = partition_matches(matches, {"TYPOS"})
    assert len(blocking) == 1
    assert advisory == []


def test_empty_blocking_set_is_all_advisory():
    # Phase-1 calibration: nothing blocks yet.
    matches = [_match("SERIAL_COMMA"), _match("PASSIVE_VOICE", "STYLE")]
    blocking, advisory = partition_matches(matches, set())
    assert blocking == []
    assert len(advisory) == 2
