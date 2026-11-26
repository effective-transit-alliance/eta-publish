"""`eta-publish suggest`: a publication's warnings, written into its Google Doc.

A build reports what it finds to whoever runs it. This puts it where the writers are:
a warning whose fix the code knows becomes a suggested edit at the place it is about,
and one only a person can fix becomes a comment there, ending with the line `key_line` writes.
A warning about no place in the document stays in the build's report.

Signed by the service account `eta-publish-ci`, which each document is shared with as a Commenter.
That is enough to suggest any edit, to comment anywhere, footnotes included,
and to reword, resolve, reopen, and delete its own threads;
not enough to edit the document or accept a suggestion, which stay a person's.

By default it only says what it would do: `--apply` is what writes.

Run again, it changes only what changed, and nothing at all when nothing did.
Only its own threads are ever touched, and they are told apart from a person's by their author.
A comment is the warning's by its key line.
A suggestion carries no text to keep a key in, so it is the warning's by the edit it makes, where.

The warnings are worked out here rather than read off the last build:
writing to a place needs to know exactly where it is in the document as it is now,
and a build's saved response is of the document as it was.
So the document is read twice, at one revision:
once as the build reads it, with open suggestions left out, to find the warnings,
and once with every suggestion and comment in it, which is what the writes are counted in.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from rich.console import Console
from rich.text import Text
lazy from googleapiclient.discovery import build
lazy from googleapiclient.errors import HttpError

from . import console
from .archive import check_pending, read_archive_index
from .build import read_image_index
from .checks import check, check_charts, check_described, check_pages
from .docs_json import JsonObject
from .embeds import check_embeds, read_embed_index
from .fetch import iter_tabs, parse_ref, select_tab, service_account_credentials, tab_id
from .inline import (
    PLACEHOLDER,
    Change,
    Kind,
    Live,
    Units,
    Unplaceable,
    align,
    read_units,
    suggested_changes,
    wanted_change,
)
from .nodes import (
    KEY_LABEL,
    Document,
    Edit,
    Link,
    Location,
    Mark,
    Notice,
    ParagraphStyle,
    Replace,
    Underline,
    key_line,
)
from .parse import parse
from .site import Publication, check_kind, publication_path
from .style import style

READS = 3
"""How many times to read a document before giving up on reading it at one revision."""

COMMENT_LIMIT = 2048
"""The longest a comment can be, in UTF-8 bytes, as the Docs API takes one."""


class SuggestFailed(RuntimeError):
    """A document this could not write into, for a reason to tell the person running it."""


class RevisionChanged(SuggestFailed):
    """A write refused because the document changed after the read it was worked out from."""


# ---- the API ----------------------------------------------------------


class Api(Protocol):
    """The two calls this makes: reading a document, and writing to it."""

    def get(self, doc_id: str, inline: bool) -> JsonObject:
        """The whole document, every tab: as the build reads it, or with everything open in it.

        `inline` is every suggestion in the text and every comment thread alongside it.
        """
        ...

    def batch(
        self, doc_id: str, requests: list[JsonObject], suggest: bool, revision: str | None
    ) -> JsonObject:
        """Send `requests` together, as suggestions if `suggest`.

        With a `revision`, only if the document is still at it, or `RevisionChanged`.
        """
        ...


class DocsApi:
    """The Docs API, as the service account."""

    def __init__(self) -> None:
        service = build("docs", "v1", credentials=service_account_credentials())
        # Generated from the discovery document at runtime, as in `fetch`.
        self.documents = service.documents()  # pyrefly: ignore[missing-attribute]

    def get(self, doc_id: str, inline: bool) -> JsonObject:
        extra = {"commentsViewMode": "COMMENTS_VIEW_MODE_INCLUDED"} if inline else {}
        request = self.documents.get(
            documentId=doc_id,
            includeTabsContent=True,
            suggestionsViewMode="SUGGESTIONS_INLINE" if inline else "PREVIEW_WITHOUT_SUGGESTIONS",
            **extra,
        )
        try:
            return request.execute()
        except HttpError as e:
            raise SuggestFailed(_explain(e)) from e

    def batch(
        self, doc_id: str, requests: list[JsonObject], suggest: bool, revision: str | None
    ) -> JsonObject:
        control: JsonObject = {}
        if suggest:
            control["writeMode"] = "SUGGEST"
        if revision:
            control["requiredRevisionId"] = revision
        body: JsonObject = {"requests": requests}
        if control:
            body["writeControl"] = control
        request = self.documents.batchUpdate(documentId=doc_id, body=body)
        try:
            answer = request.execute()
        except HttpError as e:
            if revision and e.status_code == 400 and "revision" in str(e.reason).lower():
                raise RevisionChanged(str(e.reason)) from e
            raise SuggestFailed(_explain(e)) from e
        # A comment write can fail with the batch still answered 200: only this says so.
        state = answer.get("commentUpdateState", "NO_UPDATES_REQUESTED")
        if state not in ("NO_UPDATES_REQUESTED", "ALL_SAVED"):
            raise SuggestFailed(f"the comments were not saved: `{state}`")
        return answer


def _explain(error: HttpError) -> str:
    """What the API said, with what to do about the refusals that have one thing to do."""
    if error.status_code == 403:
        return (
            f"refused ({error.reason}); the document has to be shared with "
            "the service account as a Commenter"
        )
    if error.status_code == 404:
        return "not found, or not shared with the service account"
    return f"the API returned {error.status_code}: {error.reason}"


# ---- the plan ----------------------------------------------------------


class Verb(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    REOPEN = "reopen"
    RESOLVE = "resolve"
    DELETE = "delete"
    KEEP = "keep"
    SKIP = "skip"


DONE = {
    Verb.CREATE: "created",
    Verb.UPDATE: "updated",
    Verb.REOPEN: "reopened",
    Verb.RESOLVE: "resolved",
    Verb.DELETE: "deleted",
    Verb.KEEP: "unchanged",
    Verb.SKIP: "skipped",
}


class Thing(StrEnum):
    COMMENT = "comment"
    SUGGESTION = "suggestion"


@dataclass
class Step:
    """One thing this does to the document, or decides not to, and why."""

    verb: Verb
    thing: Thing
    key: str
    """The warning's key; for a suggestion no warning asks for, what Docs sums it up as."""
    why: str = ""
    mark: Mark | None = None
    content: str = ""
    """A comment's text, for one created or updated."""
    comment_id: str = ""
    post_id: str = ""
    suggestion_id: str = ""
    made: str = ""
    """The id of the thread a write made, once it is made."""
    done: bool = False
    """Whether its write was sent and taken. A step a failed batch was to make is not."""


