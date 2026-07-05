#!/usr/bin/env bash
# install.sh -- print the git-hook wiring to adopt prose-lint in a target repo.
#
# By design this PRINTS the snippet and instructions rather than mutating the
# target repo: incorporation into a repo like stillwater goes through that
# repo's own PR / review gates, not a side-channel edit. Run it, read it, and
# paste the snippet into the repo's hook as part of that repo's change.
#
# Usage: install.sh [/path/to/target/repo]
set -euo pipefail

TOOLING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT="${TOOLING_DIR}/.venv/bin/python ${TOOLING_DIR}/bin/prose_check.py"
TARGET="${1:-.}"

echo "prose-tooling dir : ${TOOLING_DIR}"
echo "target repo       : $(cd "${TARGET}" && pwd)"
echo

if [ -f "${TARGET}/.githooks/pre-commit" ]; then
	MECH="Detected .githooks/pre-commit (core.hooksPath style)."
elif [ -f "${TARGET}/.pre-commit-config.yaml" ]; then
	MECH="Detected .pre-commit-config.yaml (pre-commit framework)."
else
	MECH="No known hook mechanism detected; choose one below."
fi
echo "${MECH}"
echo
echo "1) Ensure the LanguageTool server is running:"
echo "   ${TOOLING_DIR}/bin/prose-lint-server.sh start"
echo
echo "2a) For a .githooks/pre-commit (bash) repo, add this section:"
cat <<EOF

# prose-lint -- LanguageTool grammar/prose on staged markdown (central config)
STAGED_PROSE=\$(git diff --cached --name-only --diff-filter=ACM -- '*.md' '*.txt' || true)
if [ -n "\$STAGED_PROSE" ]; then
    if ! PROSE_OUTPUT=\$(echo "\$STAGED_PROSE" | tr '\\n' '\\0' \\
            | xargs -0 ${CLIENT} --lang en-US -- 2>&1); then
        echo "FAIL prose-lint:"; echo "\$PROSE_OUTPUT"; exit 1
    fi
    echo "\$PROSE_OUTPUT"   # advisories (exit 0)
fi
EOF
echo
echo "2b) For a pre-commit-framework repo, add a repo: local hook:"
cat <<EOF

  - repo: local
    hooks:
      - id: prose-lint
        name: prose-lint (LanguageTool)
        entry: ${CLIENT} --lang en-US --
        language: system
        files: '\\.(md|txt)\$'
EOF
echo
echo "The client exits 1 on a blocking finding, 2 if the server is unreachable."
