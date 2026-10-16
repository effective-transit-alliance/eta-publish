"""Build a `Document` tree from Google Docs API JSON.

The only module that knows the shape of the Docs API;
everything downstream sees the tree in `nodes.py`.

Several pieces of ETA house style are recognized here rather than in the emitters,
because they are facts about how the docs are written:

- a leading `Header` section carrying `Key: value` front matter
- the report headline living in the body as a `Title`-styled paragraph,
  since the Drive filename is a working name (`SAS West Feasibility Response`)
  and not what gets published
- a figure's `Source:` line between the image and its caption,
  with the caption and `Credit:` lines after that
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .docs_json import JsonObject
from .naming import (
    AnchorAllocator,
    image_filename,
    image_filenames,
    names_nothing,
    url_filename,
)
from .nodes import (
    Block,
    Crop,
    Document,
    Embed,
    Figure,
    Footnote,
    FootnoteRef,
    Heading,
    Image,
    Inline,
    LineBreak,
    List,
    Listed,
    ListItem,
    ListKind,
    Paragraph,
    Platform,
    Shown,
    Table,
    Text,
    Vector,
    document_url,
    plain_text,
    unwrap_snapshot,
)

HEADING_LEVELS = {
    "HEADING_1": 2,
    "HEADING_2": 3,
    "HEADING_3": 4,
    "HEADING_4": 5,
    "HEADING_5": 6,
    "HEADING_6": 6,
}

# Carry no content of their own, so dropping them loses nothing.
IGNORED_ELEMENTS = frozenset({"pageBreak", "columnBreak", "horizontalRule", "equation"})

# Ids the emitters generate for themselves, which no heading may take.
RESERVED_ANCHORS = frozenset({"footnotes", "contributors"})

# Docs writes a Shift+Enter line break as a vertical tab inside the run,
# a teletype control character for advancing the paper without returning the carriage.
# Nothing has used it for that in fifty years,
# and Docs uses it because its own model is the one it inherited:
# a paragraph is a run of text, so a break inside one cannot be structure
# and has to be a character, and the character set has exactly one spare.
SOFT_BREAK = "\v"


REQUIRED_FIELDS = (
    "Project Manager",
    "SME/Liaison",
    "Phase",
    "Discussion Channel",
    "Publish Due Date",
    "Goals",
    "Audience",
    "Public Contributors",
    "Private Contributors",
    "URL",
    "Short",
    "SEO Description",
    "Social Title Card",
)
"""Every field the `Header` section must carry, in the order it writes them.

Spelled as the document spells them, because the spelling is the name:
a key is recorded exactly as typed, so `Url:` is not `URL:`
but an unrecognized field, and says so.
That is the point of checking at all,
since a misspelled field is silently missing everywhere it is read.

A missing one is warned about by name rather than as a list of twelve,
because a warning naming one line is a line to go and add
and a warning naming twelve is a paragraph nobody reads twice.
"""

# Fields the header may carry and nothing requires.
# The three due dates are the schedule the editors keep;
# nothing publishes them, and a report that has shipped no longer needs them.
# `Title` is a second answer to a question the headline already answers,
# which `title` warns about separately.
OPTIONAL_FIELDS = (
    "Draft Due Date",
    "Press Due Date",
    "Final Due Date",
    "Title",
)

SOCIAL_CARD = "Social Title Card"
"""The header field naming the share card, with the picture itself on the line under it.

What Squarespace calls the page's social image: what a link to the report unfurls as.
The value is the file's name, linked to the file; the picture is what publishes."""

RETIRED_FIELDS = frozenset({"Excerpt"})
"""Fields older reports carry that nothing reads any more.

`Excerpt:` was a blog post's summary for a while, which is what `Short:` is again.
Said apart from an unknown field, which is likelier a typo to fix than a line to delete.
"""

KNOWN_FIELDS = frozenset(REQUIRED_FIELDS) | frozenset(OPTIONAL_FIELDS)
"""Every field name the header is allowed to use.

A key outside this is kept and warned about rather than dropped:
the likeliest reason for one is a misspelling,
and a misspelled `SEO Description:` is a report that publishes with no description at all
and says nothing about why.
"""

# Anything still marked unfinished, e.g. the real doc's `Source: TODO`.
# Not `TK`: these reports are not written with it,
# so here it would only ever match a word that happened to be spelled that way.
UNFINISHED = frozenset({"TODO", "FIXME", "XXX"})


def _words(text: str) -> Iterator[str]:
    """`text` split into words, the way a word boundary divides one.

    A word is letters, digits, and underscores;
    everything else separates, so `Source: TODO` and `TODO,` each carry one
    and `TODOS` carries none of them.
    """
    word: list[str] = []
    for character in text:
        if character.isalnum() or character == "_":
            word.append(character)
            continue
        if word:
            yield "".join(word)
            word = []
    if word:
        yield "".join(word)


def unfinished(text: str) -> bool:
    """Whether `text` still carries a marker saying it is not done."""
    return any(word in UNFINISHED for word in _words(text))


VIDEO_LABEL = "video"
GRAPHIC_WARNING = "graphic warning"
COPY = "copy"

# What each label may be modified by, in parentheses after it:
# `Video (Graphic Warning):`. A label missing here takes none.
LABEL_MODIFIERS: dict[str, frozenset[str]] = {
    VIDEO_LABEL: frozenset({GRAPHIC_WARNING, COPY}),
}


def is_video_note(line: list[Inline]) -> bool:
    """Whether `line` is a `Video:` line, which embeds the link after it.

    Labelled like `Credit:`, underlined and ended by a colon, because a link
    on its own line is not enough to go on: SAS West credits two stills with
    a `Credit: MTA` linked whole to the video each was taken from, and a link
    pasted on a line of its own is as often a citation nobody gave words to.

    A `Video (Graphic Warning):` line is one too, for a video the reader is
    warned about before playing it.
    """
    note = labelled(line)
    return note.underlined and note.mark == ":" and note.label.casefold() == VIDEO_LABEL


def is_graphic_video_note(line: list[Inline]) -> bool:
    """Whether `line` is a `Video (Graphic Warning):` line."""
    return is_video_note(line) and GRAPHIC_WARNING in labelled(line).modified_by()


def is_copied_video_note(line: list[Inline]) -> bool:
    """Whether `line` is a `Video (Copy):` line, whose video the site serves itself."""
    return is_video_note(line) and COPY in labelled(line).modified_by()


def after_label(line: list[Inline]) -> list[Inline]:
    """What follows a label's colon, as the runs it was written in."""
    for i, node in enumerate(line):
        if isinstance(node, Text) and ":" in node.text:
            rest = node.text.partition(":")[2]
            return ([replace(node, text=rest)] if rest else []) + line[i + 1 :]
    return []


TRAILING = re.compile(r"[\s.,;:!?]*")
"""What may follow a `Video:` line's link without being part of it: a full stop, say."""


def without_trailing(inlines: list[Inline]) -> list[Inline]:
    """`inlines` without the unlinked punctuation at their end.

    A `Video:` line ended with a full stop, as a caption is, is still a line
    naming one video. The stop stays in what the caption says.
    """
    end = len(inlines)
    while end:
        last = inlines[end - 1]
        if not isinstance(last, Text) or last.href or not TRAILING.fullmatch(last.text):
            break
        end -= 1
    return inlines[:end]


def embed_of(inlines: list[Inline]) -> Embed | None:
    """The embed a `Video:` line names, if it names nothing but one link to a video or a post.

    Nothing but: every run with text in it carries the same link, and nothing
    else is there.
    """
    inlines = without_trailing(inlines)
    hrefs = {i.href for i in inlines if isinstance(i, Text) and i.text.strip()}
    if len(hrefs) != 1 or any(not isinstance(i, Text) for i in inlines):
        return None
    href = hrefs.pop()
    if href is None:
        return None
    found = embedded(href)
    if found is None:
        return None
    platform, key, start = found
    vertical = platform is Platform.YOUTUBE and urlsplit(href).path.startswith("/shorts/")
    return Embed(url=href, platform=platform, key=key, start=start, vertical=vertical)


YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
X_HOSTS = frozenset({"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"})


def embedded(href: str) -> tuple[Platform, str, int] | None:
    """What `href` is a link to, if it is a video or a post this can embed.

    The platform, its own name for the thing, and for YouTube where to start.
    Everything else about the URL is ignored: `?si=` tracking, `/video/1` on a
    post, a `?usp=` on a Drive link.
    """
    parts = urlsplit(href)
    host = (parts.hostname or "").lower()
    path = [segment for segment in parts.path.split("/") if segment]
    query = parse_qs(parts.query)
    if host in YOUTUBE_HOSTS or host == "youtu.be":
        if host == "youtu.be" and path:
            video = path[0]
        elif path == ["watch"]:
            video = query.get("v", [""])[0]
        elif len(path) >= 2 and path[0] in ("live", "shorts", "embed"):
            video = path[1]
        else:
            return None
        if not video:
            return None
        return Platform.YOUTUBE, video, _seconds((query.get("t") or query.get("start") or [""])[0])
    if host in X_HOSTS and len(path) >= 3 and path[1] == "status" and path[2].isdigit():
        return Platform.X, path[2], 0
    if host == "bsky.app" and len(path) >= 4 and path[0] == "profile" and path[2] == "post":
        return Platform.BLUESKY, f"{path[1]}/{path[3]}", 0
    if host == "drive.google.com" and len(path) >= 3 and path[:2] == ["file", "d"]:
        return Platform.DRIVE, path[2], 0
    return None


def _seconds(t: str) -> int:
    """A YouTube `t=` as seconds: `911`, `911s`, or `15m11s`."""
    total = 0
    number = ""
    for character in t:
        if character.isdigit():
            number += character
            continue
        unit = {"h": 3600, "m": 60, "s": 1}.get(character)
        if unit is None or not number:
            return 0
        total += int(number) * unit
        number = ""
    return total + int(number or 0)


def bold_brackets(inlines: list[Inline]) -> list[str]:
    """Every `[...]` in `inlines` whose text is bold, brackets included.

    A bold note in brackets is a placeholder for whoever comes back to it,
    as unfinished as a `TODO`. Whether the brackets themselves are bold does not matter;
    whether everything between them is does, so a bracketed aside with one
    bold word in it is still prose.
    """
    characters: list[tuple[str, bool]] = [
        (character, run.bold) for run in inlines if isinstance(run, Text) for character in run.text
    ]
    found: list[str] = []
    opened: int | None = None
    for i, (character, _) in enumerate(characters):
        if character == "[":
            opened = i
        elif character == "]" and opened is not None:
            inside = characters[opened + 1 : i]
            if any(not c.isspace() for c, _ in inside) and all(
                bold or c.isspace() for c, bold in inside
            ):
                found.append("".join(c for c, _ in characters[opened : i + 1]))
            opened = None
    return found


def _is_word(text: str) -> bool:
    """Whether `text` is a single word, by the same rule `_words` splits on."""
    return bool(text) and all(c.isalnum() or c == "_" for c in text)


# Editorial notes naming where an image came from, none of which is published.
# The real report uses four spellings:
# `Source:` under an image, `Uncropped Source:` for one that was trimmed,
# and, after a caption,
# either `[Image Source](<url>)` or a bare `Image Source` whose whole text is the link.
# One optional qualifying word covers all of them and whatever the next one is.
SOURCE_LABEL = "source"

# The same idea for chart assets: `SVG:` and `PNG:` name the file to link beside a figure.
# Notes to whoever assembles the page; the published report carries real links.
ASSET_LABELS = frozenset({"svg", "png", "pdf"})

CREDIT_LABEL = "credit"

# What ends a label: a colon where the line was typed,
# a bracket where the label is the text of a link.
LABEL_MARKS = ":]"


@dataclass(frozen=True)
class Labelled:
    """A line read as the label it is headed with and what follows.

    The one shape behind both kinds of labelled line these documents write:
    a header's `SEO Description: Cheaper, shallower, faster.`
    and a figure's `Uncropped Source: sas-west-036.jpg`
    differ in which labels they allow and how they are spelled,
    not in where the label ends.
    """

    label: str
    """As written, without its modifiers. Header fields are case-sensitive
    and figure notes are not, so the casefolding is the caller's to do."""

    modifiers: tuple[str, ...]
    """What the label is qualified by, as written: the comma-separated
    `Graphic Warning` of `Video (Graphic Warning):`."""

    mark: str
    """`:` where the line was typed, `]` where the label is the text of a link,
    and empty where the line is all label, which only a bare note may be."""

    value: str
    """What follows the mark, with the space after it dropped."""

    bracketed: bool
    """Whether the label opened with `[`, which only a linked note does."""

    underlined: bool
    """Whether the label is underlined for its whole length.

    This is what tells a label from prose that happens to hold a colon.
    Nothing else does: `The answer was simple: build it shallower`
    reads as a label by every rule about capitals and length,
    and reads as the sentence it is by this one."""

    linked: bool
    """Whether the label is the text of a link, for its whole length.

    A figure names its source by linking the file, and Docs underlines
    every link whatever the writer meant, so `parse.py` drops that underline
    and the link stands in for it. A header field is never written this way,
    which is why the two are separate: the `https` of a bare linked URL
    is not a field name.
    """

    bled: bool
    """Whether the underline ran past the mark into the value.

    Docs carries a style forward as the writer keeps typing,
    so a label underlined and a value underlined with it is the one
    mistake this convention invites. The line is still the label it looks like;
    the underline is what needs fixing, and the warning says so."""

    def modified_by(self) -> frozenset[str]:
        """The modifiers, casefolded, since they are matched like figure notes."""
        return frozenset(modifier.casefold() for modifier in self.modifiers)

    def unknown_modifiers(self) -> list[str]:
        """The modifiers this label does not take, as written."""
        allowed = LABEL_MODIFIERS.get(self.label.casefold(), frozenset())
        return [modifier for modifier in self.modifiers if modifier.casefold() not in allowed]


def _modified(label: str) -> tuple[str, tuple[str, ...]]:
    """`label` split from the parenthesized modifiers it ends with, if any.

    `Label (Modifier 1, Modifier 2)` is `Label` modified by both.
    """
    name, paren, rest = label.partition("(")
    if not paren or not rest.endswith(")"):
        return label, ()
    modifiers = tuple(m.strip() for m in rest.removesuffix(")").split(",") if m.strip())
    return name.strip(), modifiers


@dataclass(frozen=True)
class Marked:
    """One character of a line, and the two things about how it is written.

    Underlining is what says a label, and a link is underlined by Docs
    whatever the writer meant, which is why the two are kept apart:
    `parse.py` already drops the underline from a linked run for that reason.
    """

    character: str
    underlined: bool
    linked: bool


def _marked(content: list[Inline]) -> list[Marked]:
    """Each character of a line, with how it is written."""
    out: list[Marked] = []
    for node in content:
        if isinstance(node, Text):
            out.extend(
                Marked(character, node.underline, node.href is not None) for character in node.text
            )
    return out


