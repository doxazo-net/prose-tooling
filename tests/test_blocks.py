"""Tests for prose-block extraction.

Markdown is split into prose blocks; markup (code, link URLs, table syntax,
frontmatter) must never appear in a block's checkable text.
"""

from prose_check import extract_blocks


def _joined(md):
    return " ".join(b.text for b in extract_blocks(md))


def test_prose_extracted():
    assert "This is a plain sentence." in _joined("This is a plain sentence.\n")


def test_fenced_code_block_excluded():
    joined = _joined("Real prose here.\n\n```\nteh brokn kode\n```\n")
    assert "Real prose here." in joined
    assert "brokn" not in joined
    assert "kode" not in joined


def test_inline_code_excluded():
    joined = _joined("Call the `teh_funktion` helper to proceed.\n")
    assert "Call the" in joined
    assert "teh_funktion" not in joined


def test_link_text_kept_url_excluded():
    joined = _joined("See the [documentation](https://example.com/teh-brokn) now.\n")
    assert "documentation" in joined
    assert "example.com" not in joined
    assert "brokn" not in joined


def test_yaml_frontmatter_excluded():
    joined = _joined("---\ntitle: teh brokn frontmatter\n---\n\nActual body prose.\n")
    assert "Actual body prose." in joined
    assert "brokn" not in joined


def test_gfm_table_syntax_excluded():
    md = "| Col | Val |\n|-----|-----|\n| foo | bar |\n\nRegular prose sentence.\n"
    joined = _joined(md)
    assert "Regular prose sentence." in joined
    # Table pipe/separator syntax must not become prose.
    assert "---" not in joined
    assert "|" not in joined
