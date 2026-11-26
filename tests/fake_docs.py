"""A Google Doc in memory, read as the Docs API reads one.

As much of it as `inline` reads, and as the API was seen to behave in testing:
a suggested deletion leaves its text in place, marked,
and a suggested insertion takes up indices in the text read with suggestions inline
and none in the text read without them.

One tab, a body, and footnotes; every character is one UTF-16 unit.
"""

from dataclasses import dataclass, field
from itertools import count, groupby

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Location

TAB = "t.0"


@dataclass(eq=False)
class Unit:
    char: str
    inserted: str | None = None
    deleted: set[str] = field(default_factory=set)


class FakeDocs:
    def __init__(self, body: str, footnotes: dict[str, str] | None = None) -> None:
        self.segments: dict[str | None, list[Unit]] = {None: [Unit(c) for c in body]}
        for footnote_id, text in (footnotes or {}).items():
            self.segments[footnote_id] = [Unit(c) for c in text]
        self.revision = 1
        self.suggestions: dict[str, JsonObject] = {}
        self._ids = count(1)

    # ---- where things are

    @staticmethod
    def offset(segment: str | None) -> int:
        """The body starts after its section break; a footnote at 0."""
        return 1 if segment is None else 0

    def preview_text(self, segment: str | None = None) -> str:
        return "".join(u.char for u in self.segments[segment] if u.inserted is None)

    def inline_text(self, segment: str | None = None) -> str:
        return "".join(u.char for u in self.segments[segment])

    def at(self, text: str, segment: str | None = None, nth: int = 0) -> Location:
        """Where the build reads `text`, its `nth` occurrence."""
        preview = self.preview_text(segment)
        start = -1
        for _ in range(nth + 1):
            start = preview.index(text, start + 1)
        start += self.offset(segment)
        return Location(TAB, segment, start, start + len(text))

    def point(self, before: str, segment: str | None = None) -> Location:
        """The point just after `before`, where the build reads it."""
        where = self.at(before, segment)
        return Location(TAB, segment, where.end, where.end)

    # ---- people

    def bump(self) -> None:
        self.revision += 1

    def person_inserts(self, text: str, after: str, segment: str | None = None) -> str:
        """Someone else suggests `text` just after `after`, as the build reads it."""
        sid = f"suggest.person{next(self._ids)}"
        units = self.segments[segment]
        preview_at = self.preview_text(segment).index(after) + len(after)
        seen = 0
        at = len(units)
        for i, unit in enumerate(units):
            if unit.inserted is None:
                if seen == preview_at:
                    at = i
                    break
                seen += 1
        units[at:at] = [Unit(c, inserted=sid) for c in text]
        self.suggestions[sid] = self._thread(sid, me=False)
        self.bump()
        return sid

    def person_deletes(self, text: str, segment: str | None = None) -> str:
        sid = f"suggest.person{next(self._ids)}"
        where = self.at(text, segment)
        for unit in self._preview_units(segment)[
            where.start - self.offset(segment) : where.end - self.offset(segment)
        ]:
            unit.deleted.add(sid)
        self.suggestions[sid] = self._thread(sid, me=False)
        self.bump()
        return sid

    def person_edits(self, old: str, new: str, segment: str | None = None) -> None:
        """Someone with edit access replaces `old` outright, as an edit and not a suggestion."""
        units = self.segments[segment]
        text = self.inline_text(segment)
        at = text.index(old)
        units[at : at + len(old)] = [Unit(c) for c in new]
        self.bump()

    def _preview_units(self, segment: str | None) -> list[Unit]:
        return [u for u in self.segments[segment] if u.inserted is None]

    # ---- the API

    def get(self, doc_id: str, inline: bool) -> JsonObject:
        tab: JsonObject = {
            "body": {"content": self._content(None, inline)},
            "footnotes": {
                segment: {"content": self._content(segment, inline)}
                for segment in self.segments
                if segment is not None
            },
        }
        document: JsonObject = {
            "documentId": doc_id,
            "title": "Doc",
            "revisionId": f"rev{self.revision}",
            "tabs": [{"tabProperties": {"tabId": TAB, "title": "Tab"}, "documentTab": tab}],
        }
        if inline:
            document["suggestions"] = [dict(t) for t in self.suggestions.values()]
        return document

    def _content(self, segment: str | None, inline: bool) -> list[JsonObject]:
        units = self.segments[segment] if inline else self._preview_units(segment)
        at = self.offset(segment)
        content: list[JsonObject] = [{"endIndex": 1, "sectionBreak": {}}] if segment is None else []
        paragraph: list[Unit] = []
        for unit in units:
            paragraph.append(unit)
            if unit.char == "\n" and not (not inline and unit.inserted):
                content.append(self._paragraph(paragraph, at, inline))
                at += len(paragraph)
                paragraph = []
        if paragraph:
            content.append(self._paragraph(paragraph, at, inline))
        return content

    def _paragraph(self, units: list[Unit], start: int, inline: bool) -> JsonObject:
        elements = []
        at = start

        def key(unit: Unit) -> tuple[object, ...]:
            if not inline:
                return ()
            return (unit.inserted, tuple(sorted(unit.deleted)))

        for _, run in groupby(units, key=key):
            run = list(run)
            text_run: JsonObject = {"content": "".join(u.char for u in run), "textStyle": {}}
            first = run[0]
            if inline:
                if first.inserted:
                    text_run["suggestedInsertionIds"] = [first.inserted]
                if first.deleted:
                    text_run["suggestedDeletionIds"] = sorted(first.deleted)
            element: JsonObject = {"endIndex": at + len(run), "textRun": text_run}
            if at:
                element["startIndex"] = at
            elements.append(element)
            at += len(run)
        paragraph: JsonObject = {"elements": elements}
        found: JsonObject = {"endIndex": start + len(units), "paragraph": paragraph}
        if start:
            found["startIndex"] = start
        return found

    @staticmethod
    def _thread(sid: str, me: bool) -> JsonObject:
        return {
            "suggestionId": sid,
            "status": "OPEN",
            "headPost": {"postId": f"post.{sid}", "author": {"me": me}},
        }
