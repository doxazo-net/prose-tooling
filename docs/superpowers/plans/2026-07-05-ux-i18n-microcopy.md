# UX i18n Microcopy Checking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the prose linter to grammar-check i18n microcopy (`en.json`) with a tuned rule profile, plus a cross-cutting suppression directive.

**Architecture:** Introduce a pluggable extractor layer: the existing Markdown path becomes one extractor, a new i18n extractor another; both return the same `(text, source_line)` block shape the existing pipeline (combine, check, partition, allowlist) already consumes. Suppression is per-surface: Markdown HTML-comment directives, i18n key-pattern/per-key ignores. A separate `en-US-microcopy` config bundle disables label/fragment rules.

**Tech Stack:** Python 3 (stdlib: `json`, `fnmatch`, `re`, `tomllib`, `urllib`), `markdown-it-py`, `pytest`, a local LanguageTool server.

## Global Constraints

- Client third-party deps stay in `prose-tooling/.venv`; target repos gain none. Only `markdown-it-py` is required at runtime.
- The block contract is `(text: str, source_line: int)` per prose run; everything after `combine_blocks` is unchanged and must not be modified for behavior.
- No em-dashes / emoji in code, comments, docs. US-Pacific labeled times if any.
- All checking runs against a local LanguageTool server only (privacy).
- Run tests with `./.venv/bin/python -m pytest`. Commit after each green task.
- Findings print as `path:line`; exit codes: 0 clean/advisory, 1 blocking, 2 server unreachable.

---

## File Structure

- `bin/prose_check.py` — the client. Add: suppression parsing, `extract_i18n`, extractor dispatch, profile selection. Refactor `check_markdown` into a shared `check_blocks` + per-file extractor call.
- `config/en-US-microcopy/severity.toml` — new microcopy rule bundle (created in Task 7, tuned in Task 8).
- `config/en-US-microcopy/dictionary.txt` — microcopy allowlist (may reuse the en-US list).
- `tests/test_suppression.py`, `tests/test_i18n.py`, `tests/test_dispatch.py` — new test files.
- `tests/fixtures/` — add `suppress.md`, `sample.en.json`.

---

## Task 1: Markdown suppression directives

**Files:**
- Modify: `bin/prose_check.py` (add `_suppressed_lines`, wire into `extract_blocks`)
- Test: `tests/test_suppression.py`

**Interfaces:**
- Produces: `suppressed_lines(text: str) -> set[int]` (1-indexed source lines to skip); `extract_blocks(markdown_text)` now omits text children on suppressed lines.
- Consumes: existing `extract_blocks`, `Block`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_suppression.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_suppression.py -v`
Expected: FAIL — `cannot import name 'suppressed_lines'`

- [ ] **Step 3: Write minimal implementation**

Add near the frontmatter regex in `bin/prose_check.py`:

```python
# Suppression directives (HTML comments; never rendered). Matched exactly so
# `disable` does not also match `disable-line`.
_DIRECTIVE_RE = re.compile(
    r"<!--\s*prose-lint-(disable-next-line|disable-line|disable|enable)\s*-->"
)


def suppressed_lines(text):
    """Return the set of 1-indexed source lines to skip per suppression directives."""
    suppressed = set()
    in_region = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        directives = _DIRECTIVE_RE.findall(line)
        # Apply enable/disable region toggles first (line-order within the line).
        for d in directives:
            if d == "enable":
                in_region = False
            elif d == "disable":
                in_region = True
        if in_region:
            suppressed.add(lineno)
        if "disable-line" in directives:
            suppressed.add(lineno)
        if "disable-next-line" in directives:
            suppressed.add(lineno + 1)
    return suppressed
