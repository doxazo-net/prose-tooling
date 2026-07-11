# Genericize B (examples, schema, scaffolding) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a new repo adopt prose-tooling in one command: ship example starter configs, a scaffold in `install.sh` that writes a `.prose-lint.toml` and prints the hook, a documented config schema, and an ergonomic `./.prose-lint.toml` auto-load.

**Architecture:** Additive. New `examples/` tree (config starters + hook templates), a scaffold code path in `bin/install.sh` (writes `.prose-lint.toml` non-clobbering, `--with-config` copies a config dir, prints hooks sourced from the example templates), a small auto-load convention in `bin/prose_check.py`, and `docs/CONFIG.md`. No change to checking/rule semantics.

**Tech Stack:** Bash (`install.sh`, `shellcheck`-clean), Python 3.11+ stdlib (`prose_check.py`), `pytest`.

## Global Constraints

- Stdlib-only Python; sole runtime dep stays `markdown-it-py`. Bash stays `shellcheck` clean; workflows `actionlint` clean.
- Ruff config `ruff.toml` selects F, E741.
- Never clobber an adopter file: back up an existing `.prose-lint.toml` to `.prose-lint.toml.bak` before writing; `--with-config` skips pre-existing files.
- The scaffold writes only under the target repo (`<target>/.prose-lint.toml`, opt-in `<target>/.prose-lint-config/`); it never edits `.git/` or an existing hook.
- Auto-load precedence: `--i18n-ignore <path>` (explicit) > `./.prose-lint.toml` (cwd, if present) > empty. A malformed TOML raises loudly (no silent empty-ignores).
- The hook snippet has ONE source: `examples/hooks/*`; `install.sh` reads and substitutes, not a second inline copy.
- Bash / macOS + Linux only; Windows and alternate backends are part A (#15), out of scope.

---

### Task 1: Example starter configs + validity test

**Files:**
- Create: `examples/config/en-US/severity.toml`, `examples/config/en-US/dictionary.txt`, `examples/config/en-US-microcopy/severity.toml`, `examples/.prose-lint.toml`
- Test: `tests/test_examples.py`

**Interfaces:**
- Consumes: `load_bundle(config_dir, bundle_name)` and `load_i18n_ignore(path)` from `bin/prose_check.py` (existing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_examples.py
"""The shipped examples/ starters must always be valid so adopters can copy them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

from prose_check import load_bundle, load_i18n_ignore

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_example_bundles_load():
    for bundle in ("en-US", "en-US-microcopy"):
        b = load_bundle(EXAMPLES / "config", bundle)
        assert b["language"] == "en-US"
        assert isinstance(b["blocking"], list) and b["blocking"]


def test_example_prose_lint_toml_parses():
    keys = load_i18n_ignore(EXAMPLES / ".prose-lint.toml")
    assert isinstance(keys, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_examples.py -q`
Expected: FAIL — `load_bundle` raises `FileNotFoundError` (examples/config absent).

- [ ] **Step 3: Create the example files**

`examples/config/en-US/severity.toml`:
```toml
# Minimal en-US docs profile -- copy to your own config dir and adapt.
# See docs/CONFIG.md for every key. Keep `blocking` to deterministic,
# low-false-positive rules only; leave spelling/style advisory.

language = "en-US"
level = "picky"

# Rules the free server surfaces that are noisy on technical Markdown.
disabled_rules = [
    "EN_QUOTES",
    "TWO_HYPHENS",
    "DASH_RULE",
    "WHITESPACE_RULE",
]
disabled_categories = []

# Only deterministic client-side + serial-comma rules fail a commit.
blocking = [
    "LOCAL_EM_DASH",
    "LOCAL_DOUBLE_SPACE",
    "SERIAL_COMMA_ON",
]
```

`examples/config/en-US/dictionary.txt`:
```text
# Per-language spelling allowlist (case-insensitive, one word per line).
# Add project nouns / tools LanguageTool does not know. Merged with the
# global config/dictionary.txt at check time.
YourProductName
```

`examples/config/en-US-microcopy/severity.toml`:
```toml
# Minimal en-US microcopy profile for short UI strings / i18n values.
language = "en-US"
level = "picky"
disabled_rules = [
    "EN_QUOTES",
    "UPPERCASE_SENTENCE_START",   # UI labels are fragments
    "PUNCTUATION_PARAGRAPH_END",
]
disabled_categories = []
blocking = [
    "LOCAL_EM_DASH",
    "SERIAL_COMMA_ON",
]
```

`examples/.prose-lint.toml`:
```toml
# Repo-local prose-lint config. Placed at your repo root, it is auto-loaded
# by prose_check.py (no flag needed). See docs/CONFIG.md.

[i18n]
# Keys whose VALUES are skipped (glob via fnmatch, or exact key). Useful for
# code-ish strings, tooltips, or log lines that are not prose.
ignore_keys = [
    "*.tooltip",
    "*.log_*",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_examples.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add examples/ tests/test_examples.py
git commit -m "feat(examples): minimal starter configs for adopters (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Hook templates + install.sh scaffold

**Files:**
- Create: `examples/hooks/githooks-pre-commit.sh`, `examples/hooks/pre-commit-config.yaml`
- Modify: `bin/install.sh` (add scaffold write + `--with-config`; print hooks from the templates instead of inline here-docs)
- Test: `tests/test_install_scaffold.py`

**Interfaces:**
- Consumes: `examples/.prose-lint.toml` and `examples/config/` from Task 1.
- Produces: `bin/install.sh [<target>] [--with-config]` — writes `<target>/.prose-lint.toml` (backup if present), optional `<target>/.prose-lint-config/`, prints hooks.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_install_scaffold.py
"""Behavioral tests for the install.sh scaffold (writes config, never clobbers)."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "bin" / "install.sh"


def _run(target, *args):
    return subprocess.run(
        [str(INSTALL), str(target), *args],
        capture_output=True, text=True,
    )


def _git_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_writes_prose_lint_toml_when_absent(tmp_path):
    repo = _git_repo(tmp_path)
    r = _run(repo)
    assert r.returncode == 0
    written = (repo / ".prose-lint.toml").read_text()
    assert "[i18n]" in written


def test_backs_up_existing_prose_lint_toml(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / ".prose-lint.toml").write_text("# my custom config\n")
    r = _run(repo)
    assert r.returncode == 0
    assert (repo / ".prose-lint.toml.bak").read_text() == "# my custom config\n"


def test_with_config_copies_config_dir(tmp_path):
    repo = _git_repo(tmp_path)
    r = _run(repo, "--with-config")
    assert r.returncode == 0
    assert (repo / ".prose-lint-config" / "en-US" / "severity.toml").exists()


def test_prints_hook_snippet(tmp_path):
    repo = _git_repo(tmp_path)
    r = _run(repo)
    assert "prose-lint" in r.stdout
    assert "prose_check.py" in r.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_install_scaffold.py -q`
Expected: FAIL — no `.prose-lint.toml` is written (install.sh only prints today).

- [ ] **Step 3: Create the hook templates**

`examples/hooks/githooks-pre-commit.sh` (the bash body; `__CLIENT__` is substituted by install.sh):
```bash
# prose-lint -- LanguageTool grammar/prose on staged markdown (central config)
STAGED_PROSE=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' '*.txt' || true)
if [ -n "$STAGED_PROSE" ]; then
    if ! PROSE_OUTPUT=$(echo "$STAGED_PROSE" | tr '\n' '\0' \
            | xargs -0 __CLIENT__ --lang en-US -- 2>&1); then
        echo "FAIL prose-lint:"; echo "$PROSE_OUTPUT"; exit 1
    fi
    echo "$PROSE_OUTPUT"   # advisories (exit 0)
fi
```

`examples/hooks/pre-commit-config.yaml`:
```yaml
  - repo: local
    hooks:
      - id: prose-lint
        name: prose-lint (LanguageTool)
        entry: __CLIENT__ --lang en-US --
        language: system
        files: '\.(md|txt)$'
```

- [ ] **Step 4: Rewrite `bin/install.sh`**

Replace the whole file with (keeps the print behavior, sourced from the templates, and adds the scaffold write + `--with-config`):
```bash
#!/usr/bin/env bash
# install.sh -- scaffold prose-lint config into a target repo and print the hook.
#
# Writes a starter .prose-lint.toml (backing up any existing one), optionally
# copies a starter config dir with --with-config, and prints the git-hook
# wiring. It never edits .git/ or an existing hook -- paste the printed snippet
# as part of the target repo's own change.
#
# Usage: install.sh [/path/to/target/repo] [--with-config]
set -euo pipefail

TOOLING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT="${TOOLING_DIR}/.venv/bin/python ${TOOLING_DIR}/bin/prose_check.py"
EXAMPLES="${TOOLING_DIR}/examples"

TARGET="."
WITH_CONFIG=0
for arg in "$@"; do
	case "$arg" in
		--with-config) WITH_CONFIG=1 ;;
		-*) echo "unknown option: $arg" >&2; exit 2 ;;
		*) TARGET="$arg" ;;
	esac
