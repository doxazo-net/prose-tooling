# prose-lint -- LanguageTool grammar/prose on staged markdown (central config)
STAGED_PROSE=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' '*.txt' || true)
if [ -n "$STAGED_PROSE" ]; then
    if ! PROSE_OUTPUT=$(echo "$STAGED_PROSE" | tr '\n' '\0' \
            | xargs -0 __CLIENT__ --lang en-US -- 2>&1); then
        echo "FAIL prose-lint:"; echo "$PROSE_OUTPUT"; exit 1
    fi
    echo "$PROSE_OUTPUT"   # advisories (exit 0)
fi