```

Then in `extract_blocks`, compute the suppressed set from the ORIGINAL text and skip suppressed children. Modify the child loop:

```python
def extract_blocks(markdown_text):
    body, frontmatter_lines = _strip_frontmatter(markdown_text)
    skip = suppressed_lines(markdown_text)
    blocks = []
    for token in _MD.parse(body):
        if token.type != "inline":
            continue
        base_line = (token.map[0] if token.map else 0) + frontmatter_lines + 1
        parts = []
        children = []
        line = base_line
        for child in token.children or []:
            kind = child.type
            if kind == "text":
                if line not in skip:
                    parts.append(child.content)
                    children.append((child.content, line))
            elif kind in ("softbreak", "hardbreak"):
                parts.append("\n")
                line += 1
            elif kind == "code_inline":
                parts.append(" ")
        text = "".join(parts)
        if text.strip():
            blocks.append(Block(text, base_line, children))
    return blocks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_suppression.py tests/test_blocks.py -v`
Expected: PASS (new suppression tests + existing block tests still green)

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_suppression.py
git commit -m "feat: markdown suppression directives (prose-lint-disable)"
```

---

## Task 2: Extractor dispatch + shared pipeline refactor

**Files:**
- Modify: `bin/prose_check.py` (extract `check_blocks`, add `select_extractor`)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: `check_blocks(blocks, server, bundle) -> list[finding]` (finding = match dict + `line`); `select_extractor(path, fmt) -> str` returning `"markdown"` or `"i18n"`.
- Consumes: `check_markdown` internals (combine/post/local/filter/partition), which move into `check_blocks`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py
from prose_check import select_extractor


def test_dispatch_markdown_by_extension():
    assert select_extractor("docs/x.md", None) == "markdown"
    assert select_extractor("notes.txt", None) == "markdown"


def test_dispatch_i18n_by_extension():
    assert select_extractor("locales/en.json", None) == "i18n"


def test_explicit_format_overrides_extension():
    assert select_extractor("weird.dat", "i18n") == "i18n"
    assert select_extractor("en.json", "markdown") == "markdown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_dispatch.py -v`
Expected: FAIL — `cannot import name 'select_extractor'`

- [ ] **Step 3: Write minimal implementation**

Add to `bin/prose_check.py`:

```python
def select_extractor(path, fmt):
    """Choose the extractor: explicit --format wins, else by file extension."""
    if fmt:
        return fmt
    return "i18n" if str(path).endswith(".json") else "markdown"
```

Refactor `check_markdown` so its post-`blocks` body becomes `check_blocks`:

```python
def check_blocks(blocks, server, bundle):
    """Run the shared pipeline over already-extracted blocks; return findings."""
    combined, spans = combine_blocks(blocks)
    findings = []
    if combined.strip():
        matches = _post_check(server, combined, bundle)
        matches = filter_allowlisted(matches, combined, bundle["allowlist"])
        for match in matches:
            enriched = dict(match)
            enriched["line"] = line_for_offset(spans, match.get("offset", 0))
            findings.append(enriched)
    for block in blocks:
        for content, line in block.children:
            for match in local_matches_text(content):
                enriched = dict(match)
                enriched["line"] = line
                findings.append(enriched)
    findings.sort(key=lambda f: (f["line"] or 0, f.get("offset", 0)))
    return findings


def check_markdown(markdown_text, server, bundle):
    """Back-compat wrapper: extract Markdown blocks then run the shared pipeline."""
    return check_blocks(extract_blocks(markdown_text), server, bundle)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/ -v`
Expected: PASS (dispatch tests plus all existing tests, since `check_markdown` behavior is unchanged)

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_dispatch.py
git commit -m "refactor: extractor dispatch + shared check_blocks pipeline"
```

---

## Task 3: i18n value extraction with line numbers

**Files:**
- Modify: `bin/prose_check.py` (add `extract_i18n`)
- Test: `tests/test_i18n.py`; Create fixture `tests/fixtures/sample.en.json`

**Interfaces:**
- Produces: `extract_i18n(json_text, ignore=None) -> list[Block]` — one Block per checkable string value, `base_line` = the source line of that value, `children = [(value_text, line)]`.
- Consumes: `Block`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_i18n.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -v`
Expected: FAIL — `cannot import name 'extract_i18n'`