done

[ -d "${TARGET}" ] || { echo "target is not a directory: ${TARGET}" >&2; exit 2; }
[ -d "${TARGET}/.git" ] || { echo "target is not a git repo: ${TARGET}" >&2; exit 2; }
TARGET_ABS="$(cd "${TARGET}" && pwd)"

echo "prose-tooling dir : ${TOOLING_DIR}"
echo "target repo       : ${TARGET_ABS}"
echo

# 1) Scaffold .prose-lint.toml (never clobber).
DEST="${TARGET_ABS}/.prose-lint.toml"
if [ -f "${DEST}" ]; then
	cp "${DEST}" "${DEST}.bak"
	echo "backed up existing .prose-lint.toml -> .prose-lint.toml.bak"
fi
cp "${EXAMPLES}/.prose-lint.toml" "${DEST}"
echo "wrote ${DEST}"

# 2) Optionally copy a starter config dir (skip pre-existing files).
CONFIG_FLAG=""
if [ "${WITH_CONFIG}" -eq 1 ]; then
	DESTCFG="${TARGET_ABS}/.prose-lint-config"
	mkdir -p "${DESTCFG}"
	# -n: never overwrite an existing file; note skips.
	cp -Rn "${EXAMPLES}/config/." "${DESTCFG}/"
	echo "copied starter config -> ${DESTCFG} (existing files skipped)"
	CONFIG_FLAG=" --config-dir ${DESTCFG}"