def comment_text(notice: Notice, mark: Mark, key: str) -> str:
    """A comment's text: what the warning says there, then its key, on a line of its own.

    Cut short to fit, which only ever loses words of the warning: the key is what finds it again.
    """
    last = "\n" + key_line(key)
    said = notice.said_at(mark)
    room = COMMENT_LIMIT - len(last.encode())
    if len(said.encode()) > room:
        said = said.encode()[: room - len("…".encode())].decode(errors="ignore") + "…"
    return said + last


def key_of(thread: JsonObject) -> str | None:
    """The key a comment ends with, if it is one of ours with a key line."""
    head = thread.get("headPost", {})
    if not head.get("author", {}).get("me"):
        return None
    lines = str(head.get("content", "")).rstrip().splitlines()
    if not lines or not lines[-1].startswith(KEY_LABEL):
        return None
    return lines[-1].removeprefix(KEY_LABEL)


def _order(location: Location | None) -> tuple[int, str, int]:
    """Document order, near enough: the body, then footnotes, then nowhere at all."""
    if location is None:
        return (2, "", 0)
    if location.segment_id is None:
        return (0, "", location.start)
    return (1, location.segment_id, location.start)


def tab_content(document: JsonObject, wanted: str) -> JsonObject:
    """One tab of a document read with `includeTabsContent`."""
    for _, tab in iter_tabs(document.get("tabs", [])):
        if tab_id(tab) == wanted or not wanted:
            return tab.get("documentTab", {})
    raise SuggestFailed(f"no tab `{wanted}` in the document as read for writing")


def _anchor(ranges: list[JsonObject], tab: str) -> Location | None:
    """Where a comment's anchor is in this tab, by its first stretch of text, if it has one."""
    for found in ranges:
        start = found.get("startIndex", 0)
        end = found.get("endIndex", start)
        if end > start:
            return Location(tab, found.get("segmentId"), start, end)
    return None