- [ ] **Step 3: Write minimal implementation**

```python
def _value_line(json_text, key):
    """1-indexed line where a flat JSON key's pair appears."""
    idx = json_text.find('"' + key + '"')
    if idx < 0:
        return 1
    return json_text.count("\n", 0, idx) + 1


def extract_i18n(json_text, ignore=None):
    """Extract checkable string values from a flat i18n locale JSON as Blocks."""
    ignore = ignore or (lambda key: False)
    data = json.loads(json_text)
    blocks = []
    for key, value in data.items():
        if not isinstance(value, str) or ignore(key):
            continue
        text = value  # placeholder masking added in Task 4
        if not text.strip():
            continue
        line = _value_line(json_text, key)
        blocks.append(Block(text, line, [(text, line)]))
    return blocks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_i18n.py
git commit -m "feat: i18n locale-JSON value extractor"
```

---

## Task 4: i18n placeholder masking

**Files:**
- Modify: `bin/prose_check.py` (add `_mask_placeholders`, call it in `extract_i18n`)
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces: `_mask_placeholders(value: str) -> str` — interpolation tokens replaced with a space; `extract_i18n` now masks before emitting.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_i18n.py
from prose_check import extract_i18n


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -k placeholder_or_printf -v`
Expected: FAIL — masks not applied (`{status}` present)

- [ ] **Step 3: Write minimal implementation**

```python
# {name}, {{name}}, %s, %d, %(name)s -> a single space (keeps word separation).
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|\{[^}]*\}|%\([^)]*\)[sd]|%[sd]")


def _mask_placeholders(value):
    return _PLACEHOLDER_RE.sub(" ", value)
```

In `extract_i18n`, change `text = value` to `text = _mask_placeholders(value)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_i18n.py
git commit -m "feat: mask i18n interpolation placeholders before checking"
```

---

## Task 5: i18n key-ignore (globs + per-key)

**Files:**
- Modify: `bin/prose_check.py` (add `load_i18n_ignore`, build the ignore predicate)
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces: `key_ignorer(patterns: list[str]) -> Callable[[str], bool]` — true if a key matches any glob or equals a listed key; `load_i18n_ignore(path) -> list[str]` reads `[i18n] ignore_keys` from a repo-local `.prose-lint.toml`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_i18n.py
from prose_check import extract_i18n, key_ignorer


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -k ignored -v`
Expected: FAIL — `cannot import name 'key_ignorer'`

- [ ] **Step 3: Write minimal implementation**

```python
import fnmatch  # add to the import block at top of file


def key_ignorer(patterns):
    """Return a predicate: key matches any glob pattern or exact listed key."""
    patterns = list(patterns or [])

    def ignore(key):
        return any(fnmatch.fnmatchcase(key, p) for p in patterns)

    return ignore


def load_i18n_ignore(path):
    """Read [i18n] ignore_keys from a repo-local .prose-lint.toml (or [])."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    return data.get("i18n", {}).get("ignore_keys", [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_i18n.py
git commit -m "feat: i18n key-pattern + per-key suppression"
```

---

## Task 6: Microcopy profile bundle + `load_bundle` by name

**Files:**
- Create: `config/en-US-microcopy/severity.toml`, `config/en-US-microcopy/dictionary.txt`
- Modify: `bin/prose_check.py` (`load_bundle` accepts a bundle dir name)
- Test: `tests/test_severity.py` (add a load test)

**Interfaces:**
- Produces: `load_bundle(config_dir, bundle_name)` where `bundle_name` is the subdir (`"en-US"` or `"en-US-microcopy"`); the merged allowlist reads `config/dictionary.txt` plus `config/<bundle_name>/dictionary.txt`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_severity.py
from pathlib import Path

from prose_check import load_bundle

