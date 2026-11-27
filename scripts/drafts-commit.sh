#!/usr/bin/env bash
#
# The drafts commit for each `eta-publish` commit (see `docs/drafts.md`):
# a commit in `drafts/`, the clone of `eta-drafts`,
# that pins the code commit and rebuilds every draft with it from the saved documents.
#
#   scripts/drafts-commit.sh check           build the drafts with the code being committed
#   scripts/drafts-commit.sh head            make the drafts commit for the commit just made, `HEAD`
#   scripts/drafts-commit.sh missing BRANCH  put `drafts/` on BRANCH, and list the code commits
#                                            from `HEAD`'s history it has no drafts commit for
#   scripts/drafts-commit.sh commit          make the drafts commit for `HEAD`, as it is checked out
#
# `check` is the `pre-commit` hook, and `head` is run by hand to make the drafts commit locally;
# `missing` and `commit` are what `eta-drafts`'s sync workflow runs.
# Each runs from the top of an `eta-publish` checkout, with `eta-drafts` cloned in it as `drafts/`.

set -euo pipefail

drafts=drafts
# Where a drafts commit records the code commit it pins: a submodule that's never checked out.
pin_path=eta-publish
# The trailer that marks a drafts commit as made here, naming the code commit it rebuilds with,
# so a branch can tell the commits it may remake from the ones someone wrote, like a pull.
trailer=eta-publish-commit

# GitHub renders this as an annotation on the run;
# a terminal renders it as what it says.
fail() {
    if [[ -n ${GITHUB_ACTIONS:-} ]]; then
        echo "::error::$1" >&2
    else
        echo "drafts: $1" >&2
    fi
    exit 1
}

say() {
    echo "drafts: $*" >&2
}

# A hook runs with `$GIT_DIR`, `$GIT_INDEX_FILE` and the like naming `eta-publish`'s repository,
# which would make every `git -C drafts` act on `eta-publish` instead.
# Nothing here needs them: it runs from the top of the checkout, as hooks do.
while read -r variable; do
    unset "$variable"
done < <(git rev-parse --local-env-vars)

dgit() {
    git -C "$drafts" "$@"
}

# The code commit the drafts commit `$1` pins, or nothing if it pins none.
pin_of() {
    dgit rev-parse --quiet --verify "$1:$pin_path" || true
}

# Whether the drafts commit `$1` was made here, rather than by hand.
made_here() {
    [[ -n "$(dgit log -1 --format="%(trailers:key=$trailer,valueonly)" "$1")" ]]
}

# Whether the code commit `$1` is `$2` or one of its ancestors.
# A pin this checkout doesn't have is neither.
in_history() {
    git merge-base --is-ancestor "$1" "$2" 2>/dev/null
}

# The newest drafts commit whose pin is in the history of the code commit `$2`,
# on the drafts branch `$1` if there is one, or else on `main`, locally or on `origin`:
# where the drafts commits for `$2`'s history continue from.
base_for() {
    local branch="$1"
    local target="$2"
    local ref
    local commit
    local pin
    for ref in "refs/heads/$branch" "refs/remotes/origin/$branch" refs/heads/main refs/remotes/origin/main; do
        if ! dgit rev-parse --quiet --verify "$ref" >/dev/null; then
            continue
        fi
        while read -r commit; do
            pin="$(pin_of "$commit")"
            # Older commits than the first pin have none either.
            if [[ -z $pin ]]; then
                break
            fi
            if in_history "$pin" "$target"; then
                echo "$commit"
                return 0
            fi
        done < <(dgit rev-list --first-parent "$ref")
    done
    return 1
}