@dataclass
class Placed:
    """One mark of one warning, as this run wants it in the document."""

    notice: Notice
    mark: Mark
    key: str


def plan(
    notices: Sequence[Notice],
    seen: dict[str | None, Units],
    document: JsonObject,
    tab: str,
) -> list[Step]:
    """What to do so the document says what the warnings say, and no more of what it said.

    `document` is the whole document read with its suggestions and comments in it,
    at the revision `seen`, the tab as the build read it, is of.
    Only the service account's own threads on this tab are considered.

    A suggestion of ours a person rejected is gone from the text, so the mark it was for
    has no suggestion open and is suggested again, as a resolved comment is reopened:
    a warning is answered by fixing the document, or by fixing `eta-publish` where it is wrong.
    The API has no way to reopen a rejected suggestion, so the new one is a suggestion of its own.
    """
    content = tab_content(document, tab)
    lives = {
        segment: align(units, seen.get(segment)) for segment, units in read_units(content).items()
    }
    placed = [Placed(notice, mark, notice.key(mark)) for notice in notices for mark in notice.marks]
    steps: list[Step] = []
    steps += _plan_comments([p for p in placed if not p.mark.fix], document, content, tab, lives)
    steps += _plan_suggestions([p for p in placed if p.mark.fix], document, lives, seen)
    return steps


def _placeable(mark: Mark, lives: dict[str | None, Live]) -> str:
    """Why a comment on a mark cannot be written where it is, or nothing if it can."""
    where = mark.location
    live = lives.get(where.segment_id)
    if live is None:
        return "its footnote is not in the document as read for writing"
    try:
        live.place(where.start, where.end, clear=False)
    except Unplaceable as e:
        return str(e)
    return ""


def _fixable(mark: Mark, lives: dict[str | None, Live]) -> str:
    """Why a mark's fix cannot be suggested where it is, or nothing if it can."""
    for edit in mark.fix:
        where = edit.location
        live = lives.get(where.segment_id)
        if live is None:
            return "its footnote is not in the document as read for writing"
        try:
            live.place(where.start, where.end, clear=True)
        except Unplaceable as e:
            return str(e)
    return ""


def _plan_comments(
    placed: list[Placed],
    document: JsonObject,
    content: JsonObject,
    tab: str,
    lives: dict[str | None, Live],
) -> list[Step]:
    here = content.get("commentAnchors", {})
    elsewhere = {
        anchor
        for _, other in iter_tabs(document.get("tabs", []))
        if tab_id(other) != tab
        for anchor in other.get("documentTab", {}).get("commentAnchors", {})
    }
    threads: dict[str, list[tuple[Location | None, JsonObject]]] = defaultdict(list)
    for thread in document.get("comments", []):
        key = key_of(thread)
        anchor = thread.get("anchorId", "")
        if key is None or (anchor in elsewhere and anchor not in here):
            continue
        # One whose anchor is in no tab at all is ours wherever its key is warned:
        # its text is gone, so nothing says which tab it was on.
        where = _anchor(here.get(anchor, {}).get("ranges", []), tab)
        threads[key].append((where, thread))
    marks: dict[str, list[Placed]] = defaultdict(list)
    for one in placed:
        marks[one.key].append(one)

    steps: list[Step] = []
    for key in sorted(set(threads) | set(marks), key=lambda k: (k not in marks, k)):
        wanted = sorted(marks.get(key, []), key=lambda p: _order(p.mark.location))
        have = sorted(threads.get(key, []), key=lambda t: _order(t[0]))
        # Each comment with the warning at the very place it is on, first;
        # only the rest are paired in document order, so fixing one of two places
        # resolves the comment on that place and not the other.
        pairs: list[tuple[Placed | None, tuple[Location | None, JsonObject] | None]] = []
        unmatched: list[Placed] = []
        for one in wanted:
            spot = _comment_place(one.mark, lives)
            hit = next((t for t in have if spot is not None and _anchored_on(t[0], spot)), None)
            if hit is None:
                unmatched.append(one)
                continue
            have.remove(hit)
            pairs.append((one, hit))
        for n in range(max(len(unmatched), len(have))):
            pairs.append(
                (unmatched[n] if n < len(unmatched) else None, have[n] if n < len(have) else None)
            )
        for one, had in pairs:
            if had is None:
                assert one is not None
                steps.append(_create_comment(one, lives))
                continue
            where, thread = had
            ids = {
                "comment_id": thread["commentId"],
                "post_id": thread.get("headPost", {}).get("postId", ""),
            }
            if one is None:
                if thread.get("status") != "RESOLVED":
                    steps.append(Step(Verb.RESOLVE, Thing.COMMENT, key, "no longer warned", **ids))
                continue
            text = comment_text(one.notice, one.mark, key)
            if where is None:
                steps.append(
                    Step(Verb.DELETE, Thing.COMMENT, key, "the text it was on is gone", **ids)
                )
                steps.append(_create_comment(one, lives, "where the warning now is"))
                continue
            kept = True
            if thread.get("headPost", {}).get("content", "") != text:
                steps.append(
                    Step(
                        Verb.UPDATE,
                        Thing.COMMENT,
                        key,
                        "the warning says something else now",
                        mark=one.mark,
                        content=text,
                        **ids,
                    )
                )
                kept = False
            if thread.get("status") == "RESOLVED":
                steps.append(
                    Step(
                        Verb.REOPEN,
                        Thing.COMMENT,
                        key,
                        "resolved while the warning is still there",
                        mark=one.mark,
                        **ids,
                    )
                )
                kept = False
            if kept:
                steps.append(Step(Verb.KEEP, Thing.COMMENT, key, mark=one.mark, **ids))
    return steps


