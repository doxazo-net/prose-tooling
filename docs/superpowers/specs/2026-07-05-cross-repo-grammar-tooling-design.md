# Cross-repo grammar / prose linting

Design doc. Status: approved 2026-07-05. Scope: a single, centrally-configured
grammar and prose linter wired into git hooks across all `~/Developer` repos,
built on a local LanguageTool server.

## Problem

The repos already run `typos` (spelling) and `markdownlint` (Markdown markup),
but nothing checks *grammar or prose style*. `typos` is a spell checker; it
cannot catch subject-verb disagreement, tense errors, missing serial commas,
passive voice, wordiness, or the refinement-level issues a pedantic writer
wants flagged. Vale, considered first, is a pattern/style linter, not a
parser-based grammar engine, so it does not fill this gap either.

The goal: real grammar checking (LanguageTool), enforced in git hooks, driven
by one central house-style config, applied uniformly across repos that span
Rust, Go, Python, and Node, most of whose prose lives in Markdown.

## Constraints

- **Privacy (hard).** Repo content is private. Nothing is ever sent to
  LanguageTool's public API. All checking runs against a *local* server.
- **Speed.** LanguageTool is a JVM app; cold start is 3-8s, unacceptable
  per-commit. A resident local server (started once) is therefore required.
- **No per-repo runtime pollution.** Rust/Go/Python repos must not gain a
  Node or Python dependency tree. Client dependencies live in the central
  tooling repo, not in target repos.
- **Markdown-aware.** Feeding raw Markdown to a plain-text checker produces
  false positives on syntax (`**bold**`, links, code fences). Markup must be
  excluded from checking while preserving source offsets.
- **Central, tunable config.** A pedantic maintainer will iterate on rules; a
  rule change should propagate from one canonical place, not be copied per repo.
- **Multi-language ready.** Future projects may ship prose in other natural
  languages. Language is a first-class config axis from day one; en-US is
  merely the first bundle. (Build en-US only now; others are added on demand.)

## Architecture

Four components.

### 1. LanguageTool server (OrbStack)

The official `erikvl87/languagetool` Docker image runs as an OrbStack
container bound to `localhost:8081`, set to auto-start. OrbStack keeps it
alive and restarts it on boot, so there is no `launchd` agent or local Java
install to maintain. The client POSTs to it.

- No n-gram / false-friends data in v1 (large download; add later if wanted).
- Single server instance serves every language via the per-request `language`
  parameter, so multi-language needs no additional infrastructure.

### 2. Central config repo: `~/Developer/prose-tooling/`

A new **local-only** git repo (no remote, like the auto-memory dir). Holds all
config, the client, and installer. Layout:

```
prose-tooling/
  bin/
    prose-check.py          # the hook client (see below)
    prose-lint-server.sh     # start/stop/status the OrbStack container
    install.sh               # wire a target repo's git hooks
  config/
    dictionary.txt           # GLOBAL shared allowlist (proper nouns, project names)
    en-US/
      severity.toml          # blocking vs advisory rule map for en-US
      dictionary.txt         # en-US-specific allowlist
      custom-rules/          # e.g. em-dash rule (LT XML "false" rules)
    # fr/, de/, ... added on demand, same shape
  .venv/                     # client deps (markdown parser); NOT in target repos
  docs/superpowers/specs/    # this doc
```

House rules that are English-specific (serial comma, em-dash, one-space) live
under `config/en-US/`. Each language bundle carries its own `severity.toml`,
dictionary, and custom rules. The global `config/dictionary.txt` merges into
every language's dictionary.

### 3. Hook client: `bin/prose-check.py`

Python 3 with its dependencies in `prose-tooling/.venv`, so target repos stay
dependency-free. Flow:

1. Read staged files: `git diff --cached --name-only --diff-filter=ACM`,
   filtered to `.md`, `.markdown`, `.mdx`, `.txt`.
2. Resolve the language for each file (see Language selection) and load the
   matching `config/<lang>/` bundle plus the global dictionary.
3. Parse each Markdown file and build the LanguageTool **`data` annotation
   payload** (`{"annotation": [{"text": ...}, {"markup": ...},
   {"markup": "\n\n", "interpretAs": "\n\n"}, ...]}`). Prose becomes `text`
   nodes; syntax (fences, inline code, link URLs, images, frontmatter) becomes
   `markup` and is excluded from checking. This is LanguageTool's supported
   markup path and preserves offsets, so results map back to source lines.
4. POST to `localhost:8081/v2/check` with `language=<lang>`, `level=picky`,
   and the bundle's `enabledRules` / `disabledRules` / `disabledCategories`.
5. Partition each returned match by `ruleId` (and category) using the
   bundle's `severity.toml`: matches whose rule is on the `blocking` list fail
   the commit; everything else prints as advisory.
6. Print findings as `path:line:col [ruleId] message` with the top suggestion.
7. Exit non-zero only if at least one blocking match was found. Advisory
   matches print but do not affect exit code.

If the server is unreachable, the client prints a clear error telling the user
to start it (`prose-lint-server.sh start`) and exits non-zero (a fail-loud
guard, not a silent skip).

### 4. Per-repo wiring: `bin/install.sh <repo>`

Detects the target repo's existing hook mechanism and adds exactly one step,
composing with (never replacing) the existing `typos` / `markdownlint` checks:

