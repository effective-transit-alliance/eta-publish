"""Where things are in a Google Doc as it is written to, lined up with where the build reads them.

The build reads a document with its open suggestions left out,
so its indices count none of the text anyone has suggested adding;
a write into the document counts it, as the document reads with every suggestion in it.
This reads each segment of a tab, the body and each footnote, unit by unit as Docs counts them,
lines the two readings up, and says where a place the build read is in the other,
or why it cannot be written to safely.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from .docs_json import JsonObject
from .nodes import utf16_length

PLACEHOLDER = "\0"
"""What stands for a unit of the document that is not text: a table's edge, a chip, an image."""


@dataclass
class Piece:
    """One element of a paragraph, as the suggestions on it are read off it."""

    start: int
    end: int
    text: str
    inserted_by: tuple[str, ...]
    deleted_by: tuple[str, ...]


@dataclass
class Units:
    """One segment of a tab, the body or a footnote, as Docs counts it: in UTF-16 units.

    `chars[i]` is the unit at index `i`: a character, empty for the second unit of one
    outside the Basic Multilingual Plane, or `PLACEHOLDER` where it is not text.
    """

    chars: list[str] = field(default_factory=list)
    inserted: list[bool] = field(default_factory=list)
    """Whether each unit is in a suggested insertion, whoever suggested it."""
    deleted: list[bool] = field(default_factory=list)
    """Whether each unit is in a suggested deletion, whoever suggested it."""
    pieces: list[Piece] = field(default_factory=list)

    def _grow(self, end: int) -> None:
        while len(self.chars) < end:
            self.chars.append(PLACEHOLDER)
            self.inserted.append(False)
            self.deleted.append(False)

    def put(
        self, start: int, end: int, text: str, inserted: Sequence[str], deleted: Sequence[str]
    ) -> None:
        """The units `start` to `end`, holding `text`, suggested to be inserted and deleted
        by the suggestions `inserted` and `deleted`."""
        self._grow(end)
        if text:
            at = start
            for character in text:
                width = utf16_length(character)
                if at + width > end:
                    break
                self.chars[at] = character
                for second in range(at + 1, at + width):
                    self.chars[second] = ""
                at += width
        else:
            for at in range(start, end):
                self.chars[at] = PLACEHOLDER
        for at in range(start, end):
            self.inserted[at] = self.inserted[at] or bool(inserted)
            self.deleted[at] = self.deleted[at] or bool(deleted)

    def text(self, start: int, end: int) -> str:
        return "".join(self.chars[start:end])

    def without(self, ids: set[str]) -> Units:
        """These units as they will be once the suggestions `ids` are deleted.

        Only the units and what is suggested of them, which is what placing an edit reads.
        """
        gone: set[int] = set()
        deleted = list(self.deleted)
        for piece in self.pieces:
            if piece.inserted_by and set(piece.inserted_by) <= ids:
                gone.update(range(piece.start, piece.end))
            if piece.deleted_by:
                still = bool(set(piece.deleted_by) - ids)
                for at in range(piece.start, piece.end):
                    deleted[at] = still
        kept = [at for at in range(len(self.chars)) if at not in gone]
        return Units(
            [self.chars[at] for at in kept],
            [self.inserted[at] for at in kept],
            [deleted[at] for at in kept],
        )


def _element_body(element: JsonObject) -> JsonObject:
    """The one object a paragraph element holds: its `textRun`, `footnoteReference`, and so on."""
    return next((v for k, v in element.items() if isinstance(v, dict) and k != "textStyle"), {})


