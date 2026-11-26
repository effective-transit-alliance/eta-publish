#!/usr/bin/env bash
#
# Check a commit message against the attribution style `CLAUDE.md` asks for.
#
# `Co-Authored-By:` is the mistake that keeps happening:
# the wrong casing still reads as right at a glance,
# so the spelling is checked mechanically rather than left to review.
#
# Only the mechanical rules are checked.
# Semantic line breaks and backticking file names are judgement calls,
# and a hook would reject correct messages.
#
# A commit a human wrote alone needs no attribution at all,
# and there is no way to tell who wrote a message from the message.
# `CLAUDECODE` is the closest thing to a signal:
# `claude` sets it in the environment it runs commands in,
# so it is set for a commit `claude` makes and unset for one typed in a terminal.
# It only gates whether the trailer is required;
# a trailer that is there is checked either way.

set -euo pipefail

readonly correct="Co-authored-by: Claude <model name> <noreply@anthropic.com>"
readonly example="Co-authored-by: Claude Opus 5 <noreply@anthropic.com>"

# GitHub renders this as an annotation on the run;
# a terminal renders it as what it says.
fail() {
    if [[ -n ${GITHUB_ACTIONS:-} ]]; then
        echo "::error::$1" >&2
    else
        echo "$1" >&2
    fi
    exit 1
}

readonly message_file="${1:?usage: check-commit-message.sh <commit message file>}"

# `git` strips comment lines and everything past the `--verbose` scissors line
# before it stores the message, so the check sees the same text the commit will.
# `git commit -F` keeps `#` lines, so a body line that starts with one
# escapes these checks; that is a gap, not a loophole worth building around.
message="$(sed -e '/^# *-\{1,\} >8 -\{1,\}/,$d' -e '/^#/d' "$message_file")"
readonly message

if [[ $message == *—* ]]; then
    fail "the commit message contains an em dash; \
use a colon, comma, semicolon, or a second sentence instead"
fi

if grep -qiE '^[[:space:]]*Claude-Session:' <<<"$message"; then
    fail "the commit message has a \`Claude-Session:\` line; delete it"
fi

# The trailer block is the last paragraph,
# so a `Co-authored-by:` line anywhere above it is not a trailer at all.
trailers="$(awk 'BEGIN { RS = "" } { last = $0 } END { print last }' <<<"$message")"
readonly trailers

readonly loose_key='^[[:space:]]*Co[-_ ]?authored[-_ ]?by[[:space:]]*:'

if grep -qiE "$loose_key" <<<"$message" && ! grep -qiE "$loose_key" <<<"$trailers"; then
    fail "the \`Co-authored-by:\` line is not in the trailer block; \
put it in the last paragraph of the message, as
    $example"
fi

# `git merge`, `git revert` and `git commit --fixup`/`--squash` write these subjects
# themselves, and `--autosquash` matches on the subject exactly,
# so there is nothing to attribute and nothing safe to rewrite.
generated_subject() {
    case $message in
        "Merge branch "* | "Merge remote-tracking branch "* | "Merge tag "* | \
            "Merge commit "* | "Merge pull request "* | 'Revert "'* | \
            "fixup! "* | "squash! "*) return 0 ;;
        *) return 1 ;;
    esac
}

# Only Claude's own trailer is this script's business:
# a human co-author is a normal `Co-authored-by:` line and is left alone.
claude_trailers="$(grep -iE "${loose_key}[[:space:]]*Claude([[:space:]]|<|\$)" <<<"$trailers" || true)"
readonly claude_trailers

if [[ -z $claude_trailers ]]; then
    if [[ -n ${CLAUDECODE:-} ]] && ! generated_subject; then
        fail "the commit message has no \`Co-authored-by:\` trailer for Claude; \
end the message with
    $example"
    fi
    exit 0
fi

# One trailer per model that worked on the commit, so a model named twice is a slip.
duplicate="$(sort <<<"$claude_trailers" | uniq -d | head -n 1)"
readonly duplicate
if [[ -n $duplicate ]]; then
    fail "the commit message names \`$duplicate\` more than once; \
keep one trailer per model"
fi

while IFS= read -r trailer; do
    if ! [[ $trailer =~ ^Co-authored-by:\ Claude\ [^\<]*[^[:space:]]\ \<noreply@anthropic\.com\>$ ]]; then
        if ! [[ $trailer == "Co-authored-by: "* ]]; then
            fail "the \`Co-authored-by:\` key is misspelled in \`$trailer\`; \
\`authored\` and \`by\` are lowercase, and one space follows the colon:
    $example"
        fi
        fail "\`$trailer\` is not the expected trailer; it has to read
    $correct
for example
    $example"
    fi
done <<<"$claude_trailers"
