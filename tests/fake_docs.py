"""A Google Doc in memory, read and written as the Docs API reads and writes one.

As much of it as `inline` and `suggest` use, and as the API was seen to behave in testing:
a suggested deletion leaves its text in place, marked;
a suggested insertion takes up indices in the text read with suggestions inline
and none in the text read without them;
and a Commenter may comment, but not edit.

One tab, a body, and footnotes; every character is one UTF-16 unit.
"""

from dataclasses import dataclass, field
from itertools import count, groupby

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Location
from eta_publish.suggest import RevisionChanged

TAB = "t.0"


@dataclass(eq=False)
class Unit:
    char: str
    inserted: str | None = None
    deleted: set[str] = field(default_factory=set)
    restyle: dict[str, tuple[str, object]] = field(default_factory=dict)
    style: str = "NORMAL_TEXT"
    """The paragraph's named style, on its newline."""
    restyle_paragraph: dict[str, str] = field(default_factory=dict)


class Refused(Exception):
    """What the API answers a Commenter asking for a plain edit."""


class FakeDocs:
    def __init__(self, body: str, footnotes: dict[str, str] | None = None) -> None:
        self.segments: dict[str | None, list[Unit]] = {None: [Unit(c) for c in body]}
        for footnote_id, text in (footnotes or {}).items():
            self.segments[footnote_id] = [Unit(c) for c in text]
        self.revision = 1
        self.comments: list[JsonObject] = []
        self.anchors: dict[str, tuple[str | None, Unit, Unit]] = {}
        self.suggestions: dict[str, JsonObject] = {}
        self.batches: list[list[JsonObject]] = []
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

    def _unit_at(self, segment: str | None, index: int) -> int:
        return index - self.offset(segment)

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

    def person_resolves(self, comment_id: str) -> None:
        self._comment(comment_id)["status"] = "RESOLVED"
        self.bump()

    def person_comments(self, content: str, on: str) -> str:
        """A comment of someone else's, which `suggest` must leave alone."""
        where = self.at(on)
        thread = self._insert_comment({"content": content, "range": _range(where)}, me=False)
        return thread["commentId"]

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
            anchors: JsonObject = {}
            tab["commentAnchors"] = anchors
            for anchor, (segment, first, last) in self.anchors.items():
                units = self.segments[segment]
                if first in units and last in units:
                    start = units.index(first) + self.offset(segment)
                    end = units.index(last) + 1 + self.offset(segment)
                    found: JsonObject = {"startIndex": start, "endIndex": end}
                    if segment:
                        found["segmentId"] = segment
                    anchors[anchor] = {"anchorId": anchor, "ranges": [found]}
            document["comments"] = [dict(c) for c in self.comments]
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
            return (unit.inserted, tuple(sorted(unit.deleted)), tuple(sorted(unit.restyle.items())))

        for _, run in groupby(units, key=key):
            run = list(run)
            text_run: JsonObject = {"content": "".join(u.char for u in run), "textStyle": {}}
            first = run[0]
            if inline:
                if first.inserted:
                    text_run["suggestedInsertionIds"] = [first.inserted]
                if first.deleted:
                    text_run["suggestedDeletionIds"] = sorted(first.deleted)
                if first.restyle:
                    text_run["suggestedTextStyleChanges"] = {
                        sid: {
                            "textStyle": {name: {"url": value} if name == "link" else value}
                            if value
                            else {},
                            "textStyleSuggestionState": {f"{name}Suggested": True},
                        }
                        for sid, (name, value) in first.restyle.items()
                    }
            element: JsonObject = {"endIndex": at + len(run), "textRun": text_run}
            if at:
                element["startIndex"] = at
            elements.append(element)
            at += len(run)
        last = units[-1]
        paragraph: JsonObject = {
            "elements": elements,
            "paragraphStyle": {"namedStyleType": last.style},
        }
        if inline and last.restyle_paragraph:
            paragraph["suggestedParagraphStyleChanges"] = {
                sid: {
                    "paragraphStyle": {"namedStyleType": named},
                    "paragraphStyleSuggestionState": {"namedStyleTypeSuggested": True},
                }
                for sid, named in last.restyle_paragraph.items()
            }
        found: JsonObject = {"endIndex": start + len(units), "paragraph": paragraph}
        if start:
            found["startIndex"] = start
        return found

    def batch(self, doc_id: str, requests: list[JsonObject], revision: str | None) -> JsonObject:
        if revision is not None and revision != f"rev{self.revision}":
            raise RevisionChanged("the required revision is not the current one")
        self.batches.append(requests)
        replies: list[JsonObject] = []
        for request in requests:
            ((name, body),) = request.items()
            reply: JsonObject = {}
            if name == "insertComment":
                reply = {"insertComment": {"commentThread": self._insert_comment(body, me=True)}}
            elif name == "updateCommentPost":
                comment = self._comment(body["commentId"])
                assert comment["headPost"]["postId"] == body["postId"]
                comment["headPost"] = {**comment["headPost"], "content": body["content"]}
            elif name == "addCommentReply":
                action = body["post"]["commentAction"]
                self._comment(body["commentId"])["status"] = (
                    "RESOLVED" if action == "RESOLVE" else "OPEN"
                )
            elif name == "deleteComment":
                self.comments.remove(self._comment(body["commentId"]))
            else:
                raise Refused(f"{name}: write access is required")
            replies.append(reply)
        self.bump()
        return {"replies": replies}

    def _span(self, segment: str | None, found: JsonObject) -> tuple[int, int]:
        start = self._unit_at(segment, found["startIndex"])
        end = self._unit_at(segment, found["endIndex"])
        assert 0 <= start < end <= len(self.segments[segment]), (start, end)
        return start, end

    @staticmethod
    def _thread(sid: str, me: bool) -> JsonObject:
        return {
            "suggestionId": sid,
            "status": "OPEN",
            "headPost": {"postId": f"post.{sid}", "author": {"me": me}},
        }

    def _insert_comment(self, body: JsonObject, me: bool) -> JsonObject:
        found = body["range"]
        assert found.get("tabId") == TAB
        segment = found.get("segmentId")
        start, end = self._span(segment, found)
        units = self.segments[segment]
        n = next(self._ids)
        anchor = f"kix.anchor{n}"
        self.anchors[anchor] = (segment, units[start], units[end - 1])
        thread: JsonObject = {
            "commentId": f"doco.{n}",
            "anchorId": anchor,
            "status": "OPEN",
            "headPost": {
                "postId": f"doco.{n}",
                "content": body["content"],
                "author": {"me": me},
            },
        }
        self.comments.append(thread)
        return thread

    def _comment(self, comment_id: str) -> JsonObject:
        return next(c for c in self.comments if c["commentId"] == comment_id)

    def commented(self, comment_id: str) -> str:
        """The text a comment is anchored to, as it reads with suggestions inline."""
        thread = self._comment(comment_id)
        segment, first, last = self.anchors[thread["anchorId"]]
        units = self.segments[segment]
        return "".join(u.char for u in units[units.index(first) : units.index(last) + 1])


def _range(where: Location) -> JsonObject:
    found: JsonObject = {"startIndex": where.start, "endIndex": where.end, "tabId": TAB}
    if where.segment_id:
        found["segmentId"] = where.segment_id
    return found
