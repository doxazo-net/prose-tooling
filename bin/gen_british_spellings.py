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


def _shared_affix(a, b):
    """Return (longest common prefix length, longest common suffix length)."""
    pre = 0
    for x, y in zip(a, b):
        if x != y:
            break
        pre += 1
    suf = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y:
            break
        suf += 1
    return pre, suf


def _looks_orthographic(brit, amer):
    """True if the pair is a spelling variant, not a semantic swap.

    Genuine British->American variants share word structure: a common prefix or
    suffix of at least two characters (colour/color by prefix, tyre/tire by the
    '-re' suffix). VarCon also carries a few non-orthographic junk pairs -- slang
    clippings and unit swaps (prev/perv, nanogrammes/micrograms) -- that share
    almost nothing; those are rejected. This matters because the corpus feeds a
    commit-blocking rule, where a semantic substitution is actively harmful.
    """
    pre, suf = _shared_affix(brit, amer)
    return pre >= 2 or suf >= 2


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
            if (
                brit
                and suggestion
                and brit.lower() != suggestion.lower()
                and "'" not in brit
                and _looks_orthographic(brit.lower(), suggestion.lower())
            ):
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
        else:
            print(f"warning: ignoring malformed override line: {line}", file=sys.stderr)
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
    if n_auto < 500:
        raise SystemExit(
            f"generator produced only {n_auto} pairs (<500) from {args.varcon}; "
            "VarCon format may have changed or the source path is wrong"
        )
    if args.overrides.exists():
        apply_overrides(mapping, args.overrides.read_text(encoding="utf-8"))
    else:
        print(f"warning: overrides file not found: {args.overrides}", file=sys.stderr)
    args.out.write_text(render(mapping, level_cap=args.level_cap), encoding="utf-8")
    print(f"wrote {len(mapping)} pairs ({n_auto} auto) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