def labelled(content: list[Inline]) -> Labelled:
    """`content` split at the end of the label it is headed with.

    An underlined `Uncropped Source` before `: a.jpg` is the label
    `Uncropped Source` with the mark `:`, and a linked `[Image Source]`
    is the label `Image Source` with the mark `]`.

    The opening bracket is optional for every label, not only the linked ones.
    Wider than the lines the reports actually write,
    deliberately: a bracketed `[SVG: ...]` is the note it looks like,
    and publishing it as prose because of the bracket helps nobody.
    """
    line = _marked(content)
    start = 0
    while start < len(line) and line[start].character.isspace():
        start += 1
    bracketed = start < len(line) and line[start].character == "["
    if bracketed:
        start += 1
        while start < len(line) and line[start].character.isspace():
            start += 1

    head = line[start:]
    end = next((i for i, m in enumerate(head) if m.character in LABEL_MARKS), None)
    label = head if end is None else head[:end]
    rest = [] if end is None else head[end + 1 :]
    name, modifiers = _modified(_text(label).strip())
    return Labelled(
        label=name,
        modifiers=modifiers,
        mark="" if end is None else head[end].character,
        value=_text(rest).lstrip(),
        bracketed=bracketed,
        underlined=_every(label, lambda m: m.underlined),
        linked=_every(label, lambda m: m.linked),
        bled=any(m.underlined and not m.linked for m in rest if not m.character.isspace()),
    )


def _text(run: list[Marked]) -> str:
    return "".join(m.character for m in run)


def _every(run: list[Marked], written: Callable[[Marked], bool]) -> bool:
    """Whether every character of `run` that is not a space is `written` that way.

    An empty run is not: a line with nothing before its colon has no label.
    """
    marks = [written(m) for m in run if not m.character.isspace()]
    return bool(marks) and all(marks)


def _written_as_a_label(note: Labelled) -> bool:
    """Whether a figure's note is written as one: underlined, or linked.

    A figure names its source by linking the file, and the link is the label.
    A header field is read more strictly, because a bare link to a page
    would otherwise make a field of the `https` its text starts with.
    """
    return note.underlined or note.linked


def unmarked(line: list[Inline]) -> list[Inline]:
    """A claimed label with the underline that marked it taken off.

    The underline says "this is a label" rather than anything to a reader,
    so publishing it puts a stray rule under the `Credit` of every figure.
    The same reason `_text_run` drops the underline Docs draws under a link.
    """
    return [
        replace(node, underline=False) if isinstance(node, Text) and node.underline else node
        for node in line
    ]


def is_source_note(line: list[Inline]) -> bool:
    """Whether `line` is a `Source:` note rather than prose.

    The bare spelling needs no mark, which is why the label has to be
    the whole of what precedes it:
    a paragraph beginning "Source of the estimate is ..." is prose,
    and only one saying nothing but "Image Source" is a note.
    """
    note = labelled(line)
    if not _written_as_a_label(note):
        return False
    words = note.label.casefold().split()
    if not words or words[-1] != SOURCE_LABEL:
        return False
    # The qualifier is one word: `Uncropped Source`, `Image Source`.
    # Anything else before the label is a sentence that happens to end in it.
    return len(words) == 1 or (len(words) == 2 and _is_word(words[0]))


def is_asset_note(line: list[Inline]) -> bool:
    """Whether `line` is a `SVG:`/`PNG:`/`PDF:` note.

    A colon and nothing else: these are typed, never linked,
    and a bare `PDF` is a word.
    """
    note = labelled(line)
    return _written_as_a_label(note) and note.mark == ":" and note.label.casefold() in ASSET_LABELS


CAPTION_LABEL = "caption"


def starts_with_label(line: list[Inline], label: str) -> bool:
    """Whether `line` begins `Label:`, however it is styled."""
    head, colon, _ = plain_text(line).lstrip().partition(":")
    return bool(colon) and head.strip().casefold() == label


def is_credit_note(line: list[Inline]) -> bool:
    """Whether `line` is a `Credit:` note. Never bare, for the same reason."""
    note = labelled(line)
    return _written_as_a_label(note) and bool(note.mark) and note.label.casefold() == CREDIT_LABEL


def key_line(line: list[Inline]) -> tuple[str, str] | None:
    """One `Key: value` line split in two, or `None` where the line is prose.

    The name is underlined and the colon ends it.
    That is the whole rule, and it is the document's rule rather than a guess
    about which runs of capitals read as a name:
    `Digging Out of a Very Deep Hole: Saving Billions on 125th Street`
    is a headline and `Barbara Russo-Lennon, "Subway spots` is a citation,
    and neither is underlined, which is all that has to be said about either.
    """
    field = labelled(line)
    # A colon and no bracket: `[Image Source]` is a figure's note, not a field.
    if not field.underlined or field.mark != ":" or field.bracketed:
        return None
    return field.label, field.value


def header_field(line: list[Inline]) -> str:
    """The header field `line` writes, or nothing where it writes none.

    The name only, without its value,
    so `SEO Description: ...` answers `SEO Description`.
    A line naming no recognized field answers nothing,
    which is what keeps a sentence holding a colon from being read as one.
    """
    found = key_line(line)
    if found is None:
        return ""
    key = found[0]
    return key if key in KNOWN_FIELDS else ""


# How much of a line a warning quotes back before it is just repeating the document.
CLIP = 60


def _clipped(line: str) -> str:
    """A line short enough to quote in a warning, cut on a word where it has to be."""
    if len(line) <= CLIP:
        return line
    return line[:CLIP].rsplit(" ", 1)[0] + "..."


def source_name(source: list[Inline]) -> str:
    """The file a `Source:` line names, or nothing if it names no file.

    The value after the colon:
    a Drive chip's title where the line links the file, plain text where it was typed.
    `Source: TODO` is a note rather than a name.
    A URL, typed after the colon or linked as `[Image Source](<url>)`,
    names the file at the end of its path, if it ends in one.
    """
    value = labelled(source).value.strip()
    if unfinished(value):
        return ""
    if value.startswith(("http:", "https:", "//")):
        return url_filename(value)
    if value:
        return value
    href = source_href(source)
    return url_filename(href) if href else ""


def source_href(source: list[Inline]) -> str:
    """Where a source line links, if it links anywhere."""
    return next((i.href for i in source if isinstance(i, Text) and i.href), "")


LIVE_OWNERS = frozenset({"effective-transit-alliance", "kkysen"})
"""The GitHub accounts whose files a `Source:` line is trusted to publish from."""


def github_raw(href: str) -> str:
    """The raw URL of the file `href` links in one of our GitHub repos, or nothing.

    A release asset is its own download link, `releases/download/<tag>/<file>`
    or `releases/latest/download/<file>`, so it is kept as it is.
    A link to a repo, a directory, a release page, or anyone else's repo
    is a citation, not the file.
    """
    split = urlsplit(href)
    parts = [unquote(p) for p in split.path.split("/") if p]
    host = split.netloc.lower()
    github = host in ("github.com", "www.github.com")
    if (
        github
        and len(parts) >= 5
        and parts[2] == "releases"
        and (
            (parts[3] == "download" and len(parts) >= 6)
            or (parts[3:5] == ["latest", "download"] and len(parts) >= 6)
        )
    ):
        if parts[0].lower() not in LIVE_OWNERS:
            return ""
        path = "/".join(quote(p) for p in parts)
        return f"https://github.com/{path}"
    if host == "raw.githubusercontent.com" and len(parts) >= 4:
        owner, repo, rest = parts[0], parts[1], parts[2:]
    elif github and len(parts) >= 5 and parts[2] in ("blob", "raw"):
        owner, repo, rest = parts[0], parts[1], parts[3:]
    else:
        return ""
    if owner.lower() not in LIVE_OWNERS:
        return ""
    path = "/".join(quote(p) for p in [owner, repo, *rest])
    return f"https://raw.githubusercontent.com/{path}"


