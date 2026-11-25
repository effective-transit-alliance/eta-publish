"""Where in the document each thing the parser reads sits, as Docs counts.

Docs counts in UTF-16 code units and Python in code points,
so every test here with an emoji in it is one the two would disagree on.
"""

from eta_publish.checks import check
from eta_publish.docs_json import JsonObject
from eta_publish.embeds import check_embeds
from eta_publish.nodes import (
    Card,
    Category,
    Document,
    Figure,
    FootnoteRef,
    Heading,
    Inline,
    Link,
    List,
    Location,
    Mark,
    Paragraph,
    ParagraphStyle,
    Replace,
    Shown,
    Table,
    Text,
    Underline,
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


def _para(
    start: int, *runs: str | tuple[str, JsonObject], style: str = "NORMAL_TEXT"
) -> JsonObject:
    """A paragraph of runs, with the indices Docs would give them, from `start`.

    Each a string of plain text, or the text and its style."""
    elements: list[JsonObject] = []
    at = start
    for run in runs:
        plain: JsonObject = {}
        text, styled = (run, plain) if isinstance(run, str) else run
        elements.append(_run(text, at, **styled))
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


# ---- what the parser warns about, and where ------------------------

UNDERLINED: JsonObject = {"underline": True}


def _edits(doc: Document, words: str) -> list[tuple[str, int, int, object]]:
    """The fix of the one warning saying `words`, as each edit's kind, place, and new value."""
    (notice,) = [w for w in doc.warnings if words in str(w)]
    (mark,) = notice.marks
    out: list[tuple[str, int, int, object]] = []
    for edit in mark.fix:
        match edit:
            case Replace(location, text):
                out.append(("replace", location.start, location.end, text))
            case Underline(location, underline):
                out.append(("underline", location.start, location.end, underline))
            case Link(location, url):
                out.append(("link", location.start, location.end, url))
            case ParagraphStyle(location, style):
                out.append(("style", location.start, location.end, style))
    return out


def test_a_stray_shift_enter_is_deleted() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(_end(title), "🚇 words\v\n")
    doc = parse(_doc(title, body))
    # `🚇 words` is 8 units from 10, so the break is the 18th.
    assert _edits(doc, "stray") == [("replace", 18, 19, "")]


def test_shift_enter_between_lines_becomes_enter_and_extra_ones_go() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(_end(title), "\vone\v", "\vtwo 🚇\v\n")
    doc = parse(_doc(title, body))
    assert _edits(doc, "give each line its own") == [
        ("replace", 10, 11, ""),
        ("replace", 14, 15, "\n"),
        ("replace", 15, 16, ""),
        ("replace", 22, 23, ""),
    ]


def test_a_caption_label_is_deleted_with_its_space() -> None:
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
    caption = _para(12, " Caption:  🚇 A train.\n")
    document = _doc(title, picture, caption)
    properties: JsonObject = {}
    document["inlineObjects"] = {
        "i": {"inlineObjectProperties": {"embeddedObject": {"imageProperties": properties}}}
    }
    doc = parse(document)
    assert _edits(doc, "starts with `Caption:`") == [("replace", 13, 23, "")]


def test_a_picture_styled_as_a_heading_is_set_to_normal_text() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    picture = {
        "startIndex": 10,
        "endIndex": 12,
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "HEADING_2"},
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
    assert _edits(doc, "styled as a `Heading`") == [("style", 10, 12, "NORMAL_TEXT")]


def test_an_archive_today_link_is_pointed_at_the_page_it_captured() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    capture = "https://archive.ph/2024.01.01-000000/https://example.org/page"
    body = _para(_end(title), "See ", ("the 🚇 page", {"link": {"url": capture}}), ".\n")
    doc = parse(_doc(title, body))
    assert _edits(doc, "archive.today link;") == [
        ("link", 14, 25, "https://example.org/page"),
    ]


def test_a_label_s_underline_is_taken_off_its_value() -> None:
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
    credit = _para(12, ("Credit: 🚇 MT", UNDERLINED), "A\n")
    document = _doc(title, picture, credit)
    properties: JsonObject = {}
    document["inlineObjects"] = {
        "i": {"inlineObjectProperties": {"embeddedObject": {"imageProperties": properties}}}
    }
    doc = parse(document)
    # From after the colon, 19 units on, to the end of the underlined run.
    assert _edits(doc, "runs past it") == [("underline", 19, 25, False)]


# ---- the `Header` section ------------------------------------------


def _field(start: int, key: str, value: str) -> JsonObject:
    return _para(start, (key, UNDERLINED), f": {value}\n")


def _header(*lines: tuple[str, str]) -> list[JsonObject]:
    """A `Header` heading at 1 and a field paragraph for each of `lines` after it."""
    content = [_para(1, "Header\n", style="HEADING_1")]
    for key, value in lines:
        content.append(_field(_end(content[-1]), key, value))
    content.append(_para(_end(content[-1]), "Headline\n", style="TITLE"))
    # Something under the headline, which `check` needs to be there.
    content.append(_para(_end(content[-1]), "Body.\n"))
    return content


def test_each_header_line_is_where_it_was_written() -> None:
    doc = parse(_doc(*_header(("Short", "🚇 Trains."), ("URL", "/reports/x"))))
    assert doc.header == Location(TAB, None, 1, 8)
    short = doc.header_lines["Short"]
    assert short.key == Location(TAB, None, 8, 13)
    # The line, newline left out: `Short: 🚇 Trains.` is 17 units.
    assert short.location == Location(TAB, None, 8, 25)
    assert doc.header_line("URL") == Location(TAB, None, 26, 41)
    assert short.find("Trains", 1, 3) == Location(TAB, None, 19, 21)
    assert doc.meta == {"Short": "🚇 Trains.", "URL": "/reports/x"}


def test_a_wrapped_header_line_runs_onto_the_next() -> None:
    content = [
        _para(1, "Header\n", style="HEADING_1"),
        _para(8, ("Short", UNDERLINED), ": one\vtwo\n"),
        _para(23, "Headline\n", style="TITLE"),
    ]
    doc = parse(_doc(*content))
    assert doc.meta["Short"] == "one two"
    # To the end of `two`, after the vertical tab at 18.
    assert doc.header_line("Short") == Location(TAB, None, 8, 22)
    assert doc.header_lines["Short"].find("two") == Location(TAB, None, 19, 22)


def test_a_retired_field_is_renamed() -> None:
    doc = parse(_doc(*_header(("Excerpt", "🚇"))))
    assert _edits(doc, "no longer used") == [("replace", 8, 15, "Short")]


def test_a_repeated_field_marks_both_lines() -> None:
    doc = parse(_doc(*_header(("Short", "one"), ("Short", "two"))))
    (notice,) = [w for w in doc.warnings if "more than one" in str(w)]
    assert [mark.location for mark in notice.marks] == [
        Location(TAB, None, 8, 18),
        Location(TAB, None, 19, 29),
    ]
    assert doc.header_line("Short") == Location(TAB, None, 19, 29)


def test_a_missing_comma_after_an_address_is_put_in() -> None:
    doc = parse(_doc(*_header(("Public Contributors", "Ana 🚇 (ana@x.org) Bo Li, Cy"))))
    check(doc)
    # `Public Contributors: Ana 🚇 (ana@x.org)` from 8 is 38 units.
    assert _edits(doc, "a comma is missing") == [("replace", 47, 47, ",")]


# ---- what the checks warn about, and where -------------------------


def _picture(start: int) -> JsonObject:
    return {
        "startIndex": start,
        "endIndex": start + 2,
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [
                {
                    "startIndex": start,
                    "endIndex": start + 1,
                    "inlineObjectElement": {"inlineObjectId": "i"},
                },
                _run("\n", start + 1),
            ],
        },
    }


