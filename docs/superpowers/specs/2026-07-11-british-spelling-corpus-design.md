# British-spelling corpus for en-US blocking

Design doc. Status: implemented 2026-07-11. Scope: replace the hand-curated inline
British-to-American map behind the `LOCAL_BRITISH_SPELLING` rule (issue #11) with
a proper, data-derived corpus generated from VarCon, plus a hand-maintained
house-style overrides layer, validated against real repo prose.

## Problem

`LOCAL_BRITISH_SPELLING` (issue #11, shipped on branch
`fix/en-us-british-spelling-11`) blocks British spellings in en-US prose. Its
word map is a ~180-entry dict hand-written inline in `bin/prose_check.py`. That
is fine as a first cut but is not a corpus: coverage is arbitrary (whatever came
to mind), inflections are spotty, there is no provenance, and growing it means
editing production code by hand. Because the rule *blocks* commits, both gaps
matter: missed words let British spellings through across the repo sweep, and a
wrong entry hard-fails a commit on a legitimate word.

We want the map to be **derived from an authoritative dataset**, **reproducible**,
**low-false-positive by construction**, and **tunable** for house style without
editing code.

## Constraints

- **No runtime network or new dependency.** The tool is local-first and
  stdlib-only (bar `markdown-it-py`). VarCon is fetched and parsed at *dev time*
  by a maintainer-run generator; the runtime loads only a static committed data
  file. This mirrors the existing offline posture.
- **Blocking-grade low false positive.** The rule fails commits, so every
  auto-included entry must be a spelling the target dialect (American English)
  does not accept at all. Debatable house-style calls must be explicit, not
  inferred.
- **Deterministic and diff-reviewable.** The corpus is a sorted text file under
  version control; regeneration produces a stable, reviewable diff.
- **Reproducible provenance.** The generator records the VarCon source and its
  public-domain licensing in the output header.
- **Whole-word, case-insensitive matching**, preserving the existing behavior
  (capitalization cast onto the suggestion; `en-US`-only via the language gate).

## Source of truth: VarCon

VarCon (Variant Conversion, from Kevin Atkinson's SCOWL project) is the canonical
cross-dialect spelling-variant dataset. Public domain / permissive. ~32k lines.
Reachable at `https://raw.githubusercontent.com/en-wl/wordlist/master/varcon/varcon.txt`
(the `wordlist.aspell.net` origin 301-redirects to it). Encoding is Latin-1.

Format: a headword block introduced by a `# headword (level N)` comment, followed
by one or more data lines. Each data line is `/`-separated clusters; each cluster
is `TAGS: word [| marker]`. Tag letters name dialects: `A` American, `B` British,
`C` Canadian, `D` Australian, `Z` the British-accepted `-ize` form. A trailing
`v`/`V` on a tag marks a *variant* (secondary) spelling within that dialect;
`V` primary-variant, `v` secondary-variant. `level N` is SCOWL frequency
(10 = very common, 95 = obscure).

Worked examples (verified against the live file):

```
# behaviour block
A Cv DV: behavior / B C D: behaviour      -> behaviour is British-only (no A tag)
# grey block
A Cv: gray / AV B C: grey                 -> grey carries AV: American variant too
# catalogue block
A: catalog / Av B: catalogue              -> catalogue carries Av: American variant too
# dialogue block (multi-line headword)
A B: dialogue / AV: dialog
A B Dv: dialog / Bv D: dialogue | <N> dialog box
                                          -> dialogue carries A: standard American
```

The tags are what make a blocking rule safe: a British token that *ever* appears
with an American tag (`A`, `Av`, or `AV`) is American-acceptable and must be
excluded from the auto corpus.

## Architecture

Three artifacts plus the runtime change.

### 1. Generator: `bin/gen_british_spellings.py` (dev-time)

Not on the runtime import path. Run by a maintainer to (re)build the corpus.

Algorithm:

1. Read a vendored `varcon.txt` (Latin-1). Accept a `--varcon PATH` arg; default
   to a checked-in vendored copy under `config/en-US/` so regeneration is
   offline and pinned. (Fetching a fresh VarCon is a deliberate, separate manual
   step, not automatic.)
2. Parse into **headword blocks**. Aggregate every cluster across *all* lines of
   a block before deciding anything (the `dialogue`/`dialog box` split above is
   why per-line parsing is wrong).
3. For each block, collect: the set of American forms (any token appearing in a
   cluster tagged `A`, including `Av`/`AV`), and the set of British forms (tokens
   in a cluster tagged `B` and never tagged `A*`).
4. Emit a `british<TAB>american` pair when: a British-only form exists, an
   American form exists, they differ, the British form has no apostrophe, and the
   block `level <= 60`. Pick the primary (non-variant) American form as the
   suggestion; fall back to a variant if that is all there is.
5. Apply the overrides file (below): remove `-` exclusions, add `+` additions.
6. Write the sorted, de-duplicated result to the data file with a provenance
   header (source URL, VarCon version note, license, generation is deterministic).

The generator is pure/stdlib and independently unit-tested. It performs no
network I/O itself; vendoring `varcon.txt` is a manual `curl` documented in the
file header and README. (Level cap 60 chosen from measured counts: on the order
of 2-3k British-only pairs at `<=60` before overrides, the conservative band the
user selected; the exact count settles after headword aggregation.)

### 2. Corpus: `config/en-US/british-american.txt` (generated, committed)

Two columns, tab-separated, sorted by British form, one pair per line, `#`
comments for the provenance header. This is the shipped artifact the runtime
reads. Regenerating it must produce a minimal diff.

### 3. Overrides: `config/en-US/british-american.overrides.txt` (hand-maintained)

Line formats:
- `+ british american` -- force-add a house-style pair even though VarCon marks
  the British form American-acceptable (e.g. `+ catalogue catalog`,
  `+ grey gray`, `+ cancelled canceled`, `+ aluminium aluminum`,
  `+ practise practice`, `+ programme program`).
- `- british` -- exclude a British-only pair that is a false positive in the
  house's American prose (e.g. `- dialogue` -- standard American, must never
  block).
- `#` comments explaining each non-obvious entry.

Overrides are the *only* place debatable calls live, so review is focused there,
not in 2.9k generated lines. The seed override set is derived from the current
inline dict's house-style entries plus the `dialogue`-class exclusions found
during design.

### 4. Runtime: `bin/prose_check.py`

- On import, load `config/en-US/british-american.txt` into a dict once (cached at
  module scope). The loader lives near the other config loaders and is stdlib
  file I/O; a missing/unreadable file is a hard, loud error (no silent empty map
  that would let every British spelling through).
- Replace the giant-alternation `_BRITISH_RE` with **tokenize-then-lookup**: scan
  prose with a fixed whole-word token regex (`(?<!\w)[A-Za-z]+(?!\w)`), lowercase
  each token, dict-lookup. The `\w` lookarounds preserve the old `\b`-on-`\w`
  boundary so a British fragment inside a snake_case or digit-adjacent identifier
  (`my_colour_var`, `colour2`) is not flagged. O(words), scales to any corpus
  size, and keeps exact offsets for line mapping.
- Everything else stays: `LOCAL_BRITISH_SPELLING` id, capitalization cast via
  `_match_case`, the `_is_american_english` language gate, blocking config.

The inline `_BRITISH_TO_AMERICAN` dict and `_BRITISH_RE` are deleted; the data
file replaces them.

## Data flow

```
(dev) curl varcon.txt -> config/en-US/varcon.txt (vendored, pinned)
(dev) gen_british_spellings.py + overrides.txt -> british-american.txt (committed)
(runtime) prose_check import -> load british-american.txt -> {british: american}
(runtime) check_blocks -> tokenize prose -> per-token lookup -> LOCAL_BRITISH_SPELLING
```

## Error handling

- Generator: unparseable VarCon line -> skip with a counted warning to stderr;
  a nonzero skip rate above a sanity threshold aborts (guards against a format
  change silently emptying the corpus). Missing overrides file -> treat as empty,
  warn. Override add whose British form is already American-tagged is expected;
  override that duplicates an auto entry is a no-op (warned).
- Runtime: data file missing/empty/unreadable -> raise, do not degrade to a
  no-op rule (a blocking rule that silently passes everything is the worst
  failure mode). This matches the "no silent-failure guards" house rule.

## Testing

- **Generator unit tests** (hermetic, tiny inline VarCon fixtures): British-only
  extraction; exclusion of `A`/`Av`/`AV`-tagged British forms (grey, catalogue,
  dialogue all excluded from auto); multi-line headword aggregation (dialogue not
  emitted); level-cap filtering; primary-vs-variant American selection; override
  add/remove application; deterministic sorted output.
- **Runtime tests** (extend `tests/test_local_rules.py`): the existing #11 cases
  (behaviour flagged, catalogue flagged via override, colour->color suggestion,
  offset correctness, capitalization, greyhound not flagged, American clean) now
  pass sourced from the corpus. Add: a loader-failure test (missing data file
  raises), and a token-boundary test drawn from the corpus.
- **Full gate**: `pytest`, `ruff`, `shellcheck` all green.

## Validation loop (the "from data" part)

After the corpus lands, run the checker across the user's `~/Developer` repos
(the sweep). Every `LOCAL_BRITISH_SPELLING` hit is reviewed; genuine British
spellings confirm coverage, false positives (a legitimate American word VarCon
mistags, or a domain term) become `-` exclusions. The overrides file thus grows
from real evidence, not speculation. Findings are reported generically per the
privacy rule (mechanism and counts, not private repo content).

## Out of scope

- Other dialects (en-GB, en-AU) as *targets* -- the language gate already opts
  them out; a future en-GB bundle is separate work.
- Suffix-rule inference (`-our`->`-or`) -- rejected: high false positive, unsafe
  for a blocking rule. The curated corpus is the deliberate alternative.
- Auto-fetching VarCon at build/runtime -- vendored and pinned instead.

## Rollout

This supersedes the inline map committed on `fix/en-us-british-spelling-11`. It
lands on the same branch (or a follow-up) so issue #11 ships the corpus-backed
version rather than the hand list, avoiding a throwaway intermediate in `main`.
