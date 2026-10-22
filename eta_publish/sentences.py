"""Break prose into lines at sentence boundaries.

The Markdown archive is committed to git, so line breaks decide what a diff looks like.
Wrapped to a fixed width, a paragraph is one long line
and correcting a single word reports the whole paragraph as changed.
Broken at sentences,
the August 21 addendum to the SAS West report is a three-line diff.

The rule is narrow because it has to be *stable* more than clever.
Publication prose is full of `125 St.`, `Phase 2.`, `$7.7 billion.`, and `Nov. 2026`,
and a splitter that changes its mind between runs churns every file it touches.

Where a case is genuinely ambiguous, it does not break.
`...runs under 125 St. It would cost...`
is indistinguishable from `...the 125 St. station...`
without understanding the sentence.
Not breaking merges two sentences onto one line, a slightly coarser diff;
breaking wrongly splits a sentence in half and churns on every regeneration.
The coarser diff is the better failure.

Changing anything here reflows every archived publication,
so it should be its own commit, reviewed as a reflow rather than as content.
"""

import re

# Words that end in a period without ending a sentence.
# Explicit and short: a general abbreviation detector is the kind of cleverness
# that makes the output unstable.
ABBREVIATIONS = frozenset(
    {
        # Streets and places, which these publications are largely about.
        "st",
        "ave",
        "av",
        "blvd",
        "rd",
        "ft",
        "mi",
        "approx",
        # Titles.
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sen",
        "rep",
        "gov",
        # Organizations and references.
        "inc",
        "co",
        "corp",
        "dept",
        "est",
        "fig",
        "no",
        "vol",
        "pp",
        "ch",
        "sec",
        # Latin.
        "e.g",
        "i.e",
        "cf",
        "etc",
        "vs",
        "al",
        # Months.
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sept",
        "sep",
        "oct",
        "nov",
        "dec",
    }
)

# The token immediately before a candidate break.
LAST_WORD = re.compile(r"([\w.]+)\.$")


def _is_abbreviation(before: str) -> bool:
    match = LAST_WORD.search(before)
    if match is None:
        return False
    word = match.group(1).lower().rstrip(".")
    if word in ABBREVIATIONS:
        return True
    # A single initial (`J. Smith`), or a dotted initialism (`U.S.`).
    # Letters only: `Phase 2.` ends a sentence,
    # and treating the digit as an initial would glue the next one onto it.
    return bool(re.fullmatch(r"[a-z]", word)) or bool(re.fullmatch(r"(?:[a-z]\.)+[a-z]", word))


# A sentence ends at `.`, `!`, or `?`, optionally closed by a quote or bracket,
# followed by a space and something that can start a sentence.
BOUNDARY = re.compile(
    r"""
    (?<=[.!?])            # the terminator
    (?P<close>["'”’)\]]*)   # any closing quote or bracket
    [ ]                   # exactly one space; newlines are already breaks
    (?=["'“‘(\[]*[A-Z0-9])  # next sentence starts here
    """,
    re.VERBOSE,
)


def split(text: str) -> list[str]:
    """Split one paragraph into sentences, preserving the text exactly.

    Joining the result with a single space reproduces the input,
    so nothing can be lost or gained by reflowing.
    """
    if not text:
        return []

    sentences: list[str] = []
    start = 0
    for match in BOUNDARY.finditer(text):
        end = match.end("close")
        if _is_abbreviation(text[start:end]):
            continue
        sentences.append(text[start:end])
        start = match.end()
    sentences.append(text[start:])
    return [s for s in sentences if s]
