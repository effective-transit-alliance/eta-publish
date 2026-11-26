"""Where in the document each finding of `style.py` is, and what would fix it.

The document is built here as the parser would leave it, each run with the place
Docs gave it, so a mark can be compared with the exact units of the document.
Each is one unit per UTF-16 code unit of text, as Docs counts,
and one unit for a line break, a footnote reference, or a smart chip.
"""

from eta_publish.nodes import (
    Category,
    Document,
    Footnote,
    FootnoteRef,
    HeaderLine,
    Inline,
    LineBreak,
    Location,
    Notice,
    Paragraph,
    Replace,
    Text,
    utf16_length,
)
from eta_publish.style import _edits, style

TAB = "t.0"


class Chip:
    """A smart chip: one unit of the document, showing a name that is longer."""

    def __init__(self, name: str) -> None:
        self.name = name


type Part = str | Chip | LineBreak | FootnoteRef


def inlines(*parts: Part, at: int = 1, segment: str | None = None) -> list[Inline]:
    """What the parser makes of `parts`, each with the place it has from `at`."""
    content: list[Inline] = []
    for part in parts:
        match part:
            case str():
                width = utf16_length(part)
                where = Location(TAB, segment, at, at + width)
                content.append(Text(text=part, location=where))
            case Chip():
                width = 1
                where = Location(TAB, segment, at, at + 1)
                content.append(Text(text=part.name, location=where))
            case _:
                width = 1
                content.append(part)
        at += width
    return content


def found(*parts: Part) -> list[Notice]:
    """The style warnings for a document of one paragraph, which starts at unit 1."""
    doc = Document(blocks=[Paragraph(content=inlines(*parts))])
    style(doc)
    return doc.warnings


def only(*parts: Part, check: str = "") -> tuple[Notice, Location, tuple[Replace, ...]]:
    """The one warning, its one mark's place, and its fix.

    Of `check`'s where a run says more than one thing is wrong with it."""
    (notice,) = [n for n in found(*parts) if not check or n.check == check]
    (mark,) = notice.marks
    assert all(isinstance(edit, Replace) for edit in mark.fix)
    return notice, mark.location, tuple(e for e in mark.fix if isinstance(e, Replace))


def at(start: int, end: int, segment: str | None = None) -> Location:
    return Location(TAB, segment, start, end)


# ---- one for each check --------------------------------------------


def test_a_gap_after_a_sentence_has_its_extra_space_marked_and_struck_out() -> None:
    notice, where, fix = only("It is deep.  It is dear.")
    # `It is deep.` is 11 units from 1, so the two spaces are 12 to 14,
    # and the first of them is the one space there should be.
    assert where == at(13, 14)
    assert fix == (Replace(at(13, 14), ""),)
    # What it is about is the words either side, whatever the number of spaces.
    assert notice.keys == ("extra-space-after-sentence: deep. It",)


def test_a_gap_between_words_has_its_extra_spaces_marked_and_struck_out() -> None:
    notice, where, fix = only("The demand   requires frequency.")
    assert where == at(12, 14)
    assert fix == (Replace(at(12, 14), ""),)
    assert notice.keys == ("extra-space-between-words: demand requires",)


def test_a_spaced_dash_has_each_of_its_spaces_struck_out_and_keeps_the_dash() -> None:
    notice, where, fix = only("A cost — a lot.")
    # One edit for the space before it and one for the space after:
    # the mark runs from the first to the last, over the dash between them.
    assert where == at(7, 10)
    assert fix == (Replace(at(7, 8), ""), Replace(at(9, 10), ""))
    assert notice.keys == ("spaced-dash: cost — a",)


def test_a_dash_spaced_on_one_side_is_closed_up_too() -> None:
    _, where, fix = only("A cost –a lot.")
    # The space before the dash, which is all of it that changes.
    assert where == at(7, 8)
    assert fix == (Replace(at(7, 8), ""),)


def test_a_hyphen_in_a_range_is_marked_alone_and_made_an_en_dash() -> None:
    notice, where, fix = only("About 10-15 trains.")
    assert where == at(9, 10)
    assert fix == (Replace(at(9, 10), "–"),)
    # The range is what it is about, which is more than the hyphen says.
    assert notice.keys == ("hyphen-in-range: 10-15",)