def video_title(link: list[Inline]) -> str:
    """What a `Video:` line's link calls the video, or nothing.

    A link pasted bare reads as its own URL, which is no name for anything.
    """
    text = plain_text(link).strip()
    if text.startswith(("http:", "https:", "//")) or names_nothing(text):
        return ""
    return text


def date_text(chip: JsonObject) -> str:
    """A date smart chip as the document shows it, e.g. `Aug 19, 2026`."""
    stamp = chip.get("dateElementProperties", {}).get("timestamp", "")
    try:
        # Docs writes the `Z` form, which `fromisoformat` has read since 3.11.
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    # `%-d` avoids the zero padding Docs does not show.
    return moment.strftime("%b %-d, %Y")


def element_text(el: JsonObject) -> str:
    """The text an inline element contributes, smart chips included.

    Reading only `textRun` loses every chip.
    In the real report that emptied `Project Manager:` and all three date fields,
    and dropped the first name from `Public Contributors:`,
    leaving it starting with a comma.
    """
    if "textRun" in el:
        # A soft break is a line break, so it reads as one here too.
        return el["textRun"].get("content", "").replace(SOFT_BREAK, "\n")
    if "person" in el:
        props = el["person"].get("personProperties", {})
        return props.get("name") or props.get("email", "")
    if "dateElement" in el:
        return date_text(el["dateElement"])
    if "richLink" in el:
        return el["richLink"].get("richLinkProperties", {}).get("title", "")
    return ""


def strip_leading_space(blocks: list[Block]) -> list[Block]:
    """Drop the space Docs puts after a footnote's marker.

    It separates the marker from the text in the document
    rather than being part of what the note says,
    and left in it doubles the space after the number.
    """
    for block in blocks:
        if not isinstance(block, Paragraph) or not block.content:
            break
        first = block.content[0]
        if isinstance(first, Text):
            block.content[0] = replace(first, text=first.text.lstrip())
        break
    return blocks


def split_lines(content: list[Inline]) -> list[list[Inline]]:
    """Break inline content at soft line breaks."""
    lines: list[list[Inline]] = [[]]
    for node in content:
        if isinstance(node, LineBreak):
            lines.append([])
        else:
            lines[-1].append(node)
    return lines


def _normalized(text: str) -> str:
    """A section name as written, for matching a reference to it.

    Case and spacing vary between the heading and the sentence referring to it;
    anything more forgiving starts matching prose."""
    return " ".join(text.split()).casefold()


def plain(para: JsonObject) -> str:
    """The paragraph's text with styling dropped, for matching conventions."""
    return "".join(element_text(el) for el in para.get("elements", [])).strip()


def style_of(para: JsonObject) -> str:
    return para.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")


def has_image(para: JsonObject) -> bool:
    return any("inlineObjectElement" in el for el in para.get("elements", []))


