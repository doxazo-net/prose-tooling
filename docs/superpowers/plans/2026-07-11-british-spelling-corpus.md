# British-spelling Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-curated inline British-to-American map behind `LOCAL_BRITISH_SPELLING` with a VarCon-derived corpus plus a house-style overrides layer, loaded at runtime from a committed data file.

**Architecture:** A dev-time generator (`bin/gen_british_spellings.py`) parses a vendored VarCon file into British-only spelling pairs, applies a hand-maintained overrides file, and writes `config/en-US/british-american.txt`. `bin/prose_check.py` loads that file once and switches from a giant-regex match to tokenize-then-dict-lookup. No new runtime dependency, no runtime network.

**Tech Stack:** Python 3.11+ stdlib only (`re`, `pathlib`, `argparse`), `pytest`, `ruff`.

## Global Constraints

- Stdlib-only for both generator and runtime; the sole runtime dependency stays `markdown-it-py`. No new deps.
- No runtime network. VarCon is vendored and parsed at dev time only.
- `LOCAL_BRITISH_SPELLING` blocks commits: auto-included entries must be British forms with NO American tag anywhere in their VarCon headword. Debatable/house-style calls live only in the overrides file.
- Ruff config `ruff.toml` selects F, E741. Line style follows existing `bin/prose_check.py`.
- VarCon file encoding is Latin-1; data/overrides files are UTF-8.
- SCOWL `level <= 60` is the conservative cap (a generator flag).
- Preserve existing rule behavior: id `LOCAL_BRITISH_SPELLING`, capitalization cast via `_match_case`, `en-US`-only via `_is_american_english`, whole-word case-insensitive matching.

---

### Task 1: Generator parser core

**Files:**
- Create: `bin/gen_british_spellings.py`
- Test: `tests/test_gen_british_spellings.py`

**Interfaces:**
- Produces: `parse_varcon(text: str, level_cap: int = 60) -> dict[str, str]` — maps lowercased British form to lowercased American suggestion. `_clusters(line: str) -> Iterator[tuple[set[str], bool, str]]` yields `(base_dialect_letters, is_primary_american, word)` per `/`-separated cluster.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gen_british_spellings.py
"""Tests for the VarCon -> British/American corpus generator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

from gen_british_spellings import parse_varcon


def test_british_only_word_is_mapped():
    varcon = "# behaviour (level 10)\nA Cv DV: behavior / B C D: behaviour\n"
    assert parse_varcon(varcon) == {"behaviour": "behavior"}


def test_american_variant_british_is_excluded():
    # grey carries AV (American variant) -> not blockable, must be dropped.
    varcon = "# gray (level 10)\nA Cv: gray / AV B C: grey\n"
    assert parse_varcon(varcon) == {}


def test_standard_american_word_excluded_via_block_aggregation():
    # dialogue is A (standard American) on one line; a later line pairs it
    # British. Block-level aggregation must still exclude it.
    varcon = (
        "# dialogue (level 20)\n"
        "A B: dialogue / AV: dialog\n"
        "A B Dv: dialog / Bv D: dialogue | <N> dialog box\n"
    )
    assert "dialogue" not in parse_varcon(varcon)


def test_level_cap_excludes_obscure_words():
    varcon = "# fantabulise (level 95)\nA Z: fantabulize / B: fantabulise\n"
    assert parse_varcon(varcon, level_cap=60) == {}
    assert parse_varcon(varcon, level_cap=95) == {"fantabulise": "fantabulize"}


def test_primary_american_form_chosen_as_suggestion():
    # colour's American is the primary 'A' token 'color'.
    varcon = "# color (level 10)\nA Cv DV: color / B C D: colour\n"
    assert parse_varcon(varcon)["colour"] == "color"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_gen_british_spellings.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gen_british_spellings'`.

- [ ] **Step 3: Write the parser**

```python
# bin/gen_british_spellings.py
#!/usr/bin/env python3
"""Generate the en-US British->American spelling corpus from VarCon.

