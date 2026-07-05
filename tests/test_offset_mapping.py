"""Tests for mapping LanguageTool match offsets back to source lines.

LanguageTool reports offsets into the reconstructed plain text (the `text`
and `interpretAs` contributions). The client must translate an offset back to
the source-file line so findings print as `path:line`.
"""

from prose_check import (
    build_annotation,
    map_offset_to_line,
    reconstruct_text,
    to_lt_payload,
)


def test_offset_maps_to_source_line():
    md = "First line prose.\n\nSecond block here.\n"
    segs = build_annotation(md)
    recon = reconstruct_text(segs)
    assert map_offset_to_line(segs, recon.index("First line")) == 1
    assert map_offset_to_line(segs, recon.index("Second block")) == 3


def test_offset_maps_through_multiline_paragraph():
    # A single paragraph wrapped across two source lines (soft break).
    md = "This clause starts here\nand continues on line two.\n"
    segs = build_annotation(md)
    recon = reconstruct_text(segs)
    assert map_offset_to_line(segs, recon.index("continues")) == 2


def test_offset_maps_through_frontmatter():
    md = "---\ntitle: x\n---\n\nBody sentence here.\n"
    segs = build_annotation(md)
    recon = reconstruct_text(segs)
    assert map_offset_to_line(segs, recon.index("Body sentence")) == 5


def test_lt_payload_excludes_internal_keys():
    payload = to_lt_payload(build_annotation("Hello world.\n"))
    assert "annotation" in payload
    for item in payload["annotation"]:
        assert set(item).issubset({"text", "markup", "interpretAs"})