class Parser:
    def __init__(self, doc_json: JsonObject) -> None:
        self.json = doc_json
        self.inline_objects: JsonObject = doc_json.get("inlineObjects", {})
        self.lists: JsonObject = doc_json.get("lists", {})
        self.footnote_defs: JsonObject = doc_json.get("footnotes", {})
        self.doc = Document()
        self.anchors = AnchorAllocator()
        self._heading_anchors: dict[str, str] = {}
        self._footnote_numbers: dict[str, int] = {}
        self._source_names: dict[str, str] = {}
        self._has_social_card = False
        """Whether a `Social Title Card:` field had its picture under it."""

    # ---- inline ------------------------------------------------------

    def inlines(self, para: JsonObject) -> list[Inline]:
        out: list[Inline] = []
        for el in para.get("elements", []):
            if "textRun" in el:
                out.extend(self._text_run(el["textRun"]))
            elif "footnoteReference" in el:
                out.append(self._footnote_ref(el["footnoteReference"]))
            elif "inlineObjectElement" in el:
                image = self._image(el["inlineObjectElement"])
                if image is not None:
                    out.append(image)
            elif "person" in el:
                out.append(self._person(el["person"]))
            elif "dateElement" in el:
                out.append(self._date(el["dateElement"]))
            elif "richLink" in el:
                out.append(self._rich_link(el["richLink"]))
            elif not (IGNORED_ELEMENTS & el.keys()):
                kinds = sorted(k for k in el if k not in ("startIndex", "endIndex"))
                self.doc.warn("unhandled document element {}, dropped", Shown(", ".join(kinds)))
        self._soft_breaks(para)
        # A soft break at either end is spacing rather than part of what the paragraph says,
        # and renders as a stray line break with nothing on one side of it.
        while out and isinstance(out[0], LineBreak):
            out.pop(0)
        while out and isinstance(out[-1], LineBreak):
            out.pop()
        return self.cross_references(out)

    def _soft_breaks(self, para: JsonObject) -> None:
        """Warn about a paragraph broken with Shift+Enter rather than Enter.

        Docs draws the two almost the same and stores them differently:
        Enter starts another paragraph, Shift+Enter writes a vertical tab
        inside this one. Nothing on the page says which is which,
        so nobody finds out until something reads the two lines as one,
        which is how this brief's `Short:` and `SEO Description:`
        went unpublished for sharing a paragraph.

        Both spellings still publish: the line break is emitted where it was written.
        The warning is that the document does not mean what it looks like it means.
        """
        text = "".join(el.get("textRun", {}).get("content", "") for el in para.get("elements", []))
        if SOFT_BREAK not in text:
            return
        lines = [line.strip() for line in text.strip().split(SOFT_BREAK)]
        written = [line for line in lines if line]
        if len(written) < 2:
            # Nothing on one side of it, so it is blank space rather than a break
            # between two things, and it is dropped rather than published.
            self.doc.warn(
                "a paragraph has a stray {} standing in for blank space; "
                "it is dropped, and a paragraph's spacing belongs in its style: {}",
                Shown("Shift+Enter"),
                Shown(_clipped(written[0]) if written else ""),
            )
            return
        self.doc.warn(
            "a paragraph is broken with {} rather than {}, "
            "so lines that look separate are one paragraph; give each line its own:{}",
            Shown("Shift+Enter"),
            Shown("Enter"),
            Listed(*((Shown(_clipped(line)),) for line in written)),
        )

    def cross_references(self, content: list[Inline]) -> list[Inline]:
        """Turn italicized section names into links to those sections.

        Google Docs cannot write a link to a heading in the same document,
        so ETA writes the section's name in italics and means a link by it.

        Matching is on the whole italic run, not on each styled piece of one,
        so a section name with a bold word in it still resolves.
        The italics come off: they stood in for the link, and now there is one.
        """
        if not self._heading_anchors:
            return content
        out: list[Inline] = []
        run: list[Text] = []

        def flush() -> None:
            anchor = self._heading_anchors.get(_normalized("".join(t.text for t in run)))
            if anchor is None:
                out.extend(run)
            else:
                out.extend(replace(t, italic=False, href=f"#{anchor}") for t in run)
            run.clear()

        for node in content:
            if isinstance(node, Text) and node.italic and node.href is None:
                run.append(node)
                continue
            flush()
            out.append(node)
        flush()
        return out

    def _person(self, chip: JsonObject) -> Text:
        """A person smart chip renders as the person's name.

        The chip also carries their email address:
        contact information the document happens to hold rather than something
        the report says, so it is not emitted.
        """
        props = chip.get("personProperties", {})
        return Text(text=props.get("name") or props.get("email", ""))

    def _date(self, chip: JsonObject) -> Text:
        """A date smart chip renders the way the document shows it."""
        text = date_text(chip)
        if not text:
            self.doc.warn("a date chip carries no timestamp; dropped")
        return Text(text=text)

    def _href(self, url: str | None) -> str | None:
        """A link as the tree holds it: the page it is of, not the capture of it.

        A `web.archive.org` URL typed into the document is a source already
        archived, so the wrapping comes off here and the capture it named is
        recorded as the one that source has. Doing it at the door means every
        output, the record, and the numbering all see one URL for one page,
        however the document happened to write it.
        """
        if url is None:
            return None
        original, archived = unwrap_snapshot(url)
        if archived is not None:
            # Keyed by the document, which is what was captured: one PDF cited
            # at fifteen of its pages is one entry in the record.
            self.doc.archives.setdefault(document_url(original), archived)
        return original

    def _rich_link(self, chip: JsonObject) -> Text:
        """A linked Drive file, which is how `Source:` lines name an asset."""
        props = chip.get("richLinkProperties", {})
        return Text(text=props.get("title", ""), href=self._href(props.get("uri")))

    def _text_run(self, run: JsonObject) -> list[Inline]:
        """One run, split at any soft line breaks it contains."""
        text = run.get("content", "")
        # A trailing newline is paragraph structure, not content.
        if text.endswith("\n"):
            text = text[:-1]
        if not text:
            return []
        style = run.get("textStyle", {})
        offset = style.get("baselineOffset")

        def styled(part: str) -> Text:
            return Text(
                text=part,
                bold=bool(style.get("bold")),
                italic=bool(style.get("italic")),
                underline=bool(style.get("underline")) and "link" not in style,
                sup=offset == "SUPERSCRIPT",
                sub=offset == "SUBSCRIPT",
                href=self._href(style.get("link", {}).get("url")),
            )

        out: list[Inline] = []
        for n, part in enumerate(text.split(SOFT_BREAK)):
            if n:
                out.append(LineBreak())
            if part:
                out.append(styled(part))
        return out

    def _footnote_ref(self, ref: JsonObject) -> FootnoteRef:
        fid = ref["footnoteId"]
        # Numbered in document order,
        # so a reference and its definition cannot disagree the way hand-written ones did.
        if fid not in self._footnote_numbers:
            self._footnote_numbers[fid] = len(self._footnote_numbers) + 1
        return FootnoteRef(footnote_id=fid, number=self._footnote_numbers[fid])

    def _image(self, ioe: JsonObject) -> Image | None:
        object_id = ioe.get("inlineObjectId", "")
        embedded = (
            self.inline_objects.get(object_id, {})
            .get("inlineObjectProperties", {})
            .get("embeddedObject", {})
        )
        if "imageProperties" not in embedded:
            self.doc.warn("inline object {} has no image; skipped", Shown(object_id))
            return None
        image_props = embedded["imageProperties"]
        # `contentUri` says where to fetch this image, not whether it is one:
        # a saved response has none, since they expire and are dropped rather
        # than committed, and everything but the download still works.
        uri = image_props.get("contentUri")
        crop = self._crop(object_id, image_props.get("cropProperties", {}))
        return Image(
            object_id=object_id,
            filename=image_filename(object_id, crop_key=crop.key),
            alt=embedded.get("description") or embedded.get("title") or "",
            source_uri=uri,
            crop=crop,
        )

    # Where a Drive link keeps the file id, in either shape Docs produces.
    DRIVE_PATH = "/file/d/"
    DRIVE_QUERY = "id"

    @classmethod
    def _drive_id(cls, uri: str) -> str:
        """The Drive file id a link names, or nothing where it names none."""
        split = urlsplit(uri)
        _, found, rest = split.path.partition(cls.DRIVE_PATH)
        if found:
            return rest.partition("/")[0]
        ids = parse_qs(split.query).get(cls.DRIVE_QUERY, [])
        return ids[0] if ids else ""

    def _vector(self, para: JsonObject) -> Vector | None:
        """The vector original a `SVG:` line links, if it links one.

        Any link counts: a Drive file, or a URL anywhere else.
        Whether it really is an SVG is settled when it is downloaded,
        except for a Drive chip, which says its type itself.
        `SVG: TODO` is a note, with nothing to publish for it.
        """
        for el in para.get("elements", []):
            props = el.get("richLink", {}).get("richLinkProperties", {})
            uri = props.get("uri", "")
            title = props.get("title", "")
            if uri and "image/svg" not in props.get("mimeType", ""):
                self.doc.warn(
                    "the {} line links {}, which is not an SVG; the raster is used",
                    Shown("SVG:"),
                    Shown(title or uri),
                )
                return None
            if not uri:
                run = el.get("textRun", {})
                uri = run.get("textStyle", {}).get("link", {}).get("url", "")
                title = run.get("content", "").strip()
            if not uri:
                continue
            if not title or title == uri:
                title = unquote(urlsplit(uri).path.rpartition("/")[2])
            file_id = self._drive_id(uri)
            return Vector(
                file_id=file_id,
                # The linked file's name names the picture,
                # the same as a `Source:` line does.
                # No crop key: the crop is applied to pixels.
                filename=image_filename(file_id or uri, extension=".svg", name=title),
                title=title,
                uri=uri,
            )
        return None

    def _crop(self, object_id: str, props: JsonObject) -> Crop:
        """How much of the image the document trims from each side.

        Docs stores tiny negative offsets for an edge that is not trimmed,
        so the values are clamped rather than trusted.
        """
        if props.get("angle"):
            self.doc.warn(
                "image {} is rotated in the document; the rotation is not applied",
                Shown(object_id),
            )

        def side(name: str) -> float:
            return max(0.0, min(1.0, float(props.get(name, 0.0) or 0.0)))

        return Crop(
            left=side("offsetLeft"),
            right=side("offsetRight"),
            top=side("offsetTop"),
            bottom=side("offsetBottom"),
        )

    # ---- lists -------------------------------------------------------

    def _list_kind(self, list_id: str, level: int) -> ListKind:
        levels = self.lists.get(list_id, {}).get("listProperties", {}).get("nestingLevels", [])
        glyph = levels[level] if level < len(levels) else {}
        numbered = glyph.get("glyphType") not in (None, "GLYPH_TYPE_UNSPECIFIED")
        return ListKind.NUMBER if numbered else ListKind.BULLET

    def _consume_list(self, content: list[JsonObject], start: int) -> tuple[List, int]:
        """Absorb the run of consecutive bulleted paragraphs starting at `start`.

        Docs gives each paragraph a flat `nestingLevel` rather than nesting them,
        so the tree is rebuilt here with a stack of sibling lists.
        """
        list_id = content[start]["paragraph"]["bullet"].get("listId", "")
        root: list[ListItem] = []
        stack: list[list[ListItem]] = [root]

        i = start
        while i < len(content):
            para = content[i].get("paragraph")
            if para is None or "bullet" not in para:
                break
            if para["bullet"].get("listId", "") != list_id:
                break

            level = para["bullet"].get("nestingLevel", 0)
            while len(stack) > level + 1:
                stack.pop()
            while len(stack) < level + 1:
                siblings = stack[-1]
                if not siblings:
                    # Docs permits an indented item with no item above it.
                    siblings.append(ListItem())
                stack.append(siblings[-1].children)
            stack[-1].append(ListItem(content=self.inlines(para)))
            i += 1

        return List(kind=self._list_kind(list_id, 0), items=root), i

    # ---- blocks ------------------------------------------------------

    def blocks(self, content: list[JsonObject]) -> list[Block]:
        out: list[Block] = []
        pending_source: list[Inline] | None = None
        # 1 while the paragraph directly after a figure is still unclaimed.
        caption_slot = 0

        def drop_pending() -> None:
            nonlocal pending_source
            if pending_source is not None:
                text = plain_text(pending_source)
                self.doc.warn(
                    "{} line not followed by an image, dropped: {}",
                    Shown("Source:"),
                    Shown(text[:80]),
                )
                pending_source = None

        i = 0
        while i < len(content):
            item = content[i]

            if "table" in item:
                drop_pending()
                caption_slot = 0
                out.append(self.table(item["table"]))
                i += 1
                continue

            para = item.get("paragraph")
            if para is None:
                i += 1
                continue

            if "bullet" in para:
                drop_pending()
                caption_slot = 0
                node, i = self._consume_list(content, i)
                out.append(node)
                continue

            i += 1
            style = style_of(para)
            text = plain(para)

            if not text and not has_image(para):
                caption_slot = 0
                continue

            if style in HEADING_LEVELS and not text and has_image(para):
                # An image inserted while a heading style was still active.
                # Treating it as a heading yields an empty one
                # whose anchor is a published URL, and buries the image inside it.
                self.doc.warn(
                    "an image is styled as a {}; treating it as a figure. "
                    "Set that paragraph to {} in the doc.",
                    Shown("Heading"),
                    Shown("Normal text"),
                )
                style = "NORMAL_TEXT"

            if style in HEADING_LEVELS:
                drop_pending()
                caption_slot = 0
                out.append(
                    Heading(
                        level=HEADING_LEVELS[style],
                        anchor=self.anchors.allocate(text),
                        content=self.inlines(para),
                    )
                )
                continue

            if unfinished(text):
                self.doc.warn("unfinished text in the document: {}", Shown(text[:80]))

            # Read once, here: what a line is depends on how it is styled,
            # and parsing a paragraph twice says everything it has to say twice.
            inlines = self.inlines(para)

            for placeholder in bold_brackets(inlines):
                self.doc.warn("unfinished text in the document: {}", Shown(placeholder[:80]))

            if is_source_note(inlines) or is_asset_note(inlines):
                self._check_label(inlines)
                last = out[-1] if out else None
                if isinstance(last, Figure):
                    # A source line after a figure sits between the image and
                    # its caption, so it belongs to the figure above it.
                    note = unmarked(inlines)
                    last.source = last.source + note
                    self._claim_name(last, note)
                    if is_asset_note(inlines) and starts_with_label(inlines, "svg"):
                        self._attach_vector(last, para)
                    continue
                drop_pending()
                pending_source = unmarked(inlines)
                caption_slot = 0
                continue

            if is_video_note(inlines):
                self._check_label(inlines)
                embed = embed_of(after_label(inlines))
                if embed is None:
                    self.doc.warn(
                        "a {} line has to be followed by one link to a YouTube video, "
                        "an X or Bluesky post, or a video in Drive; publishing it as text: {}",
                        Shown("Video:"),
                        Shown(text[:80]),
                    )
                    out.append(Paragraph(content=unmarked(inlines)))
                    continue
                embed.graphic = is_graphic_video_note(inlines)
                embed.copy = is_copied_video_note(inlines)
                embed.title = video_title(after_label(inlines))
                embed.name = video_title(
                    [i for i in after_label(inlines) if isinstance(i, Text) and i.href]
                )
                drop_pending()
                caption_slot = 0
                out.append(embed)
                continue

            if has_image(para):
                figure = Figure(image=self._only_image(inlines), source=pending_source or [])
                self._claim_name(figure, pending_source or [])
                out.append(figure)
                pending_source = None
                caption_slot = 1
                continue

            # A caption is the one paragraph directly after a figure,
            # and before its `Credit:` line, which closes the caption's slot;
            # `Credit:` and `Source:` lines keep attaching after that.
            # Matching on length would swallow short body paragraphs,
            # and a report with 50-odd figures has a great many.
            last = out[-1] if out else None
            if isinstance(last, Embed) and not last.credit and is_credit_note(inlines):
                # Credited the way a figure is, by the line right under it.
                self._check_label(inlines)
                last.credit = unmarked(inlines)
                continue
            if isinstance(last, Figure):
                # A caption and its credit are often one paragraph split by a soft line break,
                # so each line is classified separately.
                claimed = False
                for line in split_lines(inlines):
                    if not plain_text(line).strip():
                        continue
                    if is_credit_note(line):
                        self._check_label(line)
                        last.credit = unmarked(line)
                        caption_slot = 0
                        claimed = True
                    elif is_source_note(line) or is_asset_note(line):
                        self._check_label(line)
                        last.source = last.source + unmarked(line)
                        self._claim_name(last, line)
                        claimed = True
                    elif caption_slot:
                        if starts_with_label(line, CAPTION_LABEL):
                            # Nothing reads a `Caption:` label, so the word is
                            # published as the first of the caption.
                            self.doc.warn(
                                "the caption of image {} starts with {}, which is published "
                                "as part of it; take it out in the doc",
                                Shown(last.image.filename),
                                Shown("Caption:"),
                            )
                        last.caption = line
                        caption_slot = 0
                        claimed = True
                if claimed:
                    continue

            caption_slot = 0
            out.append(Paragraph(content=inlines))

        drop_pending()
        for block in out:
            if isinstance(block, Figure) and not block.image.alt and block.caption:
                # The published page uses the caption as alt text as well as showing it,
                # so an image with no description in Docs is not left unlabelled.
                caption = plain_text(block.caption)
                block.image = replace(block.image, alt=caption.strip())
        return out

    def _claim_name(self, figure: Figure, source: list[Inline]) -> None:
        """Note what a source line calls this figure's image, if it calls it anything.

        Kept until the whole document has been read rather than applied here:
        what an image ends up called
        depends on whether another one further down names the same file.

        The first line to name a file wins, so a figure with both a `Source:`
        and an `Image Source` link takes its name from the `Source:`,
        and from the link only where the `Source:` names nothing.
        """
        if labelled(source).label.casefold().split() == ["image", SOURCE_LABEL]:
            # One label in one place: `Source:` above the image takes a URL too.
            self.doc.warn(
                "write {} as a {} line above the image instead; it takes a URL as well: {}",
                Shown("Image Source"),
                Shown("Source:"),
                Shown(source_href(source) or plain_text(source).strip()[:80]),
            )
        name = source_name(source)
        if name:
            self._source_names.setdefault(figure.image.object_id, name)
        live = github_raw(source_href(source))
        if live and not figure.image.live_uri and figure.image.vector is None:
            if live.lower().endswith(".svg"):
                # Exactly what an `SVG:` line linking the same file would be.
                title = url_filename(live)
                figure.image = replace(
                    figure.image,
                    vector=Vector(
                        file_id="",
                        filename=image_filename(
                            live,
                            extension=".svg",
                            crop_key=figure.image.crop.key if figure.image.crop.trims else "",
                            name=title,
                        ),
                        title=title,
                        uri=live,
                    ),
                )
            else:
                figure.image = replace(figure.image, live_uri=live)

    def _attach_vector(self, figure: Figure, para: JsonObject) -> None:
        """Promote a `SVG:` line's link from a note to the figure's file."""
        vector = self._vector(para)
        if vector is None:
            return
        crop = figure.image.crop
        if crop.trims:
            # Named for the crop as well, as a cropped raster is:
            # recropping it in the doc publishes a different picture.
            vector = replace(
                vector,
                filename=image_filename(
                    vector.file_id or vector.uri,
                    extension=".svg",
                    crop_key=crop.key,
                    name=vector.title,
                ),
            )
        figure.image = replace(figure.image, vector=vector)

    def _only_image(self, inlines: list[Inline]) -> Image:
        images = [i for i in inlines if isinstance(i, Image)]
        if len(images) > 1:
            self.doc.warn(
                f"{len(images)} images share one paragraph; only the first becomes a figure"
            )
        prose = plain_text(inlines).strip()
        if prose:
            self.doc.warn(
                "text sharing a paragraph with an image was dropped: {}", Shown(prose[:80])
            )
        return images[0]

    def table(self, table: JsonObject) -> Table:
        return Table(
            rows=[
                [self.blocks(cell.get("content", [])) for cell in row.get("tableCells", [])]
                for row in table.get("tableRows", [])
            ]
        )

    # ---- document ----------------------------------------------------

    def _split_at_title(
        self, content: list[JsonObject]
    ) -> tuple[list[JsonObject], list[JsonObject]]:
        """What sits above the headline, and the report itself below it.

        A document with no headline has nothing above it: everything is the report.
        """
        for i, item in enumerate(content):
            if "paragraph" in item and style_of(item["paragraph"]) == "TITLE":
                return content[:i], content[i + 1 :]
        return [], content

    def subtitle(self, below: list[JsonObject]) -> list[JsonObject]:
        """Take the `Subtitle`-styled paragraph directly under the headline,
        and return the report without it.

        Only there: it is the style that shows,
        and a subtitle anywhere else is not one a reader sees under the headline.
        Blank lines between the two are skipped, as the document shows them as nothing.
        """
        for i, item in enumerate(below):
            para = item.get("paragraph")
            if para is None or "bullet" in para:
                break
            if style_of(para) == "SUBTITLE" and plain(para):
                self.doc.subtitle = self.inlines(para)
                return below[:i] + below[i + 1 :]
            if plain(para) or has_image(para):
                break
        return below

    def card(self, above: list[JsonObject]) -> Image | None:
        """The share card, which is an image the document puts above the headline.

        ETA reports open with a wide image with the title set into it,
        for whatever is linking to the report to show as a thumbnail.
        It is metadata, publishing as `og:image` rather than as a figure,
        and recognized by position, since an image above the headline
        is not in the report.
        """
        for item in above:
            para = item.get("paragraph")
            if para is None:
                continue
            for el in para.get("elements", []):
                if "inlineObjectElement" not in el:
                    continue
                image = self._image(el["inlineObjectElement"])
                if image is not None:
                    return image
        return None

    def front_matter(self, content: list[JsonObject]) -> list[JsonObject]:
        """Consume the leading `Header` section into `doc.meta`.

        Front matter is the run of `Key: value` paragraphs following the `Header` heading.
        It ends at the first paragraph that is not one:
        a heading of any level, the `Title`-styled headline, or ordinary prose.
        A picture does not end it. It is kept for the body where it was, and the
        fields after it are still the header's.

        Not "until the next heading of the same or higher level".
        In the real doc `Header` is an `h2` while the body sections are `h1`,
        so that rule runs past the headline and the hero image to the first
        body section, and the image would vanish without a warning.

        Unrecognized keys are kept rather than ending the scan,
        so adding a header field to a future report cannot leak that line into the body.

        Anything before `Header` is production scaffolding rather than the report,
        and is dropped, one reported line at a time.
        A document with no `Header` at all is left untouched
        instead of being eaten a paragraph at a time.
        """
        start = self._header_index(content)
        if start is None:
            self.doc.warn(
                "no front matter found; expected a leading {} section with {}, {}, and {} lines",
                Shown("Header"),
                Shown("URL:"),
                Shown("SEO Description:"),
                Shown("Social Title Card:"),
            )
            return content

        self.doc.has_header = True

        for item in content[:start]:
            para = item.get("paragraph")
            text = plain(para) if para is not None else ""
            if text:
                self.doc.warn(
                    "dropped a line before the {} section: {}",
                    Shown("Header"),
                    Shown(text[:80]),
                )

        end = start + 1
        # Pictures the header section holds, which are the report's and not
        # the header's: stepped over rather than ending it, and handed back.
        pictures: list[int] = []
        # The field the last header line set, so the picture under a
        # `Social Title Card:` line is known to be the card rather than the report's.
        last_key = ""
        for i in range(start + 1, len(content)):
            para = content[i].get("paragraph")
            if para is None:
                break

            style = style_of(para)
            text = plain(para)

            if style == "TITLE" or HEADING_LEVELS.get(style) is not None:
                break

            if has_image(para) and not text and last_key == SOCIAL_CARD:
                self._social_card(para)
                end = i + 1
                continue

            if has_image(para) and not self._names_social_card(para):
                # Monthly Passes puts its picture in the `Header` section with a
                # `Description:` line after it. Ending the section at the picture
                # left that line in the body, warned about as a field somewhere
                # no field goes, when it is a header field nothing recognizes.
                pictures.append(i)
                continue

            if not text:
                end = i + 1
                continue

            # A paragraph can hold more than one field:
            # the real brief writes `Short:` and `SEO Description:`
            # with a Shift+Enter between them rather than a paragraph break.
            # The two read alike in the document and are not alike here,
            # so every line of the paragraph is considered, not just the first.
            lines = split_lines(self.inlines(para))
            if key_line(lines[0]) is None:
                break  # prose: the header section is over
            if pictures and (
                is_source_note(lines[0]) or is_asset_note(lines[0]) or is_credit_note(lines[0])
            ):
                # A `Credit:` or `Source:` under a picture is that picture's,
                # however much it reads like a field, so the header ends here
                # and the picture keeps its notes.
                break

            key = ""
            for line in lines:
                field = key_line(line)
                if field is None:
                    # A line that names no field continues the value above it.
                    # Ending the scan here would drop the rest of the paragraph,
                    # and every field after it, over a value that merely wrapped.
                    wrapped = plain_text(line).strip()
                    self.doc.meta[key] = f"{self.doc.meta[key]} {wrapped}".strip()
                    continue
                self._check_label(line)
                key = self._meta_line(*field)
            if key == SOCIAL_CARD and has_image(para):
                # The picture a Shift+Enter under the field rather than a paragraph.
                self._social_card(para)
            last_key = key
            end = i + 1

        if not self.doc.meta:
            self.doc.warn(
                "the {} section holds no {} lines; expected {}, {}, and {}",
                Shown("Header"),
                Shown("Key: value"),
                Shown("URL:"),
                Shown("SEO Description:"),
                Shown("Social Title Card:"),
            )
        return [content[i] for i in pictures if i < end] + content[end:]

    def _names_social_card(self, para: JsonObject) -> bool:
        """Whether `para` opens with the `Social Title Card:` field."""
        field = key_line(split_lines(self.inlines(para))[0])
        return field is not None and field[0] == SOCIAL_CARD

    def _social_card(self, para: JsonObject) -> None:
        """Take the picture in `para` as the share card."""
        for el in para.get("elements", []):
            if "inlineObjectElement" in el:
                image = self._image(el["inlineObjectElement"])
                if image is not None:
                    self.doc.card = image
                    self._has_social_card = True
                    # Named for the file the field links, as a figure is for its `Source:`.
                    name = self.doc.meta.get(SOCIAL_CARD, "")
                    self._source_names.setdefault(image.object_id, name)
                    return

    def _check_label(self, line: list[Inline]) -> None:
        """Warn about anything wrong with how a note's label is written."""
        self._bleed(line)
        self._modifiers(line)

    def _modifiers(self, line: list[Inline]) -> None:
        """Warn about a modifier its label does not take.

        Likeliest a misspelling, and a misspelled `Graphic Warning`
        publishes a graphic video with no warning at all.
        """
        note = labelled(line)
        for modifier in note.unknown_modifiers():
            self.doc.warn(
                "{} is not a modifier {} takes; ignoring it: {}",
                Shown(modifier),
                Shown(f"{note.label}:"),
                Shown(_clipped(plain_text(line).strip())),
            )

    def _bleed(self, line: list[Inline]) -> None:
        """Warn where the underline marking a label ran on into its value.

        Docs carries a style forward as the writer keeps typing,
        which is the one mistake this convention invites.
        The line still reads as the label it looks like:
        what is wrong is the underline, and the warning says so
        rather than quietly publishing a rule under half the caption.
        """
        note = labelled(line)
        if note.bled:
            self.doc.warn(
                "the underline on {} runs past it into the value; underline the name only: {}",
                Shown(f"{note.label}:"),
                Shown(_clipped(plain_text(line).strip())),
            )

    def _meta_line(self, key: str, value: str) -> str:
        """Record one `Key: value` header line, and answer which key it set."""
        value = value.strip()
        if key in RETIRED_FIELDS:
            self.doc.warn(
                "the {} line is no longer used; rename it {}",
                Shown(f"{key}:"),
                Shown("Short:"),
            )
        elif key not in KNOWN_FIELDS:
            # A field nothing reads is a field nobody notices is missing.
            # Worth a warning even though the value is kept,
            # because the likeliest reason for one is a misspelling,
            # and a misspelled `URL:` publishes nowhere at all.
            self.doc.warn(
                "the {} section has an unrecognized {} line; check it for a typo",
                Shown("Header"),
                Shown(f"{key}:"),
            )
        if key in self.doc.meta:
            # The later line wins, and says so: a corrected line pasted
            # below the original and a duplicate nobody meant look
            # identical, and neither is visible in what gets published.
            self.doc.warn(
                "the {} section has more than one {} line; using {} and ignoring {}",
                Shown("Header"),
                Shown(f"{key}:"),
                Shown(value),
                Shown(self.doc.meta[key]),
            )
        self.doc.meta[key] = value
        return key

    def _header_index(self, content: list[JsonObject]) -> int | None:
        """Where the `Header` heading is, if the report has one.

        Found before anything is consumed, so a document without one is left untouched.
        The search stops at the headline or the first figure,
        since past either the report has already started.
        """
        for i, item in enumerate(content):
            para = item.get("paragraph")
            if para is None:
                continue
            style = style_of(para)
            if HEADING_LEVELS.get(style) is not None and plain(para).strip().lower() == "header":
                return i
            if style == "TITLE" or has_image(para):
                return None
        return None

    def title(self, content: list[JsonObject]) -> str:
        """The headline, which is the `Title`-styled paragraph and only that.

        Not a `Title:` line in the `Header` section as well:
        the style is the one that shows, where a headline set in the header
        is one nobody reading the document sees at the top of it.

        The Drive filename is the last resort and a warning, not a third way:
        it is a working name, and the SAS West report lives in a doc called
        `SAS West Feasibility Response`.
        """
        for item in content:
            para = item.get("paragraph")
            if para is not None and style_of(para) == "TITLE" and plain(para):
                self.doc.headline = self.inlines(para)
                return plain(para)

        filename = self.json.get("title", "")
        self.doc.warn(
            "no {}-styled paragraph, so the document name {} is being used as the "
            "headline; style the headline as {} in the doc",
            Shown("Title"),
            Shown(filename),
            Shown("Title"),
        )
        if self.doc.meta.get("Title"):
            # Said separately, because it is a different thing to fix:
            # the headline is written down, in a line that does not set it.
            self.doc.warn(
                "the {} section has {}, which is not what the headline comes from; "
                "style that line as {} in the body instead",
                Shown("Header"),
                Shown(f"Title: {self.doc.meta['Title']}"),
                Shown("Title"),
            )
        return filename

    def footnotes(self) -> list[Footnote]:
        """Only footnotes the body actually references, in reference order.

        A definition with no reference cannot be numbered,
        so it is reported rather than emitted with a number that means nothing.
        """
        for fid in self.footnote_defs:
            if fid not in self._footnote_numbers:
                self.doc.warn("footnote {} is defined but never referenced; omitted", Shown(fid))
        return [
            Footnote(
                footnote_id=fid,
                number=number,
                content=strip_leading_space(
                    self.blocks(self.footnote_defs.get(fid, {}).get("content", []))
                ),
            )
            for number, fid in sorted(
                (number, fid) for fid, number in self._footnote_numbers.items()
            )
        ]

    def parse(self) -> Document:
        content: list[JsonObject] = self.json.get("body", {}).get("content", [])
        content = self.front_matter(content)
        self.doc.title = self.title(content)
        self.doc.file_title = self.json.get("title", "")
        self.doc.tab_title = self.json.get("tabTitle", "")
        read_review(self.doc, self.json)

        # Allocated knowing every heading up front,
        # so two headings that slugify alike keep their anchors when the document reorders.
        heading_texts = [
            plain(item["paragraph"])
            for item in content
            if "paragraph" in item and style_of(item["paragraph"]) in HEADING_LEVELS
        ]
        self.anchors = AnchorAllocator(heading_texts, reserved=RESERVED_ANCHORS)
        # Built before the body is walked,
        # because a section can be referred to from above itself:
        # the report links to `Station Depth` long before reaching it.
        self._heading_anchors = {}
        for text in heading_texts:
            if not text:
                continue
            anchor = self.anchors.allocate(text)
            self._heading_anchors.setdefault(_normalized(text), anchor)
            # The part before the colon names the section and the part after
            # describes it, so `Appendix A: Freedom Tunnel` is referred to as
            # `Appendix A`.
            name, colon, _ = text.partition(":")
            if colon and name.strip():
                self._heading_anchors.setdefault(_normalized(name), anchor)

        above, below = self._split_at_title(content)
        # A `Social Title Card:` names the card outright; a picture above the
        # headline is the older way of saying the same, and only stands in for one.
        if SOCIAL_CARD in self.doc.meta and not self._has_social_card:
            self.doc.warn(
                "the {} line has no picture under it; paste the card itself on the next line",
                Shown(f"{SOCIAL_CARD}:"),
            )
        if self.doc.card is None:
            self.doc.card = self.card(above)
        below = self.subtitle(below)
        if self.doc.subtitle and self.doc.title.rstrip().endswith(":"):
            # The headline set over two lines, the second as its subtitle:
            # what the page, the search result, and a link preview are called
            # is the whole of it, not the half that ends in a colon.
            self.doc.title = f"{self.doc.title.rstrip()} {plain_text(self.doc.subtitle).strip()}"
            self.doc.subtitle_ends_title = True
        self.doc.blocks = self.blocks(below)
        # After the body, so that every reference has been numbered.
        self.doc.footnotes = self.footnotes()
        # Last, because a name is only known to be unambiguous
        # once every image in the document has claimed one.
        self._name_images()
        return self.doc

    def _name_images(self) -> None:
        """Rename every figure the document named a source file for.

        Settled here rather than where the images are read,
        because an image's name depends on what the other images are called,
        and the report goes on naming them for several pages after the first is built.

        Only figures and the share card: a source line is written above a figure,
        and `Social Title Card:` names the card,
        so an image inside a paragraph keeps the name it was given.
        """
        names = image_filenames(
            (image.object_id, image.crop.key, self._source_names.get(image.object_id, ""))
            for image in self.doc.images
        )
        for figure in self.doc.figures:
            claimed = self._source_names.get(figure.image.object_id, "")
            figure.image = replace(
                figure.image,
                filename=names[figure.image.object_id],
                named=not names_nothing(claimed),
            )
        card = self.doc.card
        if card is not None and card.object_id in self._source_names:
            claimed = self._source_names[card.object_id]
            self.doc.card = replace(
                card, filename=names[card.object_id], named=not names_nothing(claimed)
            )


def read_review(doc: Document, document: JsonObject) -> None:
    """Tell `doc` what the fetch recorded about the editing still open on it.

    Its own function because it is read twice:
    once when the response is parsed,
    and again once a run that could not read it
    has carried the last answer over from the saved one.
    """
    doc.open_suggestions = int(document.get("openSuggestions", 0))
    doc.suggestions_accepted = document.get("suggestions") == "accepted"
    doc.open_comments = int(document.get("openComments", 0))


def parse(doc_json: JsonObject) -> Document:
    return Parser(doc_json).parse()