def _create_comment(one: Placed, lives: dict[str | None, Live], why: str = "") -> Step:
    reason = _placeable(one.mark, lives)
    if reason:
        return Step(Verb.SKIP, Thing.COMMENT, one.key, reason, mark=one.mark)
    text = comment_text(one.notice, one.mark, one.key)
    return Step(Verb.CREATE, Thing.COMMENT, one.key, why, mark=one.mark, content=text)


def _plan_suggestions(
    placed: list[Placed],
    document: JsonObject,
    lives: dict[str | None, Live],
    seen: dict[str | None, Units],
) -> list[Step]:
    ours = {
        thread["suggestionId"]: thread
        for thread in document.get("suggestions", [])
        if thread.get("headPost", {}).get("author", {}).get("me")
    }
    open_ids = {sid for sid, thread in ours.items() if thread.get("status") == "OPEN"}
    on_tab = suggested_changes(lives, open_ids)
    # Each open change of ours, by what it changes, with the suggestions making it.
    open_changes: dict[Change, list[str]] = defaultdict(list)
    for sid, changes in on_tab.items():
        for change in changes:
            open_changes[change].append(sid)
            if change.kind is Kind.REPLACE and change.start < change.end and change.value:
                # Also the deletion and the insertion it is made of: a deletion and
                # an insertion at its start, sent together for two marks, are one
                # suggestion in Docs, and each mark's is in it.
                for part in (replace(change, value=""), replace(change, end=change.start)):
                    open_changes[part].append(sid)

    steps: list[Step] = []
    claimed: set[str] = set()
    for one in sorted(placed, key=lambda p: _order(p.mark.location)):
        changes = [wanted_change(edit, seen) for edit in one.mark.fix]
        if all(open_changes.get(change) for change in changes):
            for change in changes:
                claimed.add(open_changes[change].pop(0))
            steps.append(Step(Verb.KEEP, Thing.SUGGESTION, one.key, mark=one.mark))
            continue
        steps.append(Step(Verb.CREATE, Thing.SUGGESTION, one.key, mark=one.mark))
    deleting: set[str] = set()
    for sid in sorted(set(on_tab) - claimed):
        segments = {change.segment for change in on_tab[sid]}
        said = str(ours[sid].get("summaryText", sid))
        if not all(lives[segment].aligned for segment in segments):
            steps.append(
                Step(
                    Verb.SKIP,
                    Thing.SUGGESTION,
                    said,
                    "the text there has changed since the warnings were read",
                    suggestion_id=sid,
                )
            )
            continue
        deleting.add(sid)
        steps.append(
            Step(Verb.DELETE, Thing.SUGGESTION, said, "no warning asks for it", suggestion_id=sid)
        )
    # Placed in the text as it will be once those are deleted, which is how it is placed
    # when it is written: a fix that changed overlaps its old suggestion until that is gone.
    after = {
        segment: align(live.units.without(deleting), seen.get(segment))
        for segment, live in lives.items()
    }
    planned: dict[str | None, list[tuple[int, int]]] = defaultdict(list)
    for step in steps:
        if step.verb is not Verb.CREATE or step.mark is None:
            continue
        reason = _fixable(step.mark, after)
        spans = [(e.location.segment_id, e.location.start, e.location.end) for e in step.mark.fix]
        if not reason and any(
            _overlap((start, end), other)
            for segment, start, end in spans
            for other in planned[segment]
        ):
            # Placed in one read and sent last to first, the second of two edits
            # on the same text would be placed in text the first has already moved.
            reason = "it overlaps another fix made in this run"
        if reason:
            step.verb = Verb.SKIP
            step.why = reason
            continue
        for segment, start, end in spans:
            planned[segment].append((start, end))
    return steps


