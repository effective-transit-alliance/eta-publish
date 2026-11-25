"""Where in the document each thing the parser reads sits, as Docs counts.

Docs counts in UTF-16 code units and Python in code points,
so every test here with an emoji in it is one the two would disagree on.
"""

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import (
    Category,
    Document,
    Figure,
    FootnoteRef,
    Heading,
    Inline,
    List,
    Location,
    Mark,
    Paragraph,
    Replace,
    Shown,
    Table,
    Text,
    locate,
    sliced,
    span,
    utf16_length,
)
from eta_publish.parse import after_label, parse

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


# ---- the parsed tree -----------------------------------------------


def _run(text: str, start: int, **style: object) -> JsonObject:
    return {
        "startIndex": start,
        "endIndex": start + utf16_length(text),
        "textRun": {"content": text, "textStyle": dict(style)},
    }


def _para(start: int, *runs: str, style: str = "NORMAL_TEXT") -> JsonObject:
    """A paragraph of plain runs, with the indices Docs would give them, from `start`."""
    elements: list[JsonObject] = []
    at = start
    for text in runs:
        elements.append(_run(text, at))
        at += utf16_length(text)
    return {
        "startIndex": start,
        "endIndex": at,
        "paragraph": {"paragraphStyle": {"namedStyleType": style}, "elements": elements},
    }


def _end(item: JsonObject) -> int:
    return int(item["endIndex"])


def _doc(*content: JsonObject, footnotes: JsonObject | None = None) -> JsonObject:
    return {
        "tabId": TAB,
        "title": "Test",
        "body": {"content": [{"endIndex": 1, "sectionBreak": {}}, *content]},
        "footnotes": footnotes or {},
    }


def _texts(content: list[Inline]) -> list[Text]:
    return [node for node in content if isinstance(node, Text)]


def test_a_run_after_an_emoji_starts_where_docs_says() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(_end(title), "Trains 🚇 ", "and TODO\n")
    doc = parse(_doc(title, body))
    assert doc.tab_id == TAB
    paragraph = doc.blocks[0]
    assert isinstance(paragraph, Paragraph)
    assert paragraph.location == Location(TAB, None, 10, 10 + utf16_length("Trains 🚇 and TODO\n"))
    first, second = _texts(paragraph.content)
    assert first.location == Location(TAB, None, 10, 20)
    # The newline that ends the paragraph is structure, and not in the run.
    assert second.location == Location(TAB, None, 20, 28)
    # `TODO`, code points 13 to 17 of the paragraph's text.
    assert locate(paragraph.content, 13, 17) == Location(TAB, None, 24, 28)
    # From the space before the emoji into the second run.
    assert locate(paragraph.content, 6, 11) == Location(TAB, None, 16, 22)


def test_each_line_of_a_soft_broken_run_is_where_it_was_typed() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(_end(title), "one 🚇\vtwo\n")
    doc = parse(_doc(title, body))
    paragraph = doc.blocks[0]
    assert isinstance(paragraph, Paragraph)
    one, two = _texts(paragraph.content)
    assert (one.text, one.location) == ("one 🚇", Location(TAB, None, 10, 16))
    # After the vertical tab, which is one unit of its own.
    assert (two.text, two.location) == ("two", Location(TAB, None, 17, 20))


def test_a_heading_and_a_list_item_carry_their_paragraphs() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    heading = _para(_end(title), "Section\n", style="HEADING_1")
    item = _para(_end(heading), "first\n")
    item["paragraph"]["bullet"] = {"listId": "l"}
    doc = parse(_doc(title, heading, item))
    section, listed = doc.blocks
    assert isinstance(section, Heading)
    assert isinstance(listed, List)
    assert section.location == Location(TAB, None, 10, 18)
    assert listed.items[0].location == Location(TAB, None, 18, 24)
    assert listed.location == listed.items[0].location


def test_a_person_chip_is_one_unit() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(_end(title), "By ")
    body["paragraph"]["elements"].append(
        {
            "startIndex": 13,
            "endIndex": 14,
            "person": {"personProperties": {"name": "Alon Levy"}},
        }
    )
    body["paragraph"]["elements"].append(_run(".\n", 14))
    body["endIndex"] = 16
    doc = parse(_doc(title, body))
    paragraph = doc.blocks[0]
    assert isinstance(paragraph, Paragraph)
    chip = _texts(paragraph.content)[1]
    assert (chip.text, chip.location) == ("Alon Levy", Location(TAB, None, 13, 14))
    assert locate(paragraph.content, 3, 7) == Location(TAB, None, 13, 14)


