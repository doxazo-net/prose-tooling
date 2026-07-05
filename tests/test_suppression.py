from prose_check import extract_blocks, suppressed_lines


def _joined(md):
    return " ".join(b.text for b in extract_blocks(md))


def test_disable_line_suppresses_same_line():
    md = "This is teh checked line.\nThis has teh error. <!-- prose-lint-disable-line -->\n"
    joined = _joined(md)
    assert "This is teh checked line." in joined
    assert "This has teh error." not in joined


def test_disable_next_line_suppresses_following_line():
    md = "<!-- prose-lint-disable-next-line -->\nThis skipped line has teh error.\nThis one is checked.\n"
    joined = _joined(md)
    assert "This skipped line" not in joined
    assert "This one is checked." in joined


def test_disable_enable_region():
    md = "Before region.\n\n<!-- prose-lint-disable -->\n\nInside teh region.\n\n<!-- prose-lint-enable -->\n\nAfter region.\n"
    joined = _joined(md)
    assert "Before region." in joined
    assert "Inside" not in joined
    assert "After region." in joined


def test_suppressed_lines_set():
    md = "line one\nline two <!-- prose-lint-disable-line -->\nline three\n"
    assert suppressed_lines(md) == {2}
