from prose_check import extract_i18n, key_ignorer


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


def test_masking_does_not_manufacture_double_space():
    from prose_check import local_matches_text
    js = '{\n  "msg": "Done. {name} thanks."\n}\n'
    text = extract_i18n(js)[0].text
    assert "  " not in text  # no double space
    assert not any(m["rule"]["id"] == "LOCAL_DOUBLE_SPACE" for m in local_matches_text(text))


def test_glob_and_exact_key_ignored():
    js = (
        '{\n'
        '  "help.tooltip": "This teh tooltip is skipped.",\n'
        '  "audit.log_line": "Skipped teh log copy.",\n'
        '  "col.mbid": "MusicBrainz ID",\n'
        '  "body.text": "This regular copy is checked."\n'
        '}\n'
    )
    ignore = key_ignorer(["*.tooltip", "*.log_*", "col.mbid"])
    texts = [b.text for b in extract_i18n(js, ignore)]
    assert texts == ["This regular copy is checked."]


def test_nested_values_flattened_to_dotted_keys():
    js = (
        '{\n'
        '  "section": {\n'
        '    "title": "Nested value here.",\n'
        '    "sub": { "deep": "Deeply nested copy." }\n'
        '  }\n'
        '}\n'
    )
    texts = [b.text for b in extract_i18n(js)]
    assert "Nested value here." in texts
    assert "Deeply nested copy." in texts


def test_nested_keys_never_checked():
    js = '{\n  "greeting": { "hello": "Welcome back." }\n}\n'
    texts = [b.text for b in extract_i18n(js)]
    assert texts == ["Welcome back."]
    assert not any("greeting" in t or "hello" in t for t in texts)


def test_nested_exact_ignore_applies_to_dotted_key():
    js = (
        '{\n'
        '  "section": {\n'
        '    "title": "Skip this heading.",\n'
        '    "body": "Keep this copy."\n'
        '  }\n'
        '}\n'
    )
    ignore = key_ignorer(["section.title"])
    texts = [b.text for b in extract_i18n(js, ignore)]
    assert texts == ["Keep this copy."]


def test_nested_glob_ignore_applies_to_dotted_key():
    js = '{\n  "menu": {\n    "file": { "tooltip": "skip", "label": "Open a file." }\n  }\n}\n'
    ignore = key_ignorer(["*.tooltip"])
    texts = [b.text for b in extract_i18n(js, ignore)]
    assert texts == ["Open a file."]


def test_nested_value_line_number():
    js = '{\n  "section": {\n    "title": "First nested value."\n  }\n}\n'
    by_text = {b.text: b.base_line for b in extract_i18n(js)}
    assert by_text["First nested value."] == 3


def test_no_string_values_still_warns(capsys, tmp_path):
    import prose_check
    f = tmp_path / "novalues.json"
    f.write_text('{"count": 3, "enabled": true}\n')
    code = prose_check.main(["--no-autostart", "--format", "i18n", str(f)])
    err = capsys.readouterr().err
    assert code != 0  # non-zero: did not silently pass
    assert "no checkable string values" in err