def test_a_straight_apostrophe_is_marked_alone_and_curled() -> None:
    notice, where, fix = only("The rider's fare.")
    assert where == at(10, 11)
    assert fix == (Replace(at(10, 11), "’"),)
    assert notice.keys == ("straight-apostrophe: rider's",)


def test_an_article_before_the_initials_is_struck_out_and_the_initials_stay() -> None:
    notice, where, fix = only("So the ETA said so.")
    assert where == at(4, 8)
    assert fix == (Replace(at(4, 8), ""),)
    assert notice.keys == ("eta-with-article: the ETA",)


def test_the_article_opening_a_sentence_is_struck_out_the_same() -> None:
    _, where, fix = only("The ETA said so.")
    assert where == at(1, 5)
    assert fix == (Replace(at(1, 5), ""),)


def test_a_numbered_street_is_marked_and_written_as_the_mta_writes_it() -> None:
    notice, where, fix = only("At 125th Street today.")
    # `125` is the number as it was: `th` goes, and `Street` becomes `St`.
    assert where == at(7, 16)
    assert fix == (Replace(at(7, 9), ""), Replace(at(10, 16), "St"))
    assert notice.keys == ("station-or-street-name: 125th Street",)


def test_the_line_is_marked_and_written_as_it_is_named() -> None:
    notice, where, fix = only("It uses the Second Ave subway.")
    assert where == at(20, 30)
    assert fix == (Replace(at(20, 23), "Avenue"), Replace(at(24, 30), "Subway"))
    assert notice.keys == ("station-or-street-name: Second Ave subway",)


def test_a_street_named_in_words_is_only_commented_on() -> None:
    """It may be another agency's station, whose own name is spelled out:
    the rule knows how the MTA writes a street, and not whose this is."""
    notice, where, fix = only("Stops at Newark Broad Street.")
    assert where == at(10, 29)
    assert fix == ()
    assert notice.keys == ("station-or-street-name: Newark Broad Street",)
    assert notice.categories == {Category.COMMENT}


def test_a_street_spaced_oddly_is_only_commented_on() -> None:
    """The name is read from words, so the text under it may not be what it read."""
    _, where, fix = only("At 125th  Street today.", check="station-or-street-name")
    assert where == at(4, 17)
    assert fix == ()


def test_a_unit_spelled_out_is_marked_and_made_the_symbol() -> None:
    notice, where, fix = only("It is 137 feet long.")
    # The number stays as the document set it, and only the unit is replaced.
    assert where == at(11, 15)
    assert fix == (Replace(at(11, 15), "ft"),)
    assert notice.keys == ("unit-not-abbreviated: 137 feet",)


def test_a_hyphenated_unit_is_marked_and_made_the_measurement() -> None:
    notice, where, fix = only("A 600-foot train.")
    assert where == at(6, 11)
    assert fix == (Replace(at(6, 11), " ft"),)
    assert notice.keys == ("hyphenated-unit: 600-foot",)


def test_a_hyphenated_time_keeps_its_word_in_the_fix() -> None:
    _, where, fix = only("A 6-minute wait.")
    assert where == at(4, 5)
    assert fix == (Replace(at(4, 5), " "),)


def test_a_percentage_is_marked_and_made_the_symbol() -> None:
    notice, where, fix = only("About 92 percent ride.")
    assert where == at(9, 17)
    assert fix == (Replace(at(9, 17), "%"),)
    assert notice.keys == ("symbol-spelled-out: 92 percent",)


def test_a_sum_is_marked_and_made_the_amount_with_its_scale() -> None:
    notice, where, fix = only("It costs 7.7 billion dollars.")
    # The `$` is put in before the number, which is not touched, and ` dollars` goes.
    assert where == at(10, 29)
    assert fix == (Replace(at(10, 10), "$"), Replace(at(21, 29), ""))
    assert notice.keys == ("symbol-spelled-out: 7.7 billion dollars",)


# ---- only what changes -----------------------------------------------


def test_what_is_in_common_is_left_out_of_what_is_replaced() -> None:
    assert _edits("137 feet", "137 ft") == [(4, 8, "ft")]
    assert _edits("125th Street", "125 St") == [(3, 5, ""), (6, 12, "St")]
    assert _edits("the ", "") == [(0, 4, "")]
    assert _edits("Second Ave subway", "Second Avenue Subway") == [
        (7, 10, "Avenue"),
        (11, 17, "Subway"),
    ]
    assert _edits("a", "a") == []