def _overlap(one: tuple[int, int], other: tuple[int, int]) -> bool:
    """Whether two edits' places share text, or are one point; touching is not overlapping."""
    (start, end), (other_start, other_end) = one, other
    if start == end and other_start == other_end:
        return start == other_start
    if start == end:
        return other_start < start < other_end
    if other_start == other_end:
        return start < other_start < end
    return start < other_end and other_start < end


# ---- carrying it out ---------------------------------------------------


def _range(tab: str, segment: str | None, start: int, end: int) -> JsonObject:
    found: JsonObject = {"startIndex": start, "endIndex": end}
    if segment:
        found["segmentId"] = segment
    if tab:
        found["tabId"] = tab
    return found


def _point(tab: str, segment: str | None, index: int) -> JsonObject:
    found: JsonObject = {"index": index}
    if segment:
        found["segmentId"] = segment
    if tab:
        found["tabId"] = tab
    return found


def _thread_requests(steps: list[Step]) -> list[JsonObject]:
    """Every change to a thread already there, none of which moves any text."""
    requests: list[JsonObject] = []
    for step in steps:
        if step.thing is Thing.COMMENT:
            if step.verb is Verb.UPDATE:
                requests.append(
                    {
                        "updateCommentPost": {
                            "commentId": step.comment_id,
                            "postId": step.post_id,
                            "content": step.content,
                        }
                    }
                )
            elif step.verb in (Verb.REOPEN, Verb.RESOLVE):
                action = "REOPEN" if step.verb is Verb.REOPEN else "RESOLVE"
                requests.append(
                    {
                        "addCommentReply": {
                            "commentId": step.comment_id,
                            "post": {"commentAction": action},
                        }
                    }
                )
            elif step.verb is Verb.DELETE:
                requests.append({"deleteComment": {"commentId": step.comment_id}})
        elif step.verb is Verb.DELETE:
            requests.append({"deleteSuggestion": {"suggestionId": step.suggestion_id}})
    return requests


def _comment_place(mark: Mark, lives: dict[str | None, Live]) -> tuple[str | None, int, int] | None:
    """Where a comment on `mark` goes in the document as read for writing, or `None`.

    A comment is on text, so one about a point is on the character after it,
    or the one before where the next is not text: a paragraph's newline,
    which Docs leaves out of an anchor, or a table's edge.
    """
    where = mark.location
    live = lives.get(where.segment_id)
    if live is None:
        return None
    try:
        start, end = live.place(where.start, where.end, clear=False)
    except Unplaceable:
        return None
    if start == end:
        chars = live.units.chars
        after = chars[start] if start < len(chars) else PLACEHOLDER
        if start > 0 and after in ("\n", PLACEHOLDER):
            start -= 1
        else:
            end += 1
    return where.segment_id, start, end


def _anchored_on(where: Location | None, spot: tuple[str | None, int, int]) -> bool:
    """Whether a comment anchored at `where` is on `spot`, as `_comment_place` gives one.

    The API drops a newline ending an anchor, so one ending one unit short is on it too.
    """
    if where is None:
        return False
    segment, start, end = spot
    return where.segment_id == segment and where.start == start and where.end in (end, end - 1)