def test_a_footnote_is_its_own_segment_and_starts_at_zero() -> None:
    """Docs leaves out a zero, so the footnote's first run has an end and no start."""
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(_end(title), "Claim")
    body["paragraph"]["elements"].append(
        {"startIndex": 15, "endIndex": 16, "footnoteReference": {"footnoteId": "kix.fn"}}
    )
    body["paragraph"]["elements"].append(_run("\n", 16))
    body["endIndex"] = 17
    note = _para(0, " Source 🚇 here.\n")
    del note["startIndex"]
    del note["paragraph"]["elements"][0]["startIndex"]
    doc = parse(_doc(title, body, footnotes={"kix.fn": {"content": [note]}}))
    paragraph = doc.blocks[0]
    assert isinstance(paragraph, Paragraph)
    ref = paragraph.content[1]
    assert isinstance(ref, FootnoteRef)
    assert ref.location == Location(TAB, None, 15, 16)
    footnote = doc.footnotes[0]
    assert footnote.location == Location(TAB, "kix.fn", 0, 17)
    first = footnote.content[0]
    assert isinstance(first, Paragraph)
    assert first.location == Location(TAB, "kix.fn", 0, 17)
    (run,) = _texts(first.content)
    # The space after the marker is taken off, and the location with it.
    assert (run.text, run.location) == ("Source 🚇 here.", Location(TAB, "kix.fn", 1, 16))


def test_a_paragraph_in_a_table_cell_is_where_the_cell_puts_it() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    cell = _para(13, "cell 🚇\n")
    table = {
        "startIndex": 10,
        "endIndex": 22,
        "table": {
            "tableRows": [
                {
                    "startIndex": 11,
                    "endIndex": 21,
                    "tableCells": [{"startIndex": 12, "endIndex": 21, "content": [cell]}],
                }
            ]
        },
    }
    doc = parse(_doc(title, table))
    parsed = doc.blocks[0]
    assert isinstance(parsed, Table)
    assert parsed.location == Location(TAB, None, 10, 22)
    inside = parsed.rows[0][0][0]
    assert isinstance(inside, Paragraph)
    assert inside.location == Location(TAB, None, 13, 21)
    assert _texts(inside.content)[0].location == Location(TAB, None, 13, 20)


def test_an_image_is_one_unit_and_its_figure_is_its_paragraph() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    picture = {
        "startIndex": 10,
        "endIndex": 12,
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [
                {"startIndex": 10, "endIndex": 11, "inlineObjectElement": {"inlineObjectId": "i"}},
                _run("\n", 11),
            ],
        },
    }
    document = _doc(title, picture)
    properties: JsonObject = {}
    document["inlineObjects"] = {
        "i": {"inlineObjectProperties": {"embeddedObject": {"imageProperties": properties}}}
    }
    doc = parse(document)
    figure = doc.blocks[0]
    assert isinstance(figure, Figure)
    assert figure.location == Location(TAB, None, 10, 12)
    assert figure.image.location == Location(TAB, None, 10, 11)


def test_a_response_without_indices_has_no_locations() -> None:
    """As the tests' own hand-written responses mostly are."""
    doc = parse(
        {
            "title": "Test",
            "body": {
                "content": [
                    {"paragraph": {"elements": [{"textRun": {"content": "Words\n"}}]}},
                ]
            },
        }
    )
    paragraph = doc.blocks[0]
    assert isinstance(paragraph, Paragraph)
    assert paragraph.location is None
    assert _texts(paragraph.content)[0].location is None
    assert doc.tab_id == ""


def test_a_label_s_value_keeps_where_it_is() -> None:
    run = Text("Video: clip", location=Location(TAB, None, 5, 16))
    (rest,) = after_label([run])
    assert isinstance(rest, Text)
    assert (rest.text, rest.location) == (" clip", Location(TAB, None, 11, 16))
    assert sliced(run, 7).location == Location(TAB, None, 12, 16)


def test_locate_spans_runs_and_points_between_them() -> None:
    runs: list[Inline] = [
        Text("ab", location=Location(TAB, None, 1, 3)),
        Text("cd", location=Location(TAB, None, 3, 5)),
    ]
    assert locate(runs, 1, 3) == Location(TAB, None, 2, 4)
    assert locate(runs, 2, 2) == Location(TAB, None, 3, 3)
    assert locate(runs, 4, 4) == Location(TAB, None, 5, 5)
    assert locate(runs, 0, 5) is None
    assert span(runs) == Location(TAB, None, 1, 5)
    assert span([Text("x")]) is None


# ---- marks ---------------------------------------------------------


def test_what_a_warning_becomes_is_what_its_marks_say() -> None:
    doc = Document()
    here = Location(TAB, None, 3, 7)
    doc.warn("nowhere")
    doc.warn("somewhere {}", Shown("x"), marks=[here, None])
    doc.warn("fixable", marks=[Mark(here, fix=(Replace(here, ""),))])
    reported, commented, suggested = doc.warnings
    assert reported.marks == ()
    assert reported.categories == {Category.REPORT}
    assert commented.marks == (Mark(here),)
    assert commented.categories == {Category.COMMENT}
    assert str(commented) == "somewhere `x`"
    assert suggested.categories == {Category.SUGGESTION}