def _with_picture(document: JsonObject) -> JsonObject:
    properties: JsonObject = {}
    document["inlineObjects"] = {
        "i": {"inlineObjectProperties": {"embeddedObject": {"imageProperties": properties}}}
    }
    return document


def test_a_credit_label_left_plain_is_underlined() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    caption = _para(12, "🚇 A train.\n")
    credit = _para(_end(caption), " Credit : MTA\n")
    doc = parse(_with_picture(_doc(title, _picture(10), caption, credit)))
    check(doc)
    # `Credit`, after the caption's 12 units and the space, before the space and colon.
    assert _edits(doc, "not read as its credit") == [("underline", 25, 31, True)]


def test_a_video_line_is_made_a_copy() -> None:
    title = _para(1, "Headline 🚇\n", style="TITLE")
    url = "https://www.youtube.com/watch?v=abc"
    video = _para(13, ("Video", UNDERLINED), ": ", ("clip", {"link": {"url": url}}), "\n")
    captions = _para(_end(video), ("Captions", UNDERLINED), ": 0:01-0:02 Hi\n")
    doc = parse(_doc(title, video, captions))
    doc.cards[url] = Card(text="clip")
    check_embeds(doc)
    assert _edits(doc, "add `Copy`") == [("replace", 18, 18, " (Copy)")]


