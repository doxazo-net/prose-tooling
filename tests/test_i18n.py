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


def test_placeholders_are_masked():
    js = '{\n  "msg": "Could not ignore this group ({status}). Please retry."\n}\n'
    text = extract_i18n(js)[0].text
    assert "{status}" not in text
    assert "Could not ignore this group" in text
    assert "Please retry." in text


def test_printf_and_double_brace_masked():
    js = '{\n  "a": "Loaded %s of %d items.",\n  "b": "Hello {{name}} there."\n}\n'
    texts = [b.text for b in extract_i18n(js)]
    assert not any("%s" in t or "%d" in t for t in texts)
    assert not any("{{name}}" in t for t in texts)
