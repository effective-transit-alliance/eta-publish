"""Where things are in a document read with its suggestions in it, against a document in memory.

Each place is taken where the build reads it (`FakeDocs.at`, read without suggestions)
and looked for in the document as it reads with every suggestion in it.
"""

import pytest
from fake_docs import FakeDocs

from eta_publish.docs_json import JsonObject
from eta_publish.inline import PLACEHOLDER, Live, Units, Unplaceable, align, read_units
from eta_publish.nodes import utf16_length

BODY = "A headline\nThe line is 137 feet long, and the ETA says so.\nA last paragraph.\n"


def tab(document: JsonObject) -> JsonObject:
    return document["tabs"][0]["documentTab"]


def seen(docs: FakeDocs) -> dict[str | None, Units]:
    """The tab as the build reads it."""
    return read_units(tab(docs.get("doc", inline=False)))


def inline(docs: FakeDocs) -> dict[str | None, Units]:
    """The tab with every suggestion in it."""
    return read_units(tab(docs.get("doc", inline=True)))


def lives(docs: FakeDocs, read: dict[str | None, Units] | None = None) -> dict[str | None, Live]:
    """Each segment with every suggestion in it, lined up with `read`, or the build's reading."""
    read = seen(docs) if read is None else read
    return {segment: align(units, read.get(segment)) for segment, units in inline(docs).items()}


def test_a_tab_is_read_unit_by_unit_and_each_footnote_on_its_own() -> None:
    docs = FakeDocs(BODY, {"kix.note": " A footnote.\n"})
    units = seen(docs)
    assert units[None].chars[0] == PLACEHOLDER
    assert units[None].text(1, len(units[None].chars)) == BODY
    assert units["kix.note"].text(0, len(units["kix.note"].chars)) == " A footnote.\n"


def tab_of(*content: JsonObject) -> JsonObject:
    """A tab whose body is a section break, then `content`."""
    section_break: JsonObject = {"endIndex": 1, "sectionBreak": {}}
    return {"body": {"content": [section_break, *content]}}


def text_at(start: int, text: str) -> JsonObject:
    """A paragraph of one run of text, starting at `start`."""
    end = start + utf16_length(text)
    run: JsonObject = {"startIndex": start, "endIndex": end, "textRun": {"content": text}}
    return {"startIndex": start, "endIndex": end, "paragraph": {"elements": [run]}}


def test_a_character_outside_the_basic_multilingual_plane_takes_two_units() -> None:
    (units,) = read_units(tab_of(text_at(1, "a😀\n"))).values()
    assert units.chars == [PLACEHOLDER, "a", "😀", "", "\n"]


def test_a_table_takes_units_of_its_own_around_the_text_in_it() -> None:
    cell: JsonObject = {"startIndex": 2, "endIndex": 7, "content": [text_at(3, "abc\n")]}
    table: JsonObject = {
        "startIndex": 1,
        "endIndex": 8,
        "table": {"tableRows": [{"tableCells": [cell]}]},
    }
    (units,) = read_units(tab_of(table)).values()
    assert units.chars == [PLACEHOLDER] * 3 + list("abc\n") + [PLACEHOLDER]


def test_text_someone_suggested_before_a_place_moves_where_it_is() -> None:
    docs = FakeDocs(BODY)
    where = docs.at("feet")
    docs.person_inserts("XYZ ", after="A head")
    live = lives(docs)[None]
    assert live.aligned
    start, end = live.place(where.start, where.end, clear=False)
    assert (start, end) == (where.start + len("XYZ "), where.end + len("XYZ "))
    assert live.units.text(start, end) == "feet"
    assert (live.preview_of[start], live.preview_of[end]) == (where.start, where.end)


def test_a_suggested_deletion_is_where_it_was_in_both_readings() -> None:
    docs = FakeDocs(BODY)
    docs.person_deletes("A last")
    where = docs.at("feet")
    live = lives(docs)[None]
    assert live.place(where.start, where.end, clear=False) == (where.start, where.end)
    deleted = docs.at("A last")
    assert all(live.units.deleted[deleted.start : deleted.end])


def test_a_place_in_a_footnote_is_found_in_that_footnote() -> None:
    docs = FakeDocs(BODY, {"kix.note": " A footnote with the ETA in it.\n"})
    where = docs.at("the ETA", "kix.note")
    docs.person_inserts("new ", after=" A ", segment="kix.note")
    live = lives(docs)["kix.note"]
    start, end = live.place(where.start, where.end, clear=False)
    assert live.units.text(start, end) == "the ETA"


def test_text_that_changed_after_the_build_read_it_is_not_written_to() -> None:
    docs = FakeDocs(BODY)
    before = seen(docs)
    docs.person_edits("137", "140")
    live = lives(docs, before)[None]
    assert not live.aligned
    where = docs.at("feet")
    with pytest.raises(Unplaceable, match="changed since"):
        live.place(where.start, where.end, clear=False)


def test_a_place_past_the_end_is_not_written_to() -> None:
    docs = FakeDocs(BODY)
    live = lives(docs)[None]
    count = len(live.inline_of)
    with pytest.raises(Unplaceable, match="past the end"):
        live.place(count, count + 1, clear=False)


def test_a_suggestion_may_not_overlap_an_open_suggestion_and_a_comment_may() -> None:
    docs = FakeDocs(BODY)
    docs.person_deletes("137 feet")
    where = docs.at("feet")
    live = lives(docs)[None]
    with pytest.raises(Unplaceable, match="overlaps a suggestion"):
        live.place(where.start, where.end, clear=True)
    assert live.place(where.start, where.end, clear=False) == (where.start, where.end)


def test_an_insertion_may_not_go_against_someone_elses_insertion() -> None:
    docs = FakeDocs(BODY)
    where = docs.point("The line is ")
    docs.person_inserts("very ", after="The line is ")
    live = lives(docs)[None]
    with pytest.raises(Unplaceable, match="right there"):
        live.place(where.start, where.end, clear=True)
    at, _ = live.place(where.start, where.end, clear=False)
    assert live.units.text(at, at + len("137")) == "137"


def test_the_text_as_it_will_be_once_suggestions_are_deleted() -> None:
    docs = FakeDocs(BODY)
    inserted = docs.person_inserts("XYZ ", after="A head")
    deleted = docs.person_deletes("A last")
    units = inline(docs)[None]
    gone = units.without({inserted, deleted})
    assert "".join(gone.chars[1:]) == BODY
    assert not any(gone.inserted)
    assert not any(gone.deleted)
    kept = units.without({inserted})
    where = docs.at("A last")
    assert all(kept.deleted[where.start : where.end])
    # Lined up with the build's reading, which has neither, the text left is the same.
    assert align(kept, seen(docs)[None]).aligned
