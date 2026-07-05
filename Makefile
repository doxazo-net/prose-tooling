.PHONY: hooks doctor check lint test server

## hooks: install the pre-commit hook (sets core.hooksPath = .githooks)
hooks:
	@git config core.hooksPath .githooks
	@chmod +x .githooks/pre-commit
	@./scripts/check-hooks.sh

## doctor: verify hook wiring without modifying anything
doctor:
	@./scripts/check-hooks.sh

## lint: ruff + shellcheck (mirrors CI)
lint:
	@./.venv/bin/python -m ruff check bin/ tests/
	@shellcheck bin/*.sh

## test: run the test suite
test:
	@./.venv/bin/python -m pytest -q

## check: lint + test (the full local gate)
check: lint test

## server: start the LanguageTool container
server:
	@./bin/prose-lint-server.sh start