# ---- warnings listing many places ----------------------------------


def test_a_tracking_tag_is_taken_off_each_link() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    tagged = "https://example.org/a?id=1&utm_source=chatgpt.com#top"
    linked: JsonObject = {"link": {"url": tagged}}
    bold: JsonObject = {"link": {"url": tagged}, "bold": True}
    body = _para(10, "🚇 ", ("the ", linked), ("page", bold), ", and ", ("again", linked), ".\n")
    doc = parse(_doc(title, body))
    check(doc)
    (notice,) = [w for w in doc.warnings if "copied with" in str(w)]
    untagged = "https://example.org/a?id=1#top"
    assert [(m.location.start, m.location.end, m.fix, m.text) for m in notice.marks] == [
        (
            13,
            21,
            (Link(Location(TAB, None, 13, 21), untagged),),
            (Shown("utm_source=chatgpt.com"), " on ", Shown(tagged)),
        ),
        (
            27,
            32,
            (Link(Location(TAB, None, 27, 32), untagged),),
            (Shown("utm_source=chatgpt.com"), " on ", Shown(tagged)),
        ),
    ]


def test_an_archived_link_keeps_its_archive_when_its_tag_comes_off() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    page = "https://example.org/a?utm_medium=x"
    archived = f"https://web.archive.org/web/20240101000000/{page}"
    body = _para(10, ("cited", {"link": {"url": archived}}), ".\n")
    doc = parse(_doc(title, body))
    check(doc)
    (notice,) = [w for w in doc.warnings if "copied with" in str(w)]
    (mark,) = notice.marks
    assert mark.fix == (
        Link(
            Location(TAB, None, 10, 15),
            "https://web.archive.org/web/20240101000000/https://example.org/a",
        ),
    )


def test_each_bare_url_is_linked_where_it_is_typed() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    body = _para(
        10,
        "See 🚇 https://doi.org/10.3141/",
        "1735-13. Or ",
        ("this", {"link": {"url": "https://x.org"}}),
        " http://a.b/c\n",
    )
    doc = parse(_doc(title, body))
    check(doc)
    (notice,) = [w for w in doc.warnings if "typed out" in str(w)]
    assert [(m.fix, m.text) for m in notice.marks] == [
        (
            (Link(Location(TAB, None, 17, 48), "https://doi.org/10.3141/1735-13"),),
            (Shown("https://doi.org/10.3141/1735-13"),),
        ),
        (
            (Link(Location(TAB, None, 58, 70), "http://a.b/c"),),
            (Shown("http://a.b/c"),),
        ),
    ]


def test_each_unnamed_image_and_url_shown_as_text_is_marked_with_its_own_line() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    caption = _para(12, "A train.\n")
    url = "https://x.org/page"
    body = _para(_end(caption), ("🚇 " + url, {"link": {"url": url}}), "\n")
    doc = parse(_with_picture(_doc(title, _picture(10), caption, body)))
    check(doc)
    (unnamed,) = [w for w in doc.warnings if "unnamed" in str(w)]
    filename = doc.figures[0].image.filename
    assert unnamed.marks == (
        Mark(Location(TAB, None, 10, 11), text=(Shown(filename), ": A train.")),
    )
    # Not a URL as text: it opens with the emoji, so nothing is marked for it.
    assert not [w for w in doc.warnings if "as its text" in str(w)]


def test_a_link_showing_its_url_is_marked() -> None:
    title = _para(1, "Headline\n", style="TITLE")
    url = "https://x.org/page"
    body = _para(10, "🚇 ", (url, {"link": {"url": url}}), "\n")
    doc = parse(_doc(title, body))
    check(doc)
    (notice,) = [w for w in doc.warnings if "as its text" in str(w)]
    assert notice.marks == (Mark(Location(TAB, None, 13, 31), text=(Shown(url),)),)
