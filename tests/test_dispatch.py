from prose_check import select_extractor


def test_dispatch_markdown_by_extension():
    assert select_extractor("docs/x.md", None) == "markdown"
    assert select_extractor("notes.txt", None) == "markdown"


def test_dispatch_i18n_by_extension():
    assert select_extractor("locales/en.json", None) == "i18n"


def test_explicit_format_overrides_extension():
    assert select_extractor("weird.dat", "i18n") == "i18n"
    assert select_extractor("en.json", "markdown") == "markdown"