def _read_content(content: list[JsonObject], units: Units) -> None:
    for item in content:
        start = item.get("startIndex", 0)
        end = item.get("endIndex", start)
        if "paragraph" in item:
            paragraph = item["paragraph"]
            units._grow(end)
            for element in paragraph.get("elements", []):
                e_start = element.get("startIndex", 0)
                e_end = element.get("endIndex", e_start)
                body = _element_body(element)
                text = body.get("content", "") if "textRun" in element else ""
                inserted = tuple(body.get("suggestedInsertionIds", ()))
                deleted = tuple(body.get("suggestedDeletionIds", ()))
                units.put(e_start, e_end, text, inserted, deleted)
                units.pieces.append(Piece(e_start, e_end, text, inserted, deleted))
        else:
            # A table, its rows and cells, a table of contents, a section break:
            # each takes up units of its own, around whatever paragraphs are inside it.
            kind: JsonObject = next((v for v in item.values() if isinstance(v, dict)), {})
            units.put(
                start,
                end,
                "",
                kind.get("suggestedInsertionIds", []),
                kind.get("suggestedDeletionIds", []),
            )
            for row in kind.get("tableRows", []):
                row_inserted = row.get("suggestedInsertionIds", [])
                for cell in row.get("tableCells", []):
                    cell_inserted = [*row_inserted, *cell.get("suggestedInsertionIds", [])]
                    if cell_inserted:
                        units.put(
                            cell.get("startIndex", 0), cell["endIndex"], "", cell_inserted, ()
                        )
                    _read_content(cell.get("content", []), units)
            _read_content(kind.get("content", []), units)


def read_units(tab: JsonObject) -> dict[str | None, Units]:
    """Every segment of a tab, unit by unit: `None` for the body, each footnote by its id."""
    segments: dict[str | None, Units] = {}
    body = Units()
    _read_content(tab.get("body", {}).get("content", []), body)
    segments[None] = body
    for footnote_id, footnote in tab.get("footnotes", {}).items():
        units = Units()
        _read_content(footnote.get("content", []), units)
        segments[footnote_id] = units
    return segments


class Unplaceable(Exception):
    """A place that cannot be written to safely, and why."""


@dataclass
class Live:
    """A segment as it is with every suggestion in it, lined up with the build's reading of it.

    The build reads the document with suggestions left out, so its indices count none of
    the text anyone has suggested adding; the document is written to with that text in it.
    Suggested deletions are in both: rejecting one leaves the text where it was.
    """

    units: Units
    inline_of: list[int]
    """For each unit the build read, by its index there, its index here."""
    preview_of: list[int]
    """For each index here, and one past the end, the index the build reads it at."""
    aligned: bool
    """Whether this, less its suggested insertions, is exactly the text the build read.

    Not, and nothing here is written to: the document changed after the warnings were
    worked out, or holds something whose suggestion this cannot line up."""

    def place(self, start: int, end: int, clear: bool) -> tuple[int, int]:
        """Where `start` to `end`, as the build read them, are here.

        `clear` is for a suggestion, which may not overlap anyone's open suggestion
        or sit against someone's suggested insertion, where which side of it the edit
        goes on is a guess. A comment may: it is anchored to text, whatever is suggested in it.
        """
        if not self.aligned:
            raise Unplaceable("the text there has changed since the warnings were read")
        count = len(self.inline_of)
        if not 0 <= start <= end <= count:
            raise Unplaceable("it is past the end of the text")
        if start == end:
            at = self.inline_of[start] if start < count else len(self.units.chars)
            after = self.inline_of[start - 1] + 1 if start else 0
            if clear and at != after:
                raise Unplaceable("someone's suggested insertion is right there")
            return at, at
        first = self.inline_of[start]
        last = self.inline_of[end - 1] + 1
        if clear and (any(self.units.inserted[first:last]) or any(self.units.deleted[first:last])):
            raise Unplaceable("it overlaps a suggestion still open there")
        return first, last


def align(units: Units, seen: Units | None) -> Live:
    """Line `units`, read with every suggestion in it, up with the build's reading, `seen`."""
    inline_of = [i for i, inserted in enumerate(units.inserted) if not inserted]
    preview_of = []
    count = 0
    for inserted in units.inserted:
        preview_of.append(count)
        count += not inserted
    preview_of.append(count)
    derived = [units.chars[i] for i in inline_of]
    aligned = seen is not None and derived == seen.chars
    return Live(units, inline_of, preview_of, aligned)
