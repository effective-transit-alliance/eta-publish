#!/usr/bin/env bash
#
# Run `pytest`, unless every file the commit changes is one no test reads,
# or the tests already passed on its tree.
#
# The `pytest` hook is most of a commit's time,
# and the global `post-commit` hook runs it again on every commit
# a rebase or cherry-pick makes, docs-only ones included.
# A commit that changes only files no test reads can't change what the tests do,
# given its parent passed, so it skips them.
#
# A script rather than an `exclude:` on the hook, because `pre-commit`
# leaves deleted files out of what it passes a hook,
# so a commit that only deletes a module would skip the tests that import it.
#
# It also skips a tree the tests already passed on in this checkout,
# like each commit of a stack rebased onto `main` after its first commit is merged there,
# which gets the same tree it had before.
# The tree includes everything the tests run with that's pinned
# (`uv.lock`, `bun.lock`, `.python-version`, `mise.toml`),
# but not the gitignored images under `site/`,
# whose presence decides whether the offline build in `tests/conftest.py` draws images:
# a tree that passed without them is still skipped once they're downloaded.

set -euo pipefail

# The trees the full suite passed on, one per line, newest last.
# In the common git dir, so shared by every worktree of this checkout.
passed="$(git rev-parse --git-common-dir)/pytest-passed-trees"

# Every file no test reads, checked with `rg` against `tests/` and `eta_publish/`:
# each one appears there only in a comment, docstring, or help text.
unread() {
    case "$1" in
        docs/* | .github/*) return 0 ;;
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
    tree="$(git rev-parse "$PRE_COMMIT_TO_REF^{tree}")"
else
    mapfile -d '' changed < <(git diff --cached --name-only --no-renames -z)
    # `pre-commit` stashes unstaged changes first, so the tests see the index.
    tree="$(git write-tree)"
fi

if grep -qxF -- "$tree" "$passed" 2>/dev/null; then
    echo "skipped: the tests already passed on this tree"
    exit 0
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
# On 4 workers: in a checkout with the pictures, the suite takes about 8 seconds rather than 14.5.
# More are slower, since each worker makes the offline build in `tests/conftest.py` again.
uv run pytest -n 4 "$@"

# Only a run of the whole suite, as the hook runs it, says the tree passed.
if (($# == 0)); then
    echo "$tree" >>"$passed"
    # Keeps the newest 1000, trimmed only once there are 2000, so not on every commit.
    if (($(wc -l <"$passed") >= 2000)); then
        tail -n 1000 "$passed" >"$passed.tmp"
        mv "$passed.tmp" "$passed"
    fi
fi
