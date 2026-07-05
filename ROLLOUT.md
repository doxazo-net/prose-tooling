# Rollout tracker

prose-tooling is a local-only repo (no GitHub remote), so cross-repo rollout is
tracked here rather than as a GitHub issue with no home. Per-repo adoption lands
as an issue in each target repo (via `bin/install.sh`), calibrated after
stillwater.

## Status

- [x] Tooling built and tested (client, server, en-US config) -- 25 tests green.
- [x] cc-orchestrator #219 -- lint issue/PR/comment bodies with the same config.
- [ ] stillwater -- adopt into `.githooks/pre-commit` + `docs.yml` CI (calibration target).
      Tracked in sydlexius/stillwater #2239.
- [ ] Calibrate `config/en-US/severity.toml` + dictionary against stillwater docs.
- [ ] Roll out to remaining repos after calibration, each via its own issue:
  - [ ] canticle (pre-commit framework)
  - [ ] media-automation (pre-commit framework)
  - [ ] genogram (pre-commit framework)
  - [ ] cc-orchestrator (its own docs)
  - [ ] others as prose accumulates

## Future extensions (specced, not built)

- **UX / published-text checking** - design approved 2026-07-05, spec at
  `docs/superpowers/specs/2026-07-05-ux-published-text-checking-design.md`.
  v1 = i18n microcopy (`en.json`) via an extractor abstraction + a
  `en-US-microcopy` profile + a suppression primitive (Markdown HTML-comment
  directives; i18n key-pattern/per-key ignores). Decomposes into: (A)
  prose-tooling foundation (extractor refactor + Markdown directives), (B)
  prose-tooling i18n extractor + microcopy profile, (C) stillwater incorporation.
  Deferred: generated docs / docs-as-code, fr/ja locales, Go-string/log checking.

## Notes

- Blocking rules (en-US): LOCAL_EM_DASH, LOCAL_DOUBLE_SPACE, SERIAL_COMMA_ON,
  MORFOLOGIK_RULE_EN_US. Everything else advisory.
- Multi-language: add `config/<lang>/` bundles on demand; no infra change.
