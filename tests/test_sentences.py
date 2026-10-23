"""Sentence splitting, which decides what every archived diff looks like."""

import pytest

from eta_publish.sentences import split

CASES: list[tuple[str, list[str]]] = [
    ("", []),
    ("One sentence.", ["One sentence."]),
    ("First. Second.", ["First.", "Second."]),
    ("A question? An answer!", ["A question?", "An answer!"]),
    # The abbreviations these publications are actually full of.
    ("The 125 St. station is deep.", ["The 125 St. station is deep."]),
    ("Second Ave. runs north.", ["Second Ave. runs north."]),
    ("It is 100 ft. down. That is deep.", ["It is 100 ft. down.", "That is deep."]),
    ("See fig. 3 for detail.", ["See fig. 3 for detail."]),
    ("Costs rose in Nov. 2026 sharply.", ["Costs rose in Nov. 2026 sharply."]),
    ("Compare e.g. Paris and London.", ["Compare e.g. Paris and London."]),
    ("The U.S. spends more.", ["The U.S. spends more."]),
    ("Written by J. Smith today.", ["Written by J. Smith today."]),
    # A number ending a sentence is still a sentence end.
    ("It cost $7.7 billion. That is a lot.", ["It cost $7.7 billion.", "That is a lot."]),
    ("Phase 2. Then Phase 3.", ["Phase 2.", "Then Phase 3."]),
    # Quotes and brackets close before the break.
    ('He said "no." Then he left.', ['He said "no."', "Then he left."]),
    ("(See below.) The rest follows.", ["(See below.)", "The rest follows."]),
    # A lowercase continuation is not a new sentence.
    ("Ended. mid-word continues.", ["Ended. mid-word continues."]),
    # Genuinely ambiguous, and resolved by not breaking.
    # `125 St. It` reads as a sentence end; `125 St. station` does not,
    # and the two are indistinguishable here.
    # A merged line is a coarser diff;
    # a wrong break splits a sentence and churns on every run.
    (
        "It runs under 125 St. It would cost more.",
        ["It runs under 125 St. It would cost more."],
    ),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_split(text: str, expected: list[str]) -> None:
    assert split(text) == expected


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_splitting_never_changes_the_text(text: str, expected: list[str]) -> None:
    """Rejoining must reproduce the input, so a reflow cannot lose a word."""
    assert " ".join(split(text)) == text


def test_a_real_paragraph() -> None:
    text = (
        "On paper, the MTA's proposed extension should be a slam dunk. "
        "It is the right route, a logical extension under Harlem's main street. "
        "It would cost $7.7 billion, or 12 times what Paris achieves."
    )
    assert split(text) == [
        "On paper, the MTA's proposed extension should be a slam dunk.",
        "It is the right route, a logical extension under Harlem's main street.",
        "It would cost $7.7 billion, or 12 times what Paris achieves.",
    ]