def _comment_request(step: Step, lives: dict[str | None, Live], tab: str) -> JsonObject:
    assert step.mark is not None
    if lives.get(step.mark.location.segment_id) is None:
        raise Unplaceable("its footnote is not in the document as read for writing")
    where = step.mark.location
    live = lives[where.segment_id]
    live.place(where.start, where.end, clear=False)
    spot = _comment_place(step.mark, lives)
    assert spot is not None
    segment, start, end = spot
    return {"insertComment": {"content": step.content, "range": _range(tab, segment, start, end)}}


def _suggestion_requests(
    step: Step, lives: dict[str | None, Live], tab: str
) -> list[tuple[str | None, int, list[JsonObject]]]:
    """Each edit of a mark's fix as the requests making it, with where it starts."""
    assert step.mark is not None
    made = []
    for edit in step.mark.fix:
        where = edit.location
        segment = where.segment_id
        live = lives.get(segment)
        if live is None:
            raise Unplaceable("its footnote is not in the document as read for writing")
        start, end = live.place(where.start, where.end, clear=not isinstance(edit, ParagraphStyle))
        requests: list[JsonObject] = []
        match edit:
            case Replace(text=text):
                # Deleted first: a suggested deletion leaves its text where it was,
                # so the insertion goes in at the same index, before it,
                # which is how Docs shows a replacement.
                if end > start:
                    requests.append(
                        {"deleteContentRange": {"range": _range(tab, segment, start, end)}}
                    )
                if text:
                    requests.append(
                        {"insertText": {"location": _point(tab, segment, start), "text": text}}
                    )
            case Underline(underline=underline):
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": _range(tab, segment, start, end),
                            "textStyle": {"underline": underline},
                            "fields": "underline",
                        }
                    }
                )
            case Link(url=url):
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": _range(tab, segment, start, end),
                            "textStyle": {"link": {"url": url}},
                            "fields": "link",
                        }
                    }
                )
            case ParagraphStyle(style=named):
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": _range(tab, segment, start, max(end, start + 1)),
                            "paragraphStyle": {"namedStyleType": named},
                            "fields": "namedStyleType",
                        }
                    }
                )
        made.append((segment, start, requests))
    return made


def read(api: Api, doc_id: str) -> tuple[JsonObject, JsonObject]:
    """The document as the build reads it and with everything in it, at one revision."""
    for _ in range(READS):
        preview = api.get(doc_id, inline=False)
        inline = api.get(doc_id, inline=True)
        if preview.get("revisionId") == inline.get("revisionId"):
            return preview, inline
    raise SuggestFailed("the document changed every time it was read; try again")


def carry_out(
    api: Api, doc_id: str, tab: str, steps: list[Step], seen: dict[str | None, Units]
) -> None:
    """Make the writes `steps` plan, in three batches, reading the document again before each.

    Changes to threads already there first, which go by id and move no text.
    Then the new comments, then the new suggestions, each placed in the document as just read:
    a suggestion deleted in the first batch takes its text with it.
    The suggestions go last to first, so none moves the place of one after it.
    The last two are sent only if the document is still at the revision they were placed in,
    and refused if it is not, which fails the run.
    A step that can no longer be placed is skipped.
    """
    threads = _thread_requests(steps)
    if threads:
        api.batch(doc_id, threads, suggest=False, revision=None)
        for step in steps:
            if step.verb in (Verb.UPDATE, Verb.REOPEN, Verb.RESOLVE, Verb.DELETE):
                step.done = True
    for thing in (Thing.COMMENT, Thing.SUGGESTION):
        wanted = [s for s in steps if s.verb is Verb.CREATE and s.thing is thing]
        if not wanted:
            continue
        _, inline = read(api, doc_id)
        lives = {
            segment: align(units, seen.get(segment))
            for segment, units in read_units(tab_content(inline, tab)).items()
        }
        placed: list[tuple[Step, list[tuple[str | None, int, list[JsonObject]]]]] = []
        for step in wanted:
            try:
                if thing is Thing.COMMENT:
                    placed.append((step, [(None, 0, [_comment_request(step, lives, tab)])]))
                else:
                    placed.append((step, _suggestion_requests(step, lives, tab)))
            except Unplaceable as e:
                step.verb = Verb.SKIP
                step.why = str(e)
        if not placed:
            continue
        edits = [
            (segment, start, n, requests)
            for n, (_, made) in enumerate(placed)
            for segment, start, requests in made
        ]
        # Last to first within each segment: an insertion moves only what comes after it.
        edits.sort(key=lambda e: (e[0] or "", e[1]), reverse=True)
        requests = [request for *_, made in edits for request in made]
        owners = [n for _, _, n, made in edits for _ in made]
        answer = api.batch(
            doc_id, requests, suggest=thing is Thing.SUGGESTION, revision=inline.get("revisionId")
        )
        _record(answer, placed, owners)
        for step, _ in placed:
            step.done = True


