"""Tests for source-line mapping via the per-block engine."""

from prose_check import combine_blocks, extract_blocks, line_for_offset


def _block_with(blocks, needle):
    return next(b for b in blocks if needle in b.text)


def test_block_base_line():
    blocks = extract_blocks("First line prose.\n\nSecond block here.\n")
    assert _block_with(blocks, "First line").base_line == 1
    assert _block_with(blocks, "Second block").base_line == 3


def test_multiline_paragraph_line():
    blocks = extract_blocks("This clause starts here\nand continues on line two.\n")
    block = blocks[0]
    assert block.line_of(block.text.index("continues")) == 2


def test_frontmatter_offsets_line():
    blocks = extract_blocks("---\ntitle: x\n---\n\nBody sentence here.\n")
    block = _block_with(blocks, "Body sentence")
    assert block.line_of(block.text.index("Body sentence")) == 5


def test_combined_offset_maps_to_source_line():
    md = "First line prose.\n\nSecond block here.\n"
    blocks = extract_blocks(md)
    combined, spans = combine_blocks(blocks)
    assert line_for_offset(spans, combined.index("First line")) == 1
    assert line_for_offset(spans, combined.index("Second block")) == 3