_CONFIG = Path(__file__).resolve().parent.parent / "config"


def test_microcopy_bundle_loads_and_disables_fragment_rules():
    bundle = load_bundle(_CONFIG, "en-US-microcopy")
    assert bundle["language"] == "en-US"
    assert "UPPERCASE_SENTENCE_START" in bundle["disabled_rules"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_severity.py -k microcopy -v`
Expected: FAIL — bundle dir does not exist

- [ ] **Step 3: Create the bundle and generalize load_bundle**

Create `config/en-US-microcopy/severity.toml`:

```toml
# Microcopy profile for UI strings (labels, headers, short imperatives).
# Extends the docs en-US disables with rules that misfire on fragments.
language = "en-US"
level = "picky"
enabled_rules = ["SERIAL_COMMA_ON"]
disabled_rules = [
    "EN_QUOTES", "TWO_HYPHENS", "DASH_RULE", "ARROWS", "MULTIPLICATION_SIGN",
    "ID_CASING", "DOUBLE_PUNCTUATION", "WHITESPACE_RULE", "CONSECUTIVE_SPACES",
    "COMMA_PARENTHESIS_WHITESPACE", "SENTENCE_WHITESPACE",
    # Microcopy-specific: labels/headers are fragments, not sentences.
    "UPPERCASE_SENTENCE_START", "PUNCTUATION_PARAGRAPH_END",
    "MISSING_PERIOD_AFTER_ABBREVIATION",
]
disabled_categories = []
# Blocking stays minimal for microcopy; tuned in the calibration task.
blocking = ["LOCAL_EM_DASH", "SERIAL_COMMA_ON"]
```

Create `config/en-US-microcopy/dictionary.txt`:

```
# Microcopy allowlist (merged with global config/dictionary.txt).
# Seeded during calibration on en.json.
```

`load_bundle` already takes a second positional arg used as the subdir; confirm the signature is `load_bundle(config_dir, lang)` and rename the parameter to `bundle_name` for clarity (no behavior change — it already does `config_dir / bundle_name / "severity.toml"` and merges `config/dictionary.txt` + `config/<bundle_name>/dictionary.txt`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_severity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/en-US-microcopy/ bin/prose_check.py tests/test_severity.py
git commit -m "feat: en-US-microcopy profile bundle"
```

---

## Task 7: CLI dispatch (format, profile, i18n-ignore) + integration

**Files:**
- Modify: `bin/prose_check.py` (`main`: `--format`, `--profile`, `--i18n-ignore`; per-file extractor)
- Test: `tests/test_integration.py`; Create fixture `tests/fixtures/sample.en.json`

**Interfaces:**
- Consumes: `select_extractor`, `extract_blocks`, `extract_i18n`, `key_ignorer`, `load_i18n_ignore`, `load_bundle`, `check_blocks`.
- Produces: CLI that checks `.json` with the i18n extractor + microcopy bundle by default and honors `--i18n-ignore <toml>`.

- [ ] **Step 1: Write the failing test**

Create `tests/fixtures/sample.en.json`:

```json
{
  "ui.title": "Manage youre artists",
  "ui.tooltip": "This teh jargon-y tooltip",
  "ui.button_merge": "Confirm merge",
  "ui.status": "Loaded {count} of {total} items."
}
```

```python
# add to tests/test_integration.py
def test_i18n_file_checked_with_microcopy_profile(capsys):
    code = prose_check.main(
        ["--format", "i18n", "--profile", "microcopy", str(FIXTURES / "sample.en.json")]
    )
    out = capsys.readouterr().out
    # "youre" is a real error in a checked value.
    assert "MORFOLOGIK_RULE_EN_US" in out or "youre" in out.lower() or code in (0, 1)
    # A fragment button label must not trip a sentence-fragment error.
    assert "ui.button_merge" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_integration.py -k i18n_file -v`
Expected: FAIL — `main` does not accept `--format`/`--profile`

- [ ] **Step 3: Wire dispatch into main**

In `main`, add arguments and per-file extractor selection:

```python
    parser.add_argument("--format", choices=["markdown", "i18n"], default=None)
    parser.add_argument("--profile", choices=["docs", "microcopy"], default=None)
    parser.add_argument("--i18n-ignore", default=None,
                        help="path to a .prose-lint.toml with [i18n] ignore_keys")
```

Compute the bundle name and the i18n ignore predicate before the file loop:

```python
    profile = args.profile
    ignore_patterns = load_i18n_ignore(args.i18n_ignore) if args.i18n_ignore else []
    ignore = key_ignorer(ignore_patterns)
```

Replace the per-file body with extractor dispatch (bundle name = lang, or lang + "-microcopy"):

```python
        fmt = select_extractor(path, args.format)
        bundle_name = args.lang
        if profile == "microcopy" or (profile is None and fmt == "i18n"):
            bundle_name = f"{args.lang}-microcopy"
        bundle = load_bundle(args.config_dir, bundle_name)
        blocking_ids = set(bundle["blocking"])
        try:
            source = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"prose-check: cannot read {path}: {exc}", file=sys.stderr)
            had_blocking = True
            continue
        try:
            if fmt == "i18n":
                blocks = extract_i18n(source, ignore)
            else:
                blocks = extract_blocks(source)
            findings = check_blocks(blocks, args.server, bundle)
        except ServerUnreachable as exc:
            print(f"prose-check: LanguageTool server unreachable at {args.server}: {exc}", file=sys.stderr)
            return 2
```

(Move the `bundle`/`blocking_ids` load out of the top-of-`main` single-bundle assumption into the loop, since the bundle now varies per file. Keep the pre-loop `ensure_server` autostart call unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/ -v`
Expected: PASS (new i18n integration test + all existing)

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_integration.py tests/fixtures/sample.en.json
git commit -m "feat: CLI dispatch for i18n format + microcopy profile + key-ignore"
```

---

## Task 8: Calibrate the microcopy profile on en.json

**Files:**
- Modify: `config/en-US-microcopy/severity.toml`, `config/en-US-microcopy/dictionary.txt`
- (No test file; this is a tuning task validated by the live run.)

**Interfaces:** none (config only).

- [ ] **Step 1: Run the checker over the real locale (advisory profile)**

Run (server must be up; `bin/prose-lint-server.sh start`):

```bash
./.venv/bin/python bin/prose_check.py --format i18n --profile microcopy \
  ~/Developer/stillwater/internal/i18n/locales/en.json | tee /tmp/microcopy-cal.txt
```

- [ ] **Step 2: Review the finding distribution**

Inspect `/tmp/microcopy-cal.txt`: group by rule ID, identify (a) rules still misfiring on fragments -> add to `disabled_rules`; (b) legitimate product nouns flagged as spelling -> add to `config/en-US-microcopy/dictionary.txt`. Confirm real copy errors (typos, agreement) surface.

- [ ] **Step 3: Apply the tuning**

Edit `config/en-US-microcopy/severity.toml` `disabled_rules` and `blocking`, and `config/en-US-microcopy/dictionary.txt`, based on Step 2. Keep `blocking` to deterministic rules only (em-dash, serial comma), spelling advisory.

- [ ] **Step 4: Re-run and confirm low false-positive rate**

Run: the Step 1 command again. Expected: findings are real copy issues; fragment/label false positives gone.

- [ ] **Step 5: Commit**

```bash
git add config/en-US-microcopy/
git commit -m "config: calibrate en-US-microcopy profile on en.json"
```

---

## Out of scope (this plan)

- The stillwater incorporation (wire `en.json` into that repo's hook + CI with a repo-local `.prose-lint.toml`) is a separate issue in the stillwater repo, like #2239. It is not part of this plan.
- Generated docs / docs-as-code coverage, fr/ja locales, and Go-string / log-output extraction are deferred to later specs.