def _record(
    answer: JsonObject,
    placed: list[tuple[Step, list[tuple[str | None, int, list[JsonObject]]]]],
    owners: list[int],
) -> None:
    """Note on each step the id of what its requests made."""
    replies = answer.get("replies", [])
    suggested = answer.get("suggestionResponses", [])
    for n, owner in enumerate(owners):
        step = placed[owner][0]
        reply = replies[n] if n < len(replies) else {}
        thread = (reply or {}).get("insertComment", {}).get("commentThread", {})
        made = [thread.get("commentId", "")] if thread else []
        if n < len(suggested):
            made += (suggested[n] or {}).get("createdSuggestionIds", [])
        for one in made:
            if one and one not in step.made.split(", "):
                step.made = ", ".join(filter(None, [step.made, one]))


# ---- the warnings --------------------------------------------------------


def warnings_of(document: JsonObject, records: Path | None) -> tuple[Document, list[str]]:
    """The document parsed and checked as a build checks it, and anything to say about that.

    In the order `build.build_one` runs its checks, with what the last build recorded
    (image shapes, embeds, archive captures) read from `records`, its directory,
    and nothing downloaded or written. So the warnings are a build's, less the few
    only a download turns up: an image that differs from its source, or crops to nothing.

    A document with nothing saying where it publishes is still written into, which a build
    refuses: what is said about that, and the checks that need a path left out.
    """
    doc = parse(document)
    check(doc)
    said: list[str] = []
    try:
        publication_path(doc)
        check_kind(doc)
    except ValueError as e:
        said.append(f"{e}; written into all the same")
    style(doc)
    if records is not None:
        read_image_index(records, doc)
    check_described(doc)
    check_charts(doc)
    if records is not None:
        read_embed_index(records, doc)
    check_embeds(doc)
    if records is not None:
        read_archive_index(records, doc)
    check_pages(doc)
    check_pending(doc)
    return doc, said


def mismatch(publication: Publication, doc: Document) -> str:
    """How the document is not the one the entry names, or nothing.

    Only the name and the tab: those say whether this is the document meant at all,
    and writing into the wrong one is the mistake this has to refuse.
    """
    for said, expected, found in (
        ("calls this", publication.name, doc.file_title),
        ("expects the tab", publication.tab, doc.tab_title),
    ):
        if expected is not None and expected != found:
            return f"the list {said} `{expected}`, but the document says `{found}`"
    return ""


# ---- one publication, and all of them ---------------------------------------


@dataclass
class Outcome:
    publication: Publication
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""
    seen: dict[str | None, Units] = field(default_factory=dict)
    """The tab as the build read it, for quoting what a step is on."""


def suggest(
    api: Api,
    publication: Publication,
    records: Path | None,
    apply: bool,
    warnings: Callable[[JsonObject, Path | None], tuple[Document, list[str]]] | None = None,
) -> Outcome:
    """Work out what writing into one publication's document takes, and do it if `apply`.

    `warnings` is how the warnings are found, `warnings_of` unless a test says otherwise.
    """
    outcome = Outcome(publication)
    if "docs.google.com" not in publication.url and Path(publication.url).exists():
        outcome.error = "a saved response, not a document: there is nothing to write into"
        return outcome
    doc_id, wanted = parse_ref(publication.url)
    try:
        preview, inline = read(api, doc_id)
        document = select_tab(preview, wanted)
        doc, said = (warnings or warnings_of)(document, records)
        outcome.notes += said
        wrong = mismatch(publication, doc)
        if wrong:
            raise SuggestFailed(wrong)
        tab = str(document.get("tabId", ""))
        outcome.seen = read_units(document)
        notices = [notice for notice in doc.warnings if notice.marks]
        outcome.steps = plan(notices, outcome.seen, inline, tab)
        if apply:
            carry_out(api, doc_id, tab, outcome.steps, outcome.seen)
    except (SuggestFailed, LookupError, ValueError) as e:
        outcome.error = str(e)
    return outcome


