# Genericize B: example configs, documented schema, scaffolding

Design doc. Status: approved 2026-07-11. Scope: the "adopt prose-tooling in your
repo" half of #2 (tracked as #16). Ship copy-ready example configs, a scaffolding
command that writes a starter config into a target repo, a documented config
schema, and an ergonomic `.prose-lint.toml` auto-load. Part A (pluggable
backends + container-runtime abstraction, #15) is separate and lands independently.

## Problem

Adopting prose-tooling today means reverse-engineering the author's central
config: there is no starter template, no documented schema, and the repo-local
`.prose-lint.toml` is only loaded via an explicit `--i18n-ignore` flag. `install.sh`
prints hook wiring but writes nothing, so a new repo has no config to point at.
The goal: a new repo can run one command to get a working starter config plus the
hook wiring, and can read a schema doc instead of the source.

## Constraints

- **Additive and low-risk.** No change to the checking pipeline or rule
  semantics. New files (`examples/`, `docs/CONFIG.md`), one new bash code path in
  `install.sh`, one small loader convention in `bin/prose_check.py`.
- **Never clobber the adopter's files.** The scaffold backs up an existing
  `.prose-lint.toml` before writing; it never overwrites silently.
- **Stdlib-first.** No new dependencies. `install.sh` stays bash + `shellcheck`
  clean; Python changes stay stdlib.
- **Bash / macOS + Linux.** Windows portability is part A's concern (#15).
- **One source of truth for the hook snippet.** The snippet lives in
  `examples/pre-commit-snippet.sh`; `install.sh` reads/prints it rather than
  embedding a second copy.

## Architecture

Four additive pieces.

### 1. `examples/` directory (new)

Copy-ready, heavily commented starter templates. Deliberately more minimal than
the author's tuned `config/` so an adopter starts simple.

- `examples/config/en-US/severity.toml` — minimal docs profile: `language`,
  `level`, a short `disabled_rules` set, and `blocking` limited to the
  deterministic rules. Comments explain each key.
- `examples/config/en-US/dictionary.txt` — a few example allowlist entries with a
  comment explaining the format.
- `examples/config/en-US-microcopy/severity.toml` — microcopy starter.
- `examples/.prose-lint.toml` — commented `[i18n] ignore_keys` example.
- `examples/pre-commit-snippet.sh` — the git-hook snippet (bash), extracted
  verbatim from `install.sh`'s current here-doc so there is a single source.

The tool's own `config/` is unchanged; `examples/config/` is a separate, simpler
starting point an adopter copies and customizes.

### 2. Scaffolding — extend `bin/install.sh`

`install.sh` already takes a target repo and prints hook guidance. Extend it:

- `bin/install.sh <target>` (default): write `<target>/.prose-lint.toml` from
  `examples/.prose-lint.toml` **only if absent**; if present, copy it to
  `<target>/.prose-lint.toml.bak` first and print a notice (never a silent
  overwrite). Then print the hook wiring (existing per-mechanism logic), now
  sourced from `examples/pre-commit-snippet.sh`. The printed hook uses the tool's
  shipped `config/` by default (no per-repo config dir needed) plus the
  auto-loaded `.prose-lint.toml`.
- `bin/install.sh <target> --with-config`: additionally copy `examples/config/`
  to `<target>/.prose-lint-config/` (skipping any file that already exists, with
  a per-file notice) for adopters who want to customize severity/dictionaries;
  the printed hook then adds `--config-dir <target>/.prose-lint-config`.

Writes are confined to `<target>/.prose-lint.toml` and (opt-in)
`<target>/.prose-lint-config/`. The scaffold never edits `.git/` or an existing
hook — hook application stays the adopter's paste step, matching the current
"print, don't mutate" stance for the risky part.

### 3. Config schema docs — `docs/CONFIG.md`

Documents every config surface so adopters read docs, not source:

- `severity.toml`: `language`, `level`, `enabled_rules`, `disabled_rules`,
  `disabled_categories`, `blocking` — each with meaning, type, and the
  blocking-vs-advisory model (deterministic low-FP rules only block).
- `dictionary.txt` (per-language + global `config/dictionary.txt`): format,
  case-insensitive matching, merge order.
- `.prose-lint.toml`: `[i18n] ignore_keys` (glob + exact), and the auto-load
  convention below.
- How `--config-dir` lets a repo use its own config without editing the tool.

`README.md` links `docs/CONFIG.md` from its config section.

### 4. `.prose-lint.toml` auto-load — `bin/prose_check.py`

Today `.prose-lint.toml` is read only when `--i18n-ignore <path>` is passed.
Add a predictable convention: when `--i18n-ignore` is **not** given, load
`./.prose-lint.toml` (process cwd) if it exists; otherwise no ignores. The
explicit flag always wins. This lets the scaffold's hook snippet omit the flag.

Precedence: `--i18n-ignore <path>` (explicit) > `./.prose-lint.toml` (if present)
> empty. Documented in `docs/CONFIG.md` and surfaced in `--help`.

## Data flow (adoption)

```
adopter runs:  <tooling>/bin/install.sh /path/to/their/repo [--with-config]
  -> writes .prose-lint.toml (backup if present); optional .prose-lint-config/
  -> prints hook snippet (from examples/pre-commit-snippet.sh) to paste
adopter's commit -> hook runs prose_check.py
  -> auto-loads ./.prose-lint.toml -> checks staged prose against shipped (or copied) config
```

## Error handling

- Scaffold: target not a directory / not a git repo -> clear error, exit non-zero,
  write nothing. Existing `.prose-lint.toml` -> back up then write, print the
  backup path. `--with-config` onto existing files -> skip each with a notice,
  never overwrite.
- Auto-load: a malformed `./.prose-lint.toml` surfaces the parse error loudly
  (no silent empty-ignores fallback that would mask a typo) — consistent with the
  no-silent-failure house rule. A missing file is the normal no-ignores case.

## Testing

- **Scaffold (bash, hermetic in a tmp dir):** writes `.prose-lint.toml` when
  absent; backs up when present (original preserved in `.bak`); `--with-config`
  copies the config tree and skips pre-existing files; errors on a non-repo
  target; the printed hook references the shipped config (and `--config-dir` with
  `--with-config`). Driven from `tests/` via `subprocess`, `shellcheck` clean.
- **Auto-load (pytest):** `./.prose-lint.toml` present + no flag -> its
  `ignore_keys` apply; explicit `--i18n-ignore` overrides the cwd file; no file ->
  empty; malformed file -> raises.
- **Examples validity:** a test loads every `examples/config/*/severity.toml`
  via `load_bundle` and parses `examples/.prose-lint.toml`, so the shipped
  starters can never rot into an invalid state.
- Full gate: `pytest`, `ruff`, `shellcheck` green.

## Out of scope (part A / #15)

- Pluggable backends (binary/JAR, alternate container runtimes), runtime
  abstraction in `prose-lint-server.sh`, Windows, and `install.sh` server-start
  guidance per runtime. B's scaffold uses the existing docker/OrbStack server
  path unchanged; A generalizes it later.
- Auto-discovering a config *dir* by walking parent directories. B keeps
  `--config-dir` explicit (documented); only `./.prose-lint.toml` auto-loads.

## Rollout

One PR closing #16, off `main`. Well under 1KLOC (example files + a bash code
path + a docs file + a small loader change + tests). #2 stays open until A (#15)
also lands.