# Puts `drafts/` on its branch `$1`, at the drafts commit the commits for the code commit `$2` go on.
#
# That's the branch's last commit, unless its pin isn't in `$2`'s history,
# as after an amend, a rebase, or a force-push of the code branch.
# Then the branch is moved back to the newest commit whose pin is,
# and the drafts commits after it are made again for the rewritten code commits,
# the way the code branch itself was rewritten.
# Only drafts commits made here are dropped that way, which can all be made again,
# and never one already on `origin`'s `main`, which is never rewritten.
prepare() {
    local branch="$1"
    local target="$2"
    local base
    local tip=
    local ref
    local dropped
    local commit
    if [[ -n "$(dgit status --porcelain --untracked-files=no)" ]]; then
        fail "\`$drafts/\` has uncommitted changes, so it can't be moved to the branch \`$branch\`"
    fi
    if ! base="$(base_for "$branch" "$target")"; then
        fail "no drafts commit on \`$branch\` or \`main\` pins a commit in the history of $target"
    fi
    for ref in "refs/heads/$branch" "refs/remotes/origin/$branch"; do
        if dgit rev-parse --quiet --verify "$ref" >/dev/null; then
            tip="$ref"
            break
        fi
    done
    if [[ -n $tip ]]; then
        mapfile -t dropped < <(dgit rev-list "$base..$tip")
        for commit in "${dropped[@]}"; do
            if ! made_here "$commit"; then
                fail "moving \`$branch\` back to $base would drop $(dgit log -1 --format='%h %s' "$commit"), \
which wasn't made by this script; rebase it onto $base by hand"
            fi
            if dgit rev-parse --quiet --verify refs/remotes/origin/main >/dev/null &&
                dgit merge-base --is-ancestor "$commit" refs/remotes/origin/main; then
                fail "moving \`$branch\` back to $base would drop $(dgit log -1 --format='%h %s' "$commit"), \
which is on \`origin/main\`"
            fi
        done
        if ((${#dropped[@]} > 0)); then
            say "moving \`$branch\` back to $(dgit log -1 --format='%h %s' "$base"), \
dropping ${#dropped[@]} drafts commits for code commits no longer in its history"
        fi
    fi
    if [[ "$(dgit symbolic-ref --quiet HEAD || true)" != "refs/heads/$branch" ||
        "$(dgit rev-parse HEAD)" != "$base" ]]; then
        dgit switch --quiet --no-track -C "$branch" "$base"
    fi
}

# The code commits in `HEAD`'s history with no drafts commit on `drafts/`'s branch, oldest first.
#
# Every pin on the branch counts, not just its last one:
# after a merge, the commits from each side of it are pinned one after the other,
# and neither side's pin has the other side in its history.
# Only pins in `HEAD`'s history count, as `base_for`'s do.
missing() {
    local commit
    local pin
    local pins=()
    while read -r commit; do
        pin="$(pin_of "$commit")"
        if [[ -n $pin ]] && in_history "$pin" HEAD; then
            pins+=("$pin")
        fi
    done < <(dgit rev-list HEAD)
    git rev-list --reverse --topo-order HEAD --not "${pins[@]}"
}

# The drafts, rebuilt from the saved documents with the code checked out, into `$1`
# (or into `drafts/site/` itself, with no `$1`).
#
# Offline and with no images, so the same commit builds the same files everywhere:
# the images aren't committed, nor is anything else a build fetches,
# and without them a build writes the same committed files (see `tests/conftest.py`).
build() {
    local into=()
    if (($# > 0)); then
        into=(--into "$1")
    fi
    # The fonts, downloaded first on a machine without them, as a fresh CI runner is,
    # since an offline build downloads nothing and fails without them.
    # Pinned by their checksums, so the build still writes the same files everywhere.
    # Only with code that has them, and so has the command,
    # as the branch's newest script also builds its older commits.
    if [[ -f eta_publish/fonts.py ]]; then
        uv run eta-publish fonts
    fi
    uv run eta-publish all "$drafts/publications.toml" -o "$drafts/site" "${into[@]}" --offline --no-images
}

# Rebuilds the drafts with the code checked out, and commits them in `drafts/` pinning `HEAD`.
commit() {
    local code
    local short
    local subject
    code="$(git rev-parse HEAD)"
    short="$(git rev-parse --short=7 HEAD)"
    subject="$(git log -1 --format=%s HEAD)"
    build
    dgit add --all -- site
    dgit update-index --add --cacheinfo "160000,$code,$pin_path"
    # Not `local`: the `trap` that removes it runs once the function has returned.
    # A `trap` rather than removing it after, since a failed commit exits first.
    message="$(mktemp)"
    trap 'rm -f "$message"' EXIT
    cat >"$message" <<EOF
\`eta-publish\` $short: $subject

The drafts, rebuilt from their saved documents
with https://github.com/effective-transit-alliance/eta-publish/commit/$code.

$trailer: $code
EOF
    dgit commit --quiet --no-verify -F "$message"
    say "committed $(dgit log -1 --format='%h %s' HEAD) on \`$(dgit branch --show-current)\`"
}

# The branch `HEAD` is on, or the one being rebased, which a rebase leaves `HEAD` off of.
current_branch() {
    local head_name
    local state
    if git symbolic-ref --quiet --short HEAD; then
        return 0
    fi
    for state in rebase-merge rebase-apply; do
        head_name="$(git rev-parse --git-path "$state/head-name")"
        if [[ -f $head_name ]]; then
            head_name="$(<"$head_name")"
            echo "${head_name#refs/heads/}"
            return 0
        fi
    done
    return 1
}

case "${1:-}" in
    check)
        # As in this repository's own CI, which has no `drafts/`.
        if ! [[ -d $drafts ]]; then
            exit 0
        fi
        # Beside `site/` rather than in `/tmp`, which is another filesystem:
        # the build hard-links what it reuses.
        work="$(mktemp -d .drafts-check-XXXXXX)"
        trap 'rm -rf "$work"' EXIT
        build "$work/site"
        ;;
    head)
        if ! [[ -d $drafts ]]; then
            exit 0
        fi
        if ! branch="$(current_branch)"; then
            say "\`HEAD\` is on no branch, so there's no drafts branch to commit to"
            exit 0
        fi
        # The working copy has to be the code just committed to build with it,
        # which it isn't with uncommitted changes, as after `git commit <path>`.
        if ! git diff --quiet HEAD; then
            say "the working copy isn't the code committed, so the drafts commit is left to CI, made on push"
            exit 0
        fi
        prepare "$branch" "$(git rev-parse HEAD)"
        mapfile -t behind < <(missing)
        if ((${#behind[@]} == 0)); then
            say "\`$branch\` in \`$drafts/\` already has the drafts commit for $(git rev-parse --short HEAD)"
            exit 0
        fi
        # Only `HEAD`'s code is checked out to build with,
        # so a gap of commits made where there's no `drafts/` is CI's to fill, in order.
        if ((${#behind[@]} > 1)); then
            say "\`$branch\` in \`$drafts/\` has no drafts commits for the ${#behind[@]} code commits up to this one, \
so they're left to CI, made on push"
            exit 0
        fi
        commit
        ;;
    missing)
        if (($# != 2)); then
            fail "usage: $0 missing BRANCH"
        fi
        prepare "$2" "$(git rev-parse HEAD)"
        missing
        ;;
    commit)
        commit
        ;;
    *)
        fail "usage: $0 check | head | missing BRANCH | commit"
        ;;
esac
