[mode: plan]
[model: sonnet]
[effort: medium]

## Summary

Adopt the central `prose-tooling` LanguageTool grammar/prose linter into stillwater's `.githooks/pre-commit` and mirror it as a CI job in `docs.yml`, so staged Markdown is grammar-checked the same way locally and in CI.

## Problem / Motivation

The pre-commit hook and CI already run `typos` (spelling) and `markdownlint` (markup), but nothing checks grammar or prose style (missing serial commas, passive voice, em-dashes, one-space-after-period, wordiness). A separate, self-contained tool now exists at `~/Developer/prose-tooling` (a local LanguageTool server plus a Markdown-aware client with a central house-style config); see its design spec at `docs/superpowers/specs/2026-07-05-cross-repo-grammar-tooling-design.md`. stillwater is the designated calibration target for that rollout. This issue wires it in following the existing hook idiom, keeping local and CI in agreement as the hook header promises.

## Proposed Solution

Add one numbered section to `.githooks/pre-commit`, placed with the other doc checks (after markdownlint), following the `typos` idiom exactly: gate on staged `*.md`/`*.txt`, `command -v` guard that warns-and-skips when the client is absent (matching the mermaid opt-in check), run the central client, print advisories, and FAIL only on a blocking finding (client exit 1). The client itself fails loud (exit 2) if the LanguageTool server is unreachable, so an installed-but-server-down state never silently passes.

`bin/install.sh` in prose-tooling emits the exact snippet to paste, so the block lands identically here and in other repos.

Mirror the check as a CI job in `.github/workflows/docs.yml` alongside the existing `typos` step, running LanguageTool as a service container rather than OrbStack, so CI matches the local hook.

Calibration first: run the client over existing docs and tune the central `severity.toml` + dictionary before enabling blocking, so contributors do not hit false positives. The four blocking rules (serial comma, one space, em-dash, spelling) are deterministic and low-false-positive; the noisy style rules stay advisory.

## Acceptance Criteria

- [ ] `.githooks/pre-commit` gains a prose-lint section that checks staged `*.md`/`*.txt` via the central prose-tooling client, warns-and-skips when the client is absent, prints advisories, and fails the commit only on a blocking finding.
- [ ] `make doctor` / `check-hooks.sh` still pass; the new section does not break the hook for contributors without the tool installed.
- [ ] A CI job in `docs.yml` mirrors the check (LanguageTool service container), so local and CI agree.
- [ ] The central `severity.toml` + dictionary are calibrated against stillwater's existing docs before blocking is enabled (advisory-only first, then promote).

## Additional Context

- Depends on `~/Developer/prose-tooling` (spec: `docs/superpowers/specs/2026-07-05-cross-repo-grammar-tooling-design.md`). Client + server + en-US config already built and tested (25 tests green against a live LanguageTool container).
- Related: cc-orchestrator #219 (lint issue/PR/comment bodies with the same config).
- Out of scope: prose generation; changes to the `typos`/`markdownlint` steps.