def test_what_is_between_two_changes_is_not_replaced() -> None:
    assert _edits(" \u2013 ", "\u2013") == [(0, 1, ""), (2, 3, "")]
    # Something put in at the front is an empty stretch, an insertion.
    assert _edits("7.7 billion dollars", "$7.7 billion") == [(0, 0, "$"), (11, 19, "")]


def test_a_word_is_in_common_whole_or_not_at_all() -> None:
    """`feet` and `ft` both end in `t`, and neither is half of the other."""
    assert _edits("feet", "ft") == [(0, 4, "ft")]
    assert _edits("6-minute", "6 minute") == [(1, 2, " ")]


# ---- where the text is -----------------------------------------------


def test_a_run_after_an_emoji_is_marked_in_the_units_docs_counts() -> None:
    """The emoji is two units in Docs and one character here."""
    _, where, _ = only("\U0001f687 The rider's fare.")
    assert where == at(13, 14)


def test_a_finding_in_a_footnote_is_in_its_segment() -> None:
    doc = Document()
    run = inlines("The rider's fare.", at=0, segment="kix.fn")
    doc.footnotes = [Footnote(footnote_id="kix.fn", number=1, content=[Paragraph(content=run)])]
    style(doc)
    (mark,) = doc.warnings[0].marks
    assert mark.location == at(9, 10, "kix.fn")


def test_a_finding_in_the_subtitle_is_marked_there() -> None:
    doc = Document(subtitle=inlines("The rider's fare."))
    style(doc)
    (mark,) = doc.warnings[0].marks
    assert mark.location == at(10, 11)


def _header(*lines: list[Inline]) -> Document:
    doc = Document()
    doc.meta = {"Short": "what `meta` holds, which the lines are read instead of"}
    doc.header_lines = {"Short": HeaderLine(lines=tuple(tuple(line) for line in lines))}
    return doc


def test_a_header_value_is_marked_on_the_line_it_was_written_on() -> None:
    key = Text(text="Short", underline=True, location=at(8, 13))
    value = Text(text=":  The rider's fare.", location=at(13, 33))
    doc = _header([key, value])
    style(doc)
    (mark,) = doc.warnings[0].marks
    # `:  The rider` is 12 characters, so the apostrophe is at 13 + 12.
    assert mark.location == at(25, 26)
    assert mark.fix == (Replace(at(25, 26), "’"),)


def test_a_wrapped_header_value_is_marked_on_its_second_line() -> None:
    key = Text(text="Short", underline=True, location=at(8, 13))
    first = Text(text=": Cheaper.", location=at(13, 23))
    second = Text(text="  The rider's fare.", location=at(24, 43))
    doc = _header([key, first], [second])
    style(doc)
    (mark,) = doc.warnings[0].marks
    assert mark.location == at(24 + 11, 24 + 12)


def test_nothing_is_marked_where_the_document_has_no_places() -> None:
    doc = Document(blocks=[Paragraph(content=[Text(text="The rider's fare.")])])
    style(doc)
    assert len(doc.warnings) == 1
    assert doc.warnings[0].marks == ()


# ---- what a fix must not delete ---------------------------------------


def _chip() -> list[Part]:
    return ["It is 5 ", Chip("feet"), " long."]


def _break() -> list[Part]:
    return ["It is 5 fe", LineBreak(), "et long."]


def _footnote() -> list[Part]:
    return ["It is 5 fe", FootnoteRef(footnote_id="kix.fn", number=1), "et long."]


def test_a_finding_across_a_chip_is_only_commented_on() -> None:
    """The chip shows `feet` and is one unit: replacing the range would delete it
    whatever the replacement says, so it is the chip that is commented on."""
    notice, where, fix = only(*_chip())
    assert where == at(7, 10)
    assert fix == ()
    assert notice.categories == {Category.COMMENT}
    assert notice.keys == ("unit-not-abbreviated: 5 feet",)


def test_a_finding_across_a_shift_enter_is_only_commented_on() -> None:
    """`plain_text` leaves the break out, so the text reads `5 feet` and the
    document has the break inside the `feet` to be replaced: a replacement would
    delete it, so the whole of `5 feet` is commented on instead."""
    notice, where, fix = only(*_break())
    assert where == at(7, 14)
    assert fix == ()
    assert notice.categories == {Category.COMMENT}


