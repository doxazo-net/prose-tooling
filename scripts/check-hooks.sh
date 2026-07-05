#!/usr/bin/env bash
# Verify the git pre-commit hook is wired via core.hooksPath = .githooks.
set -euo pipefail

want=".githooks"
got="$(git config --get core.hooksPath || true)"
if [ "$got" != "$want" ]; then
	echo "core.hooksPath is '${got:-unset}', expected '$want'. Run: make hooks" >&2
	exit 1
fi
if [ ! -x ".githooks/pre-commit" ]; then
	echo ".githooks/pre-commit is not executable. Run: chmod +x .githooks/pre-commit" >&2
	exit 1
fi
echo "hooks OK (core.hooksPath=$got, pre-commit executable)"
