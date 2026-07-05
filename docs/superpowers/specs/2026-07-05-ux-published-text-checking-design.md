# UX / published-text checking (v1: i18n microcopy + suppression)

Design doc. Status: approved 2026-07-05. Extends the Markdown grammar linter
(see `2026-07-05-cross-repo-grammar-tooling-design.md`) to check user-facing
UI copy, starting with i18n microcopy, and adds a cross-cutting suppression
directive.

## Problem

The linter checks hand-written Markdown, but the text users actually read most
lives elsewhere: in-app microcopy in `internal/i18n/locales/*.json` and
generated documentation published to the ProperDocs (MkDocs) site. Microcopy
is where pedantic checking pays off most (users see every string), yet the
Markdown docs profile is wrong for it: UI strings are fragments (button labels,
column headers), so rules like `UPPERCASE_SENTENCE_START`, terminal-punctuation,
and sentence-fragment checks would flood false positives. Some strings should
never be checked at all (tooltips full of product jargon, log-output copy), so
an inline opt-out is required.

## v1 scope

- **Surface:** `en.json` only (the authored source locale). fr/ja are
  translation QA, deferred; the extractor is built so adding them is config.
- **Suppression primitive:** foundational, ships in v1 across surfaces.
- **Deferred:** generated docs / docs-as-code (its own later spec), Go-string /
  log-output checking, non-source locales.

## Approach

Extend the existing client with a pluggable **extractor** layer rather than a
second tool. The Markdown path becomes one extractor; i18n becomes another.
This reuses the entire downstream pipeline (server check, severity partition,
allowlist, line mapping, local rules) and keeps one client and one config
system. Rejected: a separate i18n tool (duplicates the pipeline and config).

## Components

### 1. Extractor abstraction

Refactor so the current `extract_blocks` (Markdown) is one of several
extractors, each returning the same `(text, source_line)` block shape the
downstream pipeline already consumes. Add `extract_i18n(json_text, ignore)`:
parse the locale JSON, walk string **values** (skip keys), and emit each value
as a block tagged with its source line in the JSON file. Dispatch by file
extension (`.md`/`.txt` -> markdown, `.json` -> i18n) with a `--format`
override. The block contract stays identical, so `combine_blocks`,
`line_for_offset`, `partition_matches`, `filter_allowlisted`, and the local
rules are unchanged.

### 2. Microcopy rule profile

A new central bundle `config/en-US-microcopy/severity.toml`, distinct from the
docs `en-US` bundle. It disables rules that misfire on labels/fragments
(`UPPERCASE_SENTENCE_START`, missing-terminal-punctuation, sentence-fragment,
sentence-start capitalization) on top of the docs bundle's disabled set, and
keeps real grammar plus spelling (advisory). Calibrated against the actual
`en.json`, the same method used for the docs profile. A `--profile` flag
selects the bundle; the i18n format defaults to `microcopy`, markdown to `docs`.

### 3. Placeholder masking

i18n interpolation is masked to a neutral token before checking, so
LanguageTool never flags it: `{status}`, `{count}`, `{{name}}`, `%s`, `%d`,
`%(name)s`. Masking happens inside `extract_i18n` (analogous to inline-code
exclusion in Markdown), preserving offsets within the value.

### 4. Suppression primitive (two surface-appropriate forms)

- **Markdown:** inline HTML-comment directives, parsed in the markdown
  extractor and never rendered:
  - `<!-- prose-lint-disable -->` / `<!-- prose-lint-enable -->` (region)
  - `<!-- prose-lint-disable-line -->` (same line)
  - `<!-- prose-lint-disable-next-line -->` (following line)
  Suppressed lines/regions are dropped before checking.
- **i18n JSON:** key-pattern globs plus an explicit per-key list. A value is
  skipped if its key matches any glob or appears in the explicit list, e.g.
  `ignore_keys = ["*.tooltip", "*.log_*", "artist_duplicates.col_mbid"]`.

### 5. Config ownership

- **Central (prose-tooling):** the extractors, the microcopy rule bundle, and
  Markdown directive parsing (shared across all repos).
- **Repo-local (target repo, e.g. stillwater):** the i18n key-ignore config.
  Those tooltip/log key conventions are the repo's, not shared, so they live in
  a repo-local `.prose-lint.toml` `[i18n]` block (`ignore_keys = [...]`) passed
  to the extractor via `--i18n-ignore <file>` (or discovered at the repo root).

## Data flow

```
file --dispatch--> extractor --> blocks[(text,line)] --> combine -->
  LanguageTool check (profile bundle) + local rules -->
  allowlist filter --> severity partition --> path:line findings
```

Only the extractor and profile-selection differ per surface; everything after
`blocks` is the existing, tested pipeline.

## Decomposition (separate PRs; foundation first)

1. **prose-tooling PR A (foundation):** extractor-abstraction refactor +
   Markdown suppression directives. No behavior change for existing Markdown
   except the new directives.
2. **prose-tooling PR B:** `extract_i18n` + placeholder masking + JSON
   key-ignore + the microcopy bundle, calibrated on `en.json`.
3. **stillwater PR (incorporation, its own issue like #2239):** wire `en.json`
   into the hook + CI, with the repo-local `.prose-lint.toml` `[i18n]` ignore
   config.

## Testing

- Unit (TDD): i18n value extraction (keys skipped, nesting handled), placeholder
  masking, key-glob + per-key ignore, and each Markdown directive
  (disable/enable region, disable-line, disable-next-line).
- A fixture proving an ignored key and a masked placeholder produce no findings.
- Live calibration on `en.json` to tune `config/en-US-microcopy/severity.toml`
  before the stillwater incorporation, same as the docs calibration.

## Non-goals (v1)

- Generated docs / docs-as-code coverage (separate later spec; the generated
  Markdown is already lintable by the docs profile, with fixes routed upstream
  to the Go `desc:` source).
- fr/ja locale checking (structure supports it; not enabled).
- Go-string / log-output extraction (a later surface; v1 covers tooltip/log
  microcopy via key-pattern ignores, not by checking Go source).
- A separate i18n tool (rejected in favor of the extractor abstraction).
