# Rollout tracker

prose-tooling is a local-only repo (no GitHub remote), so cross-repo rollout is
tracked here rather than as a GitHub issue with no home. Per-repo adoption lands
as an issue in each target repo (via `bin/install.sh`), calibrated after
stillwater.

## Status

- [x] Tooling built and tested (client, server, en-US config) -- 25 tests green.
- [x] cc-orchestrator #219 -- lint issue/PR/comment bodies with the same config.
- [ ] stillwater -- adopt into `.githooks/pre-commit` + `docs.yml` CI (calibration target).
      Issue body ready; filing blocked by a local PreToolUse hook on
      `gh issue create` against sydlexius/stillwater (maintainer to file).
- [ ] Calibrate `config/en-US/severity.toml` + dictionary against stillwater docs.
- [ ] Roll out to remaining repos after calibration, each via its own issue:
  - [ ] canticle (pre-commit framework)
  - [ ] media-automation (pre-commit framework)
  - [ ] genogram (pre-commit framework)
  - [ ] cc-orchestrator (its own docs)
  - [ ] others as prose accumulates

## Notes

- Blocking rules (en-US): LOCAL_EM_DASH, LOCAL_DOUBLE_SPACE, SERIAL_COMMA_ON,
  MORFOLOGIK_RULE_EN_US. Everything else advisory.
- Multi-language: add `config/<lang>/` bundles on demand; no infra change.
