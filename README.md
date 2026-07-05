# prose-tooling

Cross-repo grammar and prose linting for the `~/Developer` repos, built on a
local [LanguageTool](https://languagetool.org) server. Fills the gap left by
`typos` (spelling) and `markdownlint` (markup): real, parser-based grammar and
style checking, driven by one central house-style config, wired into git hooks.

Design: [`docs/superpowers/specs/2026-07-05-cross-repo-grammar-tooling-design.md`](docs/superpowers/specs/2026-07-05-cross-repo-grammar-tooling-design.md).

## Layout

- `bin/prose-lint-server.sh` -- start/stop/status the LanguageTool container (OrbStack).
- `bin/prose_check.py` -- the Markdown-aware client (deps in `.venv`, so target repos stay dependency-free).
- `bin/install.sh` -- prints the git-hook wiring to adopt this in a target repo.
- `config/<lang>/severity.toml` -- per-language rules + blocking-vs-advisory map.
- `config/dictionary.txt`, `config/<lang>/dictionary.txt` -- spelling allowlists.

## Use

```sh
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
bin/prose-lint-server.sh start
./.venv/bin/python bin/prose_check.py path/to/doc.md
```

Exit codes: `0` clean or advisory-only, `1` a blocking finding, `2` server
unreachable. The client auto-starts the container if it is stopped (one-time
~15s cost on the first commit after a stop); pass `--no-autostart` to disable.

## How it works

The client parses Markdown, feeds only prose to LanguageTool via its `data`
annotation API (markup excluded, source offsets preserved), merges in
client-side local rules, drops allowlisted spellings, then splits findings into
blocking (fails the commit) and advisory (printed, exit 0) per
`config/<lang>/severity.toml`. Everything runs against a LOCAL server -- repo
content is never sent to the public API.

### House rules (en-US)

Blocking: em-dash (`LOCAL_EM_DASH`), one space after sentence punctuation
(`LOCAL_DOUBLE_SPACE`), Oxford/serial comma (`SERIAL_COMMA_ON`), spelling
(`MORFOLOGIK_RULE_EN_US`). Advisory: passive voice, readability, and wordiness
(the last is partly premium-gated on the free server). Em-dash and double-space
are deterministic client-side rules because the free server has no rule for
them.

## Tests

```sh
./.venv/bin/python -m pytest tests/
```

Unit tests are hermetic; the integration tests skip unless a server is running.
