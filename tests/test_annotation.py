"""Tests for the Markdown -> LanguageTool data-annotation builder.

LanguageTool's /v2/check accepts a `data` payload that interleaves prose
(`text`) with markup (`markup`). Markup is ignored when looking for errors,
so Markdown syntax and code must be emitted as `markup`, never `text`.
"""

from prose_check import build_annotation


def _texts(segments):
    return [s["text"] for s in segments if "text" in s]


def test_prose_becomes_text_segment():
    md = "This is a plain sentence.\n"
    joined = " ".join(_texts(build_annotation(md)))
    assert "This is a plain sentence." in joined


def test_fenced_code_block_is_excluded_from_text():
    md = "Real prose here.\n\n```\nteh brokn kode lives here\n```\n"
    joined = " ".join(_texts(build_annotation(md)))
    assert "Real prose here." in joined
    # The mis-spelled code must never reach LanguageTool as prose.
    assert "brokn" not in joined
    assert "kode" not in joined


def test_inline_code_is_excluded_from_text():
    md = "Call the `teh_funktion` helper to proceed.\n"
    joined = " ".join(_texts(build_annotation(md)))
    assert "Call the" in joined
    assert "teh_funktion" not in joined


def test_link_url_excluded_but_text_kept():
    md = "See the [documentation](https://example.com/teh-brokn-slug) now.\n"
    joined = " ".join(_texts(build_annotation(md)))
    assert "documentation" in joined
    assert "example.com" not in joined
    assert "brokn" not in joined


def test_yaml_frontmatter_excluded():
    md = "---\ntitle: teh brokn frontmatter\n---\n\nActual body prose.\n"
    joined = " ".join(_texts(build_annotation(md)))
    assert "Actual body prose." in joined
    assert "brokn" not in joined
