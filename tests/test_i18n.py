from prose_check import extract_i18n


def test_values_extracted_keys_skipped():
    js = '{\n  "greeting.hello": "Welcome back to the app.",\n  "greeting.bye": "See you soon."\n}\n'
    blocks = extract_i18n(js)
    texts = [b.text for b in blocks]
    assert "Welcome back to the app." in texts
    assert "See you soon." in texts
    # Keys must never be checked.
    assert not any("greeting" in t for t in texts)


def test_value_line_numbers():
    js = '{\n  "a": "First value.",\n  "b": "Second value."\n}\n'
    blocks = extract_i18n(js)
    by_text = {b.text: b.base_line for b in blocks}
    assert by_text["First value."] == 2
    assert by_text["Second value."] == 3
