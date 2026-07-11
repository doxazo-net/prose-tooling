"""Tests for the VarCon -> British/American corpus generator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

from gen_british_spellings import apply_overrides, parse_varcon, render


def test_british_only_word_is_mapped():
    varcon = "# behaviour (level 10)\nA Cv DV: behavior / B C D: behaviour\n"
    assert parse_varcon(varcon) == {"behaviour": "behavior"}


def test_american_variant_british_is_excluded():
    # grey carries AV (American variant) -> not blockable, must be dropped.
    varcon = "# gray (level 10)\nA Cv: gray / AV B C: grey\n"
    assert parse_varcon(varcon) == {}


def test_standard_american_word_excluded_via_block_aggregation():
    # dialogue is A (standard American) on one line; a later line pairs it
    # British. Block-level aggregation must still exclude it.
    varcon = (
        "# dialogue (level 20)\n"
        "A B: dialogue / AV: dialog\n"
        "A B Dv: dialog / Bv D: dialogue | <N> dialog box\n"
    )
    assert "dialogue" not in parse_varcon(varcon)


def test_level_cap_excludes_obscure_words():
    varcon = "# fantabulise (level 95)\nA Z: fantabulize / B: fantabulise\n"
    assert parse_varcon(varcon, level_cap=60) == {}
    assert parse_varcon(varcon, level_cap=95) == {"fantabulise": "fantabulize"}


def test_primary_american_form_chosen_as_suggestion():
    # colour's American is the primary 'A' token 'color'.
    varcon = "# color (level 10)\nA Cv DV: color / B C D: colour\n"
    assert parse_varcon(varcon)["colour"] == "color"


def test_override_add_forces_house_style_pair():
    m = {}
    apply_overrides(m, "+ catalogue catalog  # user-requested house style\n")
    assert m["catalogue"] == "catalog"


def test_override_remove_drops_false_positive():
    m = {"dialogue": "dialog"}
    apply_overrides(m, "- dialogue  # standard American, never block\n")
    assert "dialogue" not in m


def test_override_ignores_comments_and_blanks():
    m = {}
    apply_overrides(m, "# a comment\n\n+ grey gray\n")
    assert m == {"grey": "gray"}


def test_render_is_sorted_with_header_and_tabs():
    out = render({"colour": "color", "behaviour": "behavior"}, level_cap=60)
    lines = out.splitlines()
    assert lines[0].startswith("#")
    body = [ln for ln in lines if ln and not ln.startswith("#")]
    assert body == ["behaviour\tbehavior", "colour\tcolor"]


def test_main_aborts_when_corpus_implausibly_small(tmp_path):
    import pytest

    from gen_british_spellings import main

    varcon = tmp_path / "tiny.txt"
    varcon.write_text("# behaviour (level 10)\nA Cv DV: behavior / B C D: behaviour\n", encoding="latin-1")
    out = tmp_path / "out.txt"
    overrides = tmp_path / "ov.txt"  # absent on purpose
    with pytest.raises(SystemExit):
        main(["--varcon", str(varcon), "--out", str(out), "--overrides", str(overrides)])


def test_semantic_pair_rejected_by_orthographic_gate():
    # prev/perv is a slang clipping swap, not a spelling variant -- and would be
    # harmful in a blocking rule. It shares no 2-char prefix or suffix.
    varcon = "# perv (level 40)\nA: perv / B: prev\n"
    assert parse_varcon(varcon) == {}


def test_orthographic_gate_keeps_suffix_only_variant():
    # tyre/tire share only a 1-char prefix but a 2-char '-re' suffix -- kept.
    varcon = "# tire (level 40)\nA: tire / B: tyre\n"
    assert parse_varcon(varcon) == {"tyre": "tire"}


def test_apply_overrides_warns_on_malformed_line(capsys):
    from gen_british_spellings import apply_overrides

    m = {}
    apply_overrides(m, "+ only-one-token\n")
    assert m == {}
    assert "malformed override line" in capsys.readouterr().err