Dev-time tool -- NOT on the bin/prose_check.py runtime path. Parses a vendored
VarCon file (SCOWL, public domain) into a two-column british<TAB>american data
file, applies the hand-maintained overrides, and writes a sorted, provenance-
headed corpus that bin/prose_check.py loads at runtime.

Refresh the vendored source (manual, occasional):
    curl -sL https://raw.githubusercontent.com/en-wl/wordlist/master/varcon/varcon.txt \\
      -o config/en-US/varcon.txt
Regenerate the corpus:
    ./.venv/bin/python bin/gen_british_spellings.py
"""

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_VARCON = _ROOT / "config" / "en-US" / "varcon.txt"
_DEFAULT_OVERRIDES = _ROOT / "config" / "en-US" / "british-american.overrides.txt"
_DEFAULT_OUT = _ROOT / "config" / "en-US" / "british-american.txt"
_LEVEL_CAP = 60

_LEVEL_RE = re.compile(r"\(level (\d+)\)")


def _clusters(line):
    """Yield (base_dialect_letters, is_primary_american, word) per cluster.

    A VarCon data line is '/'-separated clusters, each 'TAGS: word [| marker]'.
    Tag letters name dialects (A American, B British, ...); a trailing v/V marks
    a variant. is_primary_american is True only for the exact tag token 'A'.
    """
    for part in line.split(" / "):
        part = part.split("|", 1)[0].strip()
        if ":" not in part:
            continue
        tags_str, word = part.split(":", 1)
        word = word.strip()
        if not word or " " in word:
            continue
        tokens = tags_str.split()
        base = {t[0] for t in tokens}
        yield base, ("A" in tokens), word


def parse_varcon(text, level_cap=_LEVEL_CAP):
    """Return {british_lower: american_lower} from VarCon text.

    "Is this token ever American" is decided per headword BLOCK, so a word that
    is standard American on any line (dialogue) is excluded even where another
    line pairs it British. Suggestion pairing is per LINE.
    """
    mapping = {}
    block_level = 99
    block_lines = []

    def flush():
        if not block_lines or block_level > level_cap:
            return
        american = set()
        for ln in block_lines:
            for base, _prim, word in _clusters(ln):
                if "A" in base:
                    american.add(word.lower())
        for ln in block_lines:
            brit = amer = amer_primary = None
            for base, prim, word in _clusters(ln):
                if "A" in base:
                    if amer is None:
                        amer = word
                    if prim and amer_primary is None:
                        amer_primary = word
                if "B" in base and word.lower() not in american:
                    brit = word
            suggestion = amer_primary or amer
            if brit and suggestion and brit.lower() != suggestion.lower() and "'" not in brit:
                mapping.setdefault(brit.lower(), suggestion.lower())

    for raw in text.splitlines():
        if raw.startswith("#"):
            flush()
            block_lines = []
            m = _LEVEL_RE.search(raw)
            block_level = int(m.group(1)) if m else 99
        elif raw.strip():
            block_lines.append(raw)
    flush()
    return mapping
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_gen_british_spellings.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add bin/gen_british_spellings.py tests/test_gen_british_spellings.py
git commit -m "feat(gen): VarCon parser for British-spelling corpus (#11)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Overrides, rendering, and CLI

**Files:**
- Modify: `bin/gen_british_spellings.py` (append functions + `main`)
- Test: `tests/test_gen_british_spellings.py` (append)

**Interfaces:**
- Consumes: `parse_varcon` from Task 1.
- Produces: `apply_overrides(mapping: dict, text: str) -> dict` (mutates+returns), `render(mapping: dict, level_cap: int) -> str`, `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_british_spellings.py
from gen_british_spellings import apply_overrides, render


def test_override_add_forces_house_style_pair():
    m = {}
    apply_overrides(m, "+ catalogue catalog  # user-requested house style\n")
    assert m["catalogue"] == "catalog"


def test_override_remove_drops_false_positive():
    m = {"dialogue": "dialog"}
    apply_overrides(m, "- dialogue  # standard American, never block\n")
    assert "dialogue" not in m


def test_override_ignores_comments_and_blanks():
    m = {}
    apply_overrides(m, "# a comment\n\n+ grey gray\n")
    assert m == {"grey": "gray"}


def test_render_is_sorted_with_header_and_tabs():
    out = render({"colour": "color", "behaviour": "behavior"}, level_cap=60)
    lines = out.splitlines()
    assert lines[0].startswith("#")
    body = [ln for ln in lines if ln and not ln.startswith("#")]
    assert body == ["behaviour\tbehavior", "colour\tcolor"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_gen_british_spellings.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_overrides'`.

- [ ] **Step 3: Append the implementation**

```python
# append to bin/gen_british_spellings.py

def apply_overrides(mapping, text):
    """Apply the hand-maintained overrides file to a parsed mapping.

    '+ british american' force-adds a house-style pair; '- british' removes a
    false positive. '#' starts a comment. Returns the mutated mapping.
    """
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        op, rest = line[0], line[1:].split()
        if op == "+" and len(rest) == 2:
            mapping[rest[0].lower()] = rest[1].lower()
        elif op == "-" and rest:
            mapping.pop(rest[0].lower(), None)
    return mapping


def render(mapping, level_cap=_LEVEL_CAP):
    header = [
        "# en-US British -> American spelling corpus. GENERATED -- do not edit by hand.",
        "# Regenerate: ./.venv/bin/python bin/gen_british_spellings.py",
        "# Source: VarCon (SCOWL) -- https://github.com/en-wl/wordlist (public domain).",
        "#   Vendored copy + license: config/en-US/varcon.txt",
        f"# Filter: British-only forms (no American tag in the headword), SCOWL level <= {level_cap}.",
        "# House-style adds/exclusions: config/en-US/british-american.overrides.txt",
        "# Format: <british><TAB><american>, one pair per line, sorted.",
        "",
    ]
    body = [f"{b}\t{a}" for b, a in sorted(mapping.items())]
    return "\n".join(header + body) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the British-spelling corpus from VarCon.")
    ap.add_argument("--varcon", type=Path, default=_DEFAULT_VARCON)
    ap.add_argument("--overrides", type=Path, default=_DEFAULT_OVERRIDES)
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--level-cap", type=int, default=_LEVEL_CAP)
    args = ap.parse_args(argv)

    text = args.varcon.read_text(encoding="latin-1")
    mapping = parse_varcon(text, level_cap=args.level_cap)
    n_auto = len(mapping)
    if args.overrides.exists():
        apply_overrides(mapping, args.overrides.read_text(encoding="utf-8"))
    else:
        print(f"warning: overrides file not found: {args.overrides}", file=sys.stderr)
    args.out.write_text(render(mapping, level_cap=args.level_cap), encoding="utf-8")
    print(f"wrote {len(mapping)} pairs ({n_auto} auto) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_gen_british_spellings.py -q && ./.venv/bin/ruff check bin/gen_british_spellings.py tests/test_gen_british_spellings.py`
Expected: PASS (9 passed), ruff clean.

- [ ] **Step 5: Commit**

```bash
git add bin/gen_british_spellings.py tests/test_gen_british_spellings.py
git commit -m "feat(gen): overrides, rendering, and CLI for corpus generator (#11)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Vendor VarCon, seed overrides, generate corpus

**Files:**
- Create: `config/en-US/varcon.txt` (vendored, ~32k lines)
- Create: `config/en-US/british-american.overrides.txt`
- Create: `config/en-US/british-american.txt` (generated)

**Interfaces:**
- Consumes: `main` from Task 2.

- [ ] **Step 1: Vendor the VarCon source**

Run:
```bash
curl -sL https://raw.githubusercontent.com/en-wl/wordlist/master/varcon/varcon.txt \
  -o config/en-US/varcon.txt
head -20 config/en-US/varcon.txt   # confirm the license/legend header is present
wc -l config/en-US/varcon.txt       # expect ~32k lines
```
Expected: file exists, header present, ~32000 lines. (If the license header is not in the file body, prepend a short provenance comment noting VarCon is public domain, Kevin Atkinson / SCOWL, with the source URL.)

- [ ] **Step 2: Write the seed overrides file**

```text
# config/en-US/british-american.overrides.txt
# House-style adds and false-positive exclusions layered onto the VarCon corpus.
# '+ british american' force-adds a pair VarCon marks American-acceptable but the
#   house style dispreferred. '- british' drops a British-only VarCon pair that is
#   in fact standard American (a false positive). Grow the '-' set from the repo sweep.

# House-style adds: VarCon tags these as an American variant, so the auto filter
# drops them, but house style wants the American form.
+ grey gray
+ catalogue catalog
+ catalogues catalogs
+ catalogued cataloged
+ cancelled canceled
+ cancelling canceling
+ practise practice
+ aluminium aluminum
+ programme program
+ programmes programs

# Exclusions: standard American spellings VarCon may pair as British. Never block.
- dialogue
```

- [ ] **Step 3: Generate the corpus**

Run: `./.venv/bin/python bin/gen_british_spellings.py`
Expected: `wrote N pairs (M auto) to .../british-american.txt` with N in the low thousands.

- [ ] **Step 4: Verify key words landed correctly**

Run:
```bash
grep -P '^(behaviour|colour|organise|analogue|licence|travelling)\t' config/en-US/british-american.txt
grep -P '^(catalogue|grey|cancelled|aluminium)\t' config/en-US/british-american.txt
grep -Pc '^dialogue\t' config/en-US/british-american.txt   # expect 0
```
Expected: the British-only words and the override adds are present; `dialogue` count is `0`. If `dialogue` appears, the block-aggregation logic or override is wrong — fix before continuing.

- [ ] **Step 5: Commit**

```bash
git add config/en-US/varcon.txt config/en-US/british-american.overrides.txt config/en-US/british-american.txt
git commit -m "data(en-US): vendor VarCon and generate British-spelling corpus (#11)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Runtime loader and tokenize-lookup

**Files:**
- Modify: `bin/prose_check.py` — delete `_BRITISH_TO_AMERICAN` (lines 169-254) and `_BRITISH_RE` (256-261); add loader + `_WORD_RE`; rewrite the British branch in `local_matches_text` (299-322).
- Test: `tests/test_local_rules.py` (adjust/extend)

**Interfaces:**
- Consumes: `config/en-US/british-american.txt` from Task 3.
- Produces: `_load_british_map(path) -> dict[str, str]` (raises on missing/empty), `_british_map() -> dict` (cached), unchanged `local_matches_text(text, language=None)` behavior.

- [ ] **Step 1: Write/adjust the failing tests**

The Task-#11 behavior tests in `tests/test_local_rules.py` stay as-is (they assert `behaviour`, `catalogue`, `colour->color`, `greyhound` not flagged, etc., all satisfied by the corpus + overrides). Append a loader-failure test:

```python
# append to tests/test_local_rules.py
def test_load_british_map_missing_file_raises(tmp_path):
    import pytest
    from prose_check import _load_british_map
    with pytest.raises(OSError):
        _load_british_map(tmp_path / "absent.txt")
```

- [ ] **Step 2: Run to verify the new test fails**

Run: `./.venv/bin/python -m pytest tests/test_local_rules.py::test_load_british_map_missing_file_raises -q`
Expected: FAIL — `ImportError: cannot import name '_load_british_map'`.

- [ ] **Step 3: Delete the inline map/regex and add the loader**

Delete the entire `_BRITISH_TO_AMERICAN = { ... }` literal and the `_BRITISH_RE = re.compile( ... )` block. Keep `_match_case` and `_is_american_english`. In their place add:

```python
_WORD_RE = re.compile(r"[A-Za-z]+")
_BRITISH_MAP_CACHE = None


def _load_british_map(path):
    """Load the British->American corpus. Raises if missing/empty: a blocking
    rule must never silently degrade to a no-op (no-silent-failure house rule)."""
    mapping = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        brit, _tab, amer = line.partition("\t")
        if amer:
            mapping[brit.strip().lower()] = amer.strip().lower()
    if not mapping:
        raise ValueError(f"British-spelling corpus is empty: {path}")
    return mapping


def _british_map():
    global _BRITISH_MAP_CACHE
    if _BRITISH_MAP_CACHE is None:
        _BRITISH_MAP_CACHE = _load_british_map(
            _DEFAULT_CONFIG_DIR / "en-US" / "british-american.txt"
        )
    return _BRITISH_MAP_CACHE
```

Note: `_DEFAULT_CONFIG_DIR` is defined later in the module (line ~375); `_british_map` only reads it at call time, so import order is fine.

- [ ] **Step 4: Rewrite the British branch in `local_matches_text`**

Replace the `for m in _BRITISH_RE.finditer(text):` block with the tokenize-lookup:

```python
    if _is_american_english(language):
        mapping = _british_map()
        for m in _WORD_RE.finditer(text):
            american = mapping.get(m.group(0).lower())
            if american is not None:
                american = _match_case(m.group(0), american)
                matches.append(
                    _local_match(
                        "LOCAL_BRITISH_SPELLING",
                        m.start(),
                        m.end() - m.start(),
                        f"British spelling: prefer American '{american}'.",
                        [american],
                    )
                )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_local_rules.py -q`
Expected: PASS (12 passed — the 11 from #11 plus the loader-failure test).

- [ ] **Step 6: Commit**

```bash
git add bin/prose_check.py tests/test_local_rules.py
git commit -m "refactor(en-US): load British corpus from data file, tokenize-lookup (#11)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Docs and full-gate verification

**Files:**
- Modify: `README.md` (House rules section), `CLAUDE.md` (Key Rules), `docs/superpowers/specs/2026-07-11-british-spelling-corpus-design.md` (mark implemented)

- [ ] **Step 1: Update README house-rules note**

In `README.md`, extend the British-spelling sentence to name the corpus source. Add after the existing `LOCAL_BRITISH_SPELLING` description:

```markdown
The British-spelling list is a corpus generated from VarCon (SCOWL, public
domain) by `bin/gen_british_spellings.py` into `config/en-US/british-american.txt`,
with house-style adds/exclusions in `config/en-US/british-american.overrides.txt`.
Regenerate after editing overrides or refreshing the vendored `config/en-US/varcon.txt`.
```

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md` under Architecture (the `config/<lang>/` bullet), add a sentence:

```markdown
  The en-US British-spelling corpus (`config/en-US/british-american.txt`) is
  generated from a vendored VarCon by `bin/gen_british_spellings.py`; edit
  `british-american.overrides.txt` (not the generated file) then regenerate.
```

- [ ] **Step 3: Run the full local gate**

Run:
```bash
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check bin/ tests/
shellcheck bin/*.sh
```
Expected: all tests pass, ruff clean, shellcheck clean.

- [ ] **Step 4: End-to-end reproduction**

Run:
```bash
printf '# T\n\nThe behaviour of the catalogue is a grey colour.\n' > /tmp/uk.md
./.venv/bin/python bin/prose_check.py /tmp/uk.md; echo "exit: $?"
```
Expected: `LOCAL_BRITISH_SPELLING` ERROR findings for behaviour, catalogue, grey, colour; exit `1`.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/superpowers/specs/2026-07-11-british-spelling-corpus-design.md
git commit -m "docs: document British-spelling corpus generation (#11)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Post-implementation (not a code task)

Run the checker across the user's `~/Developer` repos (the sweep). Review every
`LOCAL_BRITISH_SPELLING` hit; feed any false positive into the overrides `-` list
and regenerate. Report findings generically (mechanism + counts, not private repo
content) per the privacy rule. This is operational validation, done with the user,
after the branch is reviewed.

## Notes for the implementer

- The current branch is `fix/en-us-british-spelling-11`, which already carries the
  inline-map version of `LOCAL_BRITISH_SPELLING` (issue #11) and the design spec.
  This plan supersedes the inline map on the same branch.
- Do not push or open a PR without explicit user permission (repo + global rules).
- `config/en-US/varcon.txt` is Latin-1; everything else is UTF-8.