- Repos with `.githooks/pre-commit` (stillwater-style, `core.hooksPath`):
  append a call to the central `prose-check.py`.
- Repos using the pre-commit framework (canticle etc.): add a
  `repo: local` hook entry that calls the central `prose-check.py`.

The target repo's default language and any path-based overrides are recorded
in a small per-repo marker the installer writes (e.g. `.prose-lint.toml`:
`lang = "en-US"`, optional `[[override]] path = "**/fr/**" lang = "fr"`).

## House rules (en-US bundle)

From the maintainer's answers. `level=picky` unlocks the pedantic rules;
`severity.toml` decides block vs warn.

| Rule | Setting | Severity |
|------|---------|----------|
| Language | en-US | -- |
| Serial (Oxford) comma | require | blocking |
| One space after sentence punctuation | enforce | blocking |
| Em-dash usage | flag (client-side local rule) | blocking |
| Spelling | en-US dict + shared allowlist | blocking |
| Passive voice | flag | advisory |
| Contractions | allow | off |
| Long / complex sentences | aggressive threshold | advisory |
| Wordiness / weasel words / cliche | flag | advisory |

The em-dash policy mirrors the maintainer's global no-em-dash rule (favor
dashes, commas, parens). LanguageTool has no default em-dash rule, so this is
a small custom rule in `config/en-US/custom-rules/`.

**Exact rule IDs are resolved at implementation** against the running server's
`/v2/rules` listing (and the LanguageTool rule catalog), not asserted here.
Known anchors: `level=picky` for the style set; passive/wordiness/readability
live in the STYLE category; serial comma and double-space are dedicated rules;
em-dash is custom. `severity.toml` is authored from that resolved list.

## Language selection

- Per-repo default language, set by `install.sh` in `.prose-lint.toml`
  (`en-US` default).
- Optional per-path overrides for genuinely bilingual repos (e.g.
  `**/fr/**` or `*.fr.md` -> `fr`).
- LanguageTool's `auto` detection is deliberately **not** used as the default:
  it is unreliable on short text and would misclassify occasional foreign-
  language strings (e.g. the French values already allowlisted in `typos`).

## Rollout (calibration)

Blocking an untuned grammar engine invites the `--no-verify` reflex (which the
maintainer's rules forbid), so the config is calibrated before it can block.

- **Phase 1 - stillwater, advisory-only.** Install with an empty `blocking`
  list. Run over existing docs. Tune: seed the dictionary from real false
  positives, demote noisy rules, confirm Markdown extraction yields no
  syntax false positives.
- **Phase 2 - stillwater, blocking.** Promote the four blocking rules (serial
  comma, one-space, em-dash, spelling) into `severity.toml`.
- **Phase 3 - roll out.** `install.sh` the tuned central config to the other
  repos, honoring each repo's existing hook mechanism.

## Testing

- Fixture Markdown files with known violations; assert the client reports the
  expected rule IDs and the expected exit code (blocking vs advisory).
- A fixture containing fenced code blocks and inline code with
  deliberately "wrong" prose inside them; assert **zero** findings, proving
  the annotation-based markup exclusion works.
- A server-down fixture; assert the client fails loud (non-zero, clear
  message), not silently.

## Non-goals (v1)

- **Vale** - deferred. Optional later layer for house-style/terminology that
  LanguageTool does not cover; not needed for grammar.
- **CI integration** - local hooks first. The same client and server can be
  reused in CI later without redesign.
- **n-gram / false-friends data** - large; add only if a real need appears.
- **Public LanguageTool API** - never; privacy constraint.

## Related, out of scope (tracked separately)

Prose-*drafting* helpers (generating issue bodies, PR bodies, review comments)
are an authoring aid, not a linter, and belong in the cc-orchestrator workflow
tooling. Tracked as cc-orchestrator issue #219, not in this spec.

## Implementation notes (as built 2026-07-05)

Deviations from the design above, discovered while building against a live
`erikvl87/languagetool` server:

- **Client filename is `bin/prose_check.py`** (underscore), so it is importable
  by the test suite; the design's `prose-check.py` references mean this file.
- **Em-dash and one-space are client-side local rules, not LanguageTool XML
  rules.** The free server has no em-dash rule and does not flag double spaces
  even at `level=picky`, so both are deterministic regex rules in the client
  (`LOCAL_EM_DASH`, `LOCAL_DOUBLE_SPACE`), emitting LanguageTool-shaped matches
  through the same offset/severity pipeline. No `config/<lang>/custom-rules/`
  dir is needed and it was removed.
- **The dictionary is a client-side post-filter.** The free server has no
  per-request custom dictionary, so allowlisted words are dropped from
  spelling (TYPOS) matches client-side after the check.
- **Resolved rule IDs:** `SERIAL_COMMA_ON` (require Oxford comma, blocking),
  `MORFOLOGIK_RULE_EN_US` (spelling, blocking), `PASSIVE_VOICE_SIMPLE`
  (advisory). Wordiness / weasel-word rules are largely premium-gated on the
  free server, so advisory wordiness coverage is partial (documented limit).
- **Findings print as `path:line`** (line-level). markdown-it does not expose
  reliable source columns for inline content, so precise columns are deferred.