fi
echo

# 3) Detect hook mechanism and print the wiring (single source: examples/hooks).
if [ -f "${TARGET_ABS}/.githooks/pre-commit" ]; then
	echo "Detected .githooks/pre-commit (core.hooksPath style)."
elif [ -f "${TARGET_ABS}/.pre-commit-config.yaml" ]; then
	echo "Detected .pre-commit-config.yaml (pre-commit framework)."
else
	echo "No known hook mechanism detected; choose one below."
fi
echo
echo "The client auto-starts the container on demand if it is stopped."
echo "To manage it manually: ${TOOLING_DIR}/bin/prose-lint-server.sh start"
echo
echo "2a) For a .githooks/pre-commit (bash) repo, add this section:"
echo
sed "s|__CLIENT__|${CLIENT}${CONFIG_FLAG}|g" "${EXAMPLES}/hooks/githooks-pre-commit.sh"
echo
echo "2b) For a pre-commit-framework repo, add a repo: local hook:"
echo
sed "s|__CLIENT__|${CLIENT}${CONFIG_FLAG}|g" "${EXAMPLES}/hooks/pre-commit-config.yaml"
echo
echo "The client exits 1 on a blocking finding, 2 if the server is unreachable."
```

- [ ] **Step 5: Run tests + shellcheck**

Run: `./.venv/bin/python -m pytest tests/test_install_scaffold.py -q && shellcheck bin/install.sh`
Expected: PASS (4 passed), shellcheck clean.

- [ ] **Step 6: Commit**

```bash
git add examples/hooks/ bin/install.sh tests/test_install_scaffold.py
git commit -m "feat(install): scaffold .prose-lint.toml + single-source hook snippets (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Auto-load `./.prose-lint.toml`

**Files:**
- Modify: `bin/prose_check.py` (line 524 area — replace the ignore resolution; add a helper)
- Test: `tests/test_i18n.py` (append)

**Interfaces:**
- Consumes: `load_i18n_ignore(path)` (existing).
- Produces: `_resolve_i18n_ignore(explicit)` — returns the ignore-key list per precedence.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_i18n.py
def test_cwd_prose_lint_toml_auto_loaded(tmp_path, monkeypatch):
    import prose_check
    (tmp_path / ".prose-lint.toml").write_text('[i18n]\nignore_keys = ["*.skip"]\n')
    monkeypatch.chdir(tmp_path)
    assert prose_check._resolve_i18n_ignore(None) == ["*.skip"]


def test_explicit_flag_overrides_cwd(tmp_path, monkeypatch):
    import prose_check
    (tmp_path / ".prose-lint.toml").write_text('[i18n]\nignore_keys = ["*.cwd"]\n')
    other = tmp_path / "other.toml"
    other.write_text('[i18n]\nignore_keys = ["*.explicit"]\n')
    monkeypatch.chdir(tmp_path)
    assert prose_check._resolve_i18n_ignore(str(other)) == ["*.explicit"]