def _quoted(text: str, width: int = 40) -> str:
    text = " ".join(text.replace(PLACEHOLDER, " ").split())
    return f"“{text if len(text) <= width else text[: width - 1] + '…'}”"


def describe(step: Step, seen: dict[str | None, Units]) -> str:
    """One step as a line of the run's account of itself: what, on what text, and why."""
    line = f"{step.thing} {step.key}"
    if step.mark is not None and step.verb in (Verb.CREATE, Verb.SKIP):
        where = step.mark.location
        units = seen.get(where.segment_id)
        if units is not None:
            on = _quoted(units.text(where.start, where.end)) if not where.empty else "a point"
            line += f" on {on}" + (" in a footnote" if where.segment_id else "")
        if step.thing is Thing.SUGGESTION and units is not None:
            line += ", " + "; ".join(_edit_said(edit, seen) for edit in step.mark.fix)
    if step.why:
        line += f": {step.why}"
    if step.made:
        line += f" ({step.made})"
    return line


def _edit_said(edit: Edit, seen: dict[str | None, Units]) -> str:
    where = edit.location
    units = seen.get(where.segment_id)
    old = units.text(where.start, where.end) if units is not None else ""
    match edit:
        case Replace(text=text):
            if not old:
                return f"insert {_quoted(text)}"
            return f"{_quoted(old)} to {_quoted(text)}" if text else f"delete {_quoted(old)}"
        case Underline(underline=underline):
            return f"{'underline' if underline else 'take the underline off'} {_quoted(old)}"
        case Link(url=url):
            return f"link {_quoted(old)} to {url}"
        case ParagraphStyle(style=named):
            return f"make the paragraph {named}"


def write(outcome: Outcome, apply: bool, log: Console) -> None:
    """What was done to one publication's document, or would be."""
    heading = Text(outcome.publication.name or outcome.publication.url, style="bold")
    if outcome.publication.tab:
        heading.append(f", tab {outcome.publication.tab}")
    console.write(heading, log)
    for note in outcome.notes:
        console.write(console.note("{}", note), log)
    kept = Counter(step.thing for step in outcome.steps if step.verb is Verb.KEEP)
    for step in outcome.steps:
        if step.verb is Verb.KEEP:
            continue
        if not apply or step.verb is Verb.SKIP:
            verb = DONE[step.verb] if step.verb is Verb.SKIP else f"would {step.verb}"
        else:
            verb = DONE[step.verb] if step.done else f"not {DONE[step.verb]}"
        line = Text("  ")
        line.append(f"{verb:<20}", style="yellow" if step.verb is Verb.SKIP else "")
        line.append(describe(step, outcome.seen))
        console.write(line, log)
    if kept:
        said = ", ".join(
            f"{count} {thing}{'' if count == 1 else 's'}" for thing, count in sorted(kept.items())
        )
        console.write(Text(f"  {'unchanged':<20}{said}", style="dim"), log)
    if outcome.error:
        console.write(Text(f"  failed: {outcome.error}", style="bold red"), log)


def tally(outcomes: Sequence[Outcome], apply: bool) -> Text:
    """The run in a line: how many of each thing it did, or would do, over every document."""
    settled = (Verb.KEEP, Verb.SKIP)
    steps = [step for outcome in outcomes for step in outcome.steps]
    counts = Counter(step.verb for step in steps if not apply or step.done or step.verb in settled)
    failed = sum(1 for outcome in outcomes if outcome.error)
    parts = []
    for verb in Verb:
        if counts[verb]:
            done = DONE[verb] if apply or verb in settled else f"to {verb}"
            parts.append(f"{counts[verb]} {done}")
    undone = sum(1 for step in steps if apply and not step.done and step.verb not in settled)
    if undone:
        parts.append(f"{undone} not done")
    if failed:
        parts.append(f"{failed} failed")
    line = Text(" · ".join(parts) if parts else "nothing to do", style="bold red" if failed else "")
    if not apply:
        line.append("; nothing written: `--apply` writes it", style="dim")
    return line
