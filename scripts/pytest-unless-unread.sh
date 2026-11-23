#!/usr/bin/env bash
#
# Run `pytest`, unless every file the commit changes is one no test reads.
#
# The `pytest` hook is about 9 seconds of a commit's 10.5,
# and the global `post-commit` hook runs it again on every commit
# a rebase or cherry-pick makes, docs-only ones included.
# A commit that changes only files no test reads can't change what the tests do,
# given its parent passed, so it skips them.
#
# A script rather than an `exclude:` on the hook, because `pre-commit`
# leaves deleted files out of what it passes a hook,
# so a commit that only deletes a module would skip the tests that import it.

set -euo pipefail

# Every file no test reads, checked with `rg` against `tests/` and `eta_publish/`:
# each one appears there only in a comment, docstring, or help text.
unread() {
    case "$1" in
        docs/* | .github/* | scripts/check-commit-message.sh) return 0 ;;
        README.md | LICENSE | discrepancies.md | .markdownlint-cli2.jsonc) return 0 ;;
        *) return 1 ;;
    esac
}

# What the commit changes, deletions and both sides of a rename included.
# `pre-commit run --from-ref` (as the `post-commit` hook runs it) sets these;
# a plain `git commit` commits the index.
if [[ -n ${PRE_COMMIT_FROM_REF:-} && -n ${PRE_COMMIT_TO_REF:-} ]]; then
    mapfile -d '' changed < <(
        git diff --name-only --no-renames -z "$PRE_COMMIT_FROM_REF" "$PRE_COMMIT_TO_REF"
    )
else
    mapfile -d '' changed < <(git diff --cached --name-only --no-renames -z)
fi

# Nothing changed at all, as for `pre-commit run --all-files` with nothing staged,
# says nothing about what can be skipped, so the tests run.
skip=$((${#changed[@]} > 0))
for path in "${changed[@]}"; do
    if ! unread "$path"; then
        skip=0
        break
    fi
done

if ((skip)); then
    echo "skipped: no test reads any of the ${#changed[@]} changed files"
    exit 0
fi
exec uv run pytest "$@"
