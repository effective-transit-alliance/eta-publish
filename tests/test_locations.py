"""Where in the document each thing the parser reads sits, as Docs counts.

Docs counts in UTF-16 code units and Python in code points,
so every test here with an emoji in it is one the two would disagree on.
"""

from eta_publish.nodes import Location, utf16_length

TAB = "t.0"


def test_a_character_past_the_basic_plane_is_two_units() -> None:
    assert utf16_length("abc") == 3
    assert utf16_length("é") == 1
    assert utf16_length("🚇") == 2
    assert utf16_length("a🚇b🚉") == 6
    assert utf16_length("") == 0


def test_a_part_of_a_run_counts_the_units_before_it() -> None:
    run = Location(TAB, None, 10, 10 + utf16_length("a🚇 TODO"))
    assert run.part("a🚇 TODO", 3, 7) == Location(TAB, None, 14, 18)
    assert run.part("a🚇 TODO", 1, 2) == Location(TAB, None, 11, 13)


def test_an_empty_part_is_a_point() -> None:
    run = Location(TAB, "kix.fn", 0, 5)
    point = run.part("hello", 2, 2)
    assert point == Location(TAB, "kix.fn", 2, 2)
    assert point.empty
    assert not run.empty


def test_any_part_of_a_chip_is_the_whole_chip() -> None:
    """A person chip is one unit of the document, however long the name it shows."""
    chip = Location(TAB, None, 40, 41)
    assert chip.part("Alon Levy", 0, 4) == chip


def test_through_runs_from_one_start_to_another_end() -> None:
    first = Location(TAB, None, 3, 8)
    last = Location(TAB, None, 12, 20)
    assert first.through(last) == Location(TAB, None, 3, 20)