def test_a_finding_across_a_footnote_reference_is_only_commented_on() -> None:
    _, where, fix = only(*_footnote())
    assert where == at(7, 14)
    assert fix == ()


def test_a_dash_spaced_across_a_shift_enter_has_each_space_struck_out_either_side_of_it() -> None:
    """The break is between the first space and the dash, and is left where it is."""
    _, where, fix = only("A cost ", LineBreak(), "— a lot.")
    assert where == at(7, 11)
    assert fix == (Replace(at(7, 8), ""), Replace(at(10, 11), ""))


def test_an_insertion_is_a_point_after_a_shift_enter_where_the_number_starts() -> None:
    """Not at the end of the run before the break: the finding starts after it."""
    _, where, fix = only("It costs ", LineBreak(), "7.7 billion dollars.")
    assert where == at(11, 30)
    assert fix == (Replace(at(11, 11), "$"), Replace(at(22, 30), ""))
    assert fix[0].location.empty


def test_an_insertion_beside_a_chip_is_only_commented_on() -> None:
    """The point would be at the chip, which is one unit and not the text it shows."""
    notice, where, fix = only("It costs ", Chip("7.7"), " billion dollars.")
    assert where == at(10, 27)
    assert fix == ()
    assert notice.categories == {Category.COMMENT}


def test_a_shift_enter_beside_what_is_replaced_is_no_reason_to_withhold_it() -> None:
    """The break is in the words the finding and its fix share, which stay as they are."""
    _, where, fix = only("It is 5 ", LineBreak(), "feet long.")
    assert where == at(10, 14)
    assert fix == (Replace(at(10, 14), "ft"),)


def test_a_gap_across_a_shift_enter_has_only_the_space_after_it_struck_out() -> None:
    _, where, fix = only("It is deep. ", LineBreak(), " It is dear.")
    assert where == at(14, 15)
    assert fix == (Replace(at(14, 15), ""),)


def test_a_finding_after_a_shift_enter_is_still_fixed() -> None:
    _, where, fix = only("It is deep.", LineBreak(), "The rider's fare.")
    assert where == at(22, 23)
    assert fix == (Replace(at(22, 23), "’"),)


def test_a_finding_before_a_chip_is_still_fixed() -> None:
    _, where, fix = only("The rider's fare, ", Chip("Alon Levy"))
    assert where == at(10, 11)
    assert fix == (Replace(at(10, 11), "’"),)


def test_a_finding_inside_a_chip_is_the_whole_chip_and_only_commented_on() -> None:
    _, where, fix = only("By ", Chip("Alon  Levy"), ".")
    assert where == at(4, 5)
    assert fix == ()


# ---- the keys ------------------------------------------------------------


def test_a_key_does_not_depend_on_how_many_spaces_there_are() -> None:
    keys = [only("It is deep." + " " * n + "It is dear.")[0].keys for n in (2, 3, 5)]
    assert keys[0] == keys[1] == keys[2]


def test_the_same_run_gives_the_same_keys_every_time() -> None:
    content = ["It's deep.  It's about 10-15 feet, the ETA says — at 125th Street."]
    first = [n.keys for n in found(*content)]
    second = [n.keys for n in found(*content)]
    assert first == second
    assert [key for keys in first for key in keys] == [
        "extra-space-after-sentence: deep. It's",
        "spaced-dash: says \u2014 at",
        "hyphen-in-range: 10-15",
        "straight-apostrophe: It's",
        "straight-apostrophe: It's",
        "eta-with-article: the ETA",
        "station-or-street-name: 125th Street",
        "unit-not-abbreviated: 15 feet",
    ]


def test_two_findings_of_one_text_have_the_same_key_for_the_order_to_pair() -> None:
    first, second = found("A 6-minute wait, then a 6-minute ride.")
    assert first.keys == second.keys == ("hyphenated-unit: 6-minute",)
    assert first.marks[0].location != second.marks[0].location


def test_a_long_subject_is_clipped_like_a_quoted_line() -> None:
    long = "x" * 80
    (notice,) = found(f"A cost — {long} more.")
    assert notice.marks[0].subject == "cost —..."