def test_no_toml_means_no_ignores(tmp_path, monkeypatch):
    import prose_check
    monkeypatch.chdir(tmp_path)
    assert prose_check._resolve_i18n_ignore(None) == []


def test_malformed_cwd_toml_raises(tmp_path, monkeypatch):
    import prose_check
    import pytest
    (tmp_path / ".prose-lint.toml").write_text("this is not = valid = toml\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(Exception):
        prose_check._resolve_i18n_ignore(None)
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -k resolve_i18n -q`
Expected: FAIL — `AttributeError: module 'prose_check' has no attribute '_resolve_i18n_ignore'`.

- [ ] **Step 3: Implement the resolver**

Add after `load_i18n_ignore` (around line 479):
```python
def _resolve_i18n_ignore(explicit):
    """Ignore-key list by precedence: explicit --i18n-ignore path, else an
    auto-loaded ./.prose-lint.toml in the cwd if present, else none. A malformed
    file raises (tomllib) rather than silently yielding no ignores."""
    if explicit:
        return load_i18n_ignore(explicit)
    default = Path(".prose-lint.toml")
    return load_i18n_ignore(default) if default.exists() else []
```

Replace line 524:
```python
    ignore_patterns = load_i18n_ignore(args.i18n_ignore) if args.i18n_ignore else []
```
with:
```python
    ignore_patterns = _resolve_i18n_ignore(args.i18n_ignore)
```

Update the `--i18n-ignore` help text (line 508) to note the default:
```python
        help="path to a .prose-lint.toml with [i18n] ignore_keys "
        "(default: ./.prose-lint.toml if present)",
```

- [ ] **Step 4: Run tests**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -q`
Expected: PASS (all i18n tests, including the 4 new).

- [ ] **Step 5: Commit**

```bash
git add bin/prose_check.py tests/test_i18n.py
git commit -m "feat(i18n): auto-load ./.prose-lint.toml when --i18n-ignore is absent (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Config schema docs

**Files:**
- Create: `docs/CONFIG.md`
- Modify: `README.md` (link the new doc from the config section)

- [ ] **Step 1: Write `docs/CONFIG.md`**

Document each surface with meaning + type. Cover:
- `severity.toml`: `language` (str, required), `level` (`"default"|"picky"`), `enabled_rules` / `disabled_rules` (rule-ID lists), `disabled_categories` (category-ID list), `blocking` (rule-ID or category-ID list that fails a commit; keep to deterministic low-false-positive rules). Note the client-side `LOCAL_EM_DASH` / `LOCAL_DOUBLE_SPACE` / `LOCAL_BRITISH_SPELLING` rule IDs.
- `dictionary.txt`: per-language + global `config/dictionary.txt`, case-insensitive, one word per line, merged.
- `.prose-lint.toml`: `[i18n] ignore_keys` (fnmatch globs or exact keys); the auto-load precedence (`--i18n-ignore` > `./.prose-lint.toml` > none).
- Adopting your own config: point `--config-dir` at your own directory (no tool edit needed); `bin/install.sh <repo> --with-config` scaffolds a starter.

- [ ] **Step 2: Link from README**

In `README.md`, under the config section, add: `See [docs/CONFIG.md](docs/CONFIG.md) for the full config schema and adoption guide.`

- [ ] **Step 3: Full gate**

Run:
```bash
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check bin/ tests/
shellcheck bin/*.sh
```
Expected: all pass/clean.

- [ ] **Step 4: End-to-end scaffold check**

Run:
```bash
tmp=$(mktemp -d); git -C "$tmp" init -q
bin/install.sh "$tmp" --with-config >/dev/null
test -f "$tmp/.prose-lint.toml" && test -f "$tmp/.prose-lint-config/en-US/severity.toml" && echo "scaffold OK"
rm -rf "$tmp"
```
Expected: `scaffold OK`.

- [ ] **Step 5: Commit**

```bash
git add docs/CONFIG.md README.md
git commit -m "docs: config schema + adoption guide (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: examples/ (T1), scaffold + hook single-source (T2), auto-load (T3), schema docs + config-discovery documentation (T4). All spec sections mapped.
- The scaffold writes only under the target repo and backs up an existing `.prose-lint.toml`; `--with-config` uses `cp -Rn` so pre-existing files are skipped (Global Constraints honored).
- `_resolve_i18n_ignore` centralizes precedence; `main` calls it. Malformed TOML propagates from `tomllib` (loud), a missing file is the normal empty case.
- Rollout: one PR closing #16, off `main`, well under 1KLOC.
