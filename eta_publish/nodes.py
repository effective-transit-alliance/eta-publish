"""The document tree every emitter renders from.

The only intermediate representation:
the parser builds it, and each emitter walks it independently.
The HTML is not rendered from the Markdown,
which would lose the figure source/caption/credit distinction,
superscripts, and exact link targets,
and would create a second source of truth the moment anyone edited the `.md`.

It carries what ETA reports use, not what a Google Doc can express.
Anything the parser cannot place here becomes a warning rather than a silent drop.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from string import ascii_letters
from typing import override
from urllib.parse import urlsplit

# ---- inline content ------------------------------------------------


@dataclass(frozen=True)
class Archived:
    """Where a snapshot of one source lives, or why there is none.

    `snapshot` and `timestamp` are the capture; `error` is a capture that was
    tried and did not happen, which is a third state and not the absence of one.
    A source nothing has ever tried is simply missing from the record, and a
    later build submits it; one recorded here with an `error` is one a later
    build already knows the answer for, and so does not submit again and again
    forever. Some URLs cannot be archived at all: a page behind a login, and
    every `mp.weixin.qq.com` link the reports cite.
    """

    snapshot: str = ""
    timestamp: str = ""
    """When the snapshot was taken, as the 14 digits Wayback writes, or the
    date the attempt failed."""
    error: str = ""
    pending: bool = False
    """Whether `error` is about the moment rather than the source: the archive
    was busy, refused for now, or is still capturing it. Published as not
    archived like any failure, and asked about again by the next build that can.
    Recorded rather than left missing, so an offline build publishes the same."""

    said: str = ""
    """All the service or the connection said, where `error` is `pending`:
    `error` is short enough to publish beside the source, and this is the
    warning's, recorded so an offline build warns the same."""

    job: str = ""
    """The Save Page Now job that made the capture or failed to, if this build's
    request made it: what to ask the service about when a capture goes missing."""

    version: str = ""
    """A permanent link to the version of a Wikipedia or Wikimedia Commons page
    the report read, where no capture could be made: its `oldid` link.

    Published as `versioned` rather than `archived`. It stays as long as
    Wikimedia keeps that version, which is nearly always but not always:
    a deleted page takes its old versions with it."""

    versioned: str = ""
    """When `version` was recorded, as `YYYYMMDD`: the version current then."""

    pages: int = 0
    """How many pages the document has, if it is a PDF cited by page, or 0.

    Counted once from the capture and recorded with it, because a capture does
    not change and an offline build has to be able to check a `#page=` against
    it. A source nothing has counted, or that is not a PDF, is 0.
    """

    @property
    def reason(self) -> str:
        """Why it was not archived, as a reader is shown it: `error` without its `error:`.

        Wayback starts every reason with it, and beside "not archived" it says nothing.
        """
        return self.error.removeprefix("error:")

    @property
    def date(self) -> str:
        """The capture written out, e.g. `Sep 3, 2024`.

        The month as its three letters, so that a list of them is all one width
        rather than as wide as whichever month is longest.

        A reader checking a source against the page it cites is asking when the
        report read it, and 14 digits is not an answer anyone reads.
        Whatever does not parse as a date is shown as it is, which is the same
        choice `dateline` makes and for the same reason.
        """
        return _long_date(self.timestamp[:8], month="%b")

    @property
    def version_date(self) -> str:
        """When `version` was recorded, written out as `date` is."""
        return _long_date(self.versioned, month="%b")


@dataclass(frozen=True)
class Text:
    """A run of text sharing one style.

    `sup` and `sub` are separate from bold/italic
    because footnote references and units rely on them,
    and Typst spells them differently from HTML.
    """

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    sup: bool = False
    sub: bool = False
    href: str | None = None


@dataclass(frozen=True)
class LineBreak:
    """A soft line break inside a paragraph, from Shift+Enter in Docs.

    Docs encodes these as a vertical tab inside the text run
    rather than as a paragraph boundary.
    Left alone they reach the published page as a raw control character,
    and they hide that a `Credit:` line following one
    is a credit rather than part of the caption.
    """


@dataclass(frozen=True)
class FootnoteRef:
    """A reference to a footnote, identified by the Docs footnote id.

    The parser numbers these in document order,
    so a reference and its definition cannot disagree.
    """

    footnote_id: str
    number: int


@dataclass(frozen=True)
class Crop:
    """How much of an image the document trims from each side.

    Docs stores a crop as fractions of the original,
    so the file it serves is always the uncropped one.
    Nothing downstream can express this:
    Markdown has no way to crop, and a CSS crop would not reach the PDF.
    So the crop is applied to the file,
    which is what the document's own `Uncropped Source:` lines imply anyway.
    """

    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    @property
    def trims(self) -> bool:
        """Whether any side is trimmed by more than `key` rounds away.

        Docs stores an untrimmed side as a leftover like `1.1e-16` as well as a negative one,
        which is no crop, but would otherwise name the file as though it were.
        """
        return any(round(side, 6) for side in (self.left, self.right, self.top, self.bottom))

    @property
    def key(self) -> str:
        """Changing this renames the file."""
        if not self.trims:
            return ""
        return f"|{self.left:.6f},{self.right:.6f},{self.top:.6f},{self.bottom:.6f}"

    def box(self, width: int, height: int) -> tuple[int, int, int, int]:
        """The pixel box to keep, for an original of this size."""
        return (
            round(self.left * width),
            round(self.top * height),
            width - round(self.right * width),
            height - round(self.bottom * height),
        )


@dataclass(frozen=True)
class Vector:
    """A vector original the document names beside a rasterized copy.

    Google Docs cannot place an SVG,
    so a chart is pasted as a PNG and the real file linked beside it on an `SVG:` line.
    Every output here can show the vector,
    so the raster is only a stand-in for the editor.
    """

    file_id: str
    """The Drive file id, which is what the API downloads by.

    Empty for a link outside Drive, which is downloaded from `uri` instead.
    """

    filename: str
    title: str = ""
    uri: str = ""


@dataclass(frozen=True)
class Image:
    """An inline image.

    `object_id` is the Docs `inlineObjectId`, which is stable across edits.
    Filenames derive from it rather than from a counter,
    so inserting one image into a 54-image report
    does not rename the other 53 or move their published URLs.
    """

    object_id: str
    filename: str

    named: bool = False
    """Whether the document said which file this is, in a `Source:` line.

    Not a question the filename can answer: an image with no name publishes
    under `img-` and a hash, and a `Source:` line is free to name a file
    called `img-something.jpg`."""

    alt: str = ""
    source_uri: str | None = None
    crop: Crop = field(default_factory=lambda: Crop())
    vector: Vector | None = None

    live_uri: str = ""
    """Where the picture's own file is kept, when that is somewhere we keep things:
    a `Source:` line linking a file in one of our GitHub repos, as its raw URL.

    Downloaded in place of the copy pasted into the document, which goes stale
    whenever the file is regenerated and nobody pastes it again.
    The document's crop is still applied to it."""


Inline = Text | LineBreak | FootnoteRef | Image


def plain_text(content: list[Inline]) -> str:
    """Inline content with every mark dropped, for reading rather than rendering.

    A table of contents entry, the file a `Source:` line names,
    the caption an image borrows when Docs gave it no description:
    each wants what the run says, not how it is set.
    A break, a footnote reference, and an image say nothing in a line,
    so each contributes nothing.
    """
    return "".join(i.text for i in content if isinstance(i, Text))


# ---- block content -------------------------------------------------


@dataclass
class Paragraph:
    content: list[Inline] = field(default_factory=list)


@dataclass
class Heading:
    level: int
    """2 through 6. The title is not a heading; it is `Document.title`."""

    anchor: str
    """A published URL, so it must not move
    when an unrelated section is added elsewhere."""

    content: list[Inline] = field(default_factory=list)


class ListKind(Enum):
    BULLET = "bullet"
    NUMBER = "number"


@dataclass
class ListItem:
    content: list[Inline] = field(default_factory=list)
    children: list[ListItem] = field(default_factory=list)


@dataclass
class List:
    kind: ListKind
    items: list[ListItem] = field(default_factory=list)


@dataclass
class Figure:
    """An image together with the lines the doc attaches to it.

    ETA reports write an optional `Source:` line before the image,
    and a caption and `Credit:` line after it.
    Keeping the three distinct lets HTML class them separately
    and lets Typst place the credit differently from the caption.
    """

    image: Image
    source: list[Inline] = field(default_factory=list)
    caption: list[Inline] = field(default_factory=list)
    credit: list[Inline] = field(default_factory=list)


@dataclass
class Table:
    rows: list[list[list[Block]]] = field(default_factory=list)
    """Rows of cells; each cell holds blocks."""

    header: bool = False


class Platform(Enum):
    """Where an embedded video or post lives, which decides how it is played."""

    YOUTUBE = "youtube"
    X = "x"
    BLUESKY = "bluesky"
    DRIVE = "drive"
    """A video file in Drive, which the build downloads and the site serves itself."""


@dataclass
class Embed:
    """A video or a post, from a paragraph that is nothing but a link to one.

    Written that way in the document because that is what pasting a link gives:
    Docs has no way to place a video, and a link on its own line is the one
    thing a writer does that says "show this here" rather than "cite this".
    A link inside a sentence is a citation, and stays one.

    `key` is what the platform calls it: a video id, a post id,
    `handle/rkey` for Bluesky, or a Drive file id.
    """

    url: str
    platform: Platform
    key: str
    start: int = 0
    """Where a YouTube link asks to start, in seconds, from its `t=`."""

    vertical: bool = False
    """Whether it is a YouTube Short, which is taller than it is wide.
    Played in a landscape frame, it is a strip down the middle of one."""

    warning: list[Inline] = field(default_factory=list)
    """The `Warning:` line under it, label and all, which the reader is shown first:
    `Warning: Graphic Content: a man is hit by a train`, or empty where there is none."""

    warning_kind: str = ""
    """What its `Warning:` line warns of, without the details after it:
    `Graphic Content`, which the video shows until it is played."""

    copy: bool = False
    """Whether its line was `Video (Copy):`, so the build downloads the video
    and the site serves it, rather than leaving it to a post that can be deleted."""

    captions: list[Cue] | None = None
    """The `Captions:` written under it, or `None` where there is no such line.

    Empty where the line is: nothing said in it is what it is there to show,
    so a video the site serves without captions is not warned about."""

    title: str = ""
    """What its `Video:` line says after the label, which names the video on the page,
    or empty where the link reads as its own URL."""

    name: str = ""
    """The linked words alone, which name its file:
    what follows the link, a full stop say, is the caption's and not the file's."""

    credit: list[Inline] = field(default_factory=list)
    """The `Credit:` line under it, as a figure has, or empty where there is none."""

    @property
    def uncaptioned(self) -> bool:
        """Whether its `Captions:` line said there are none, by saying nothing."""
        return self.captions == []


@dataclass(frozen=True)
class Cue:
    """One line of a video's written captions: `0:04–0:04.7 Jesus`."""

    start: int
    """In milliseconds, as is `end`."""
    end: int
    text: str


@dataclass(frozen=True)
class Captions:
    """The captions a copied video came with, as a WebVTT file beside it."""

    file: str
    automatic: bool = False
    """Whether the platform made them by recognizing the speech, rather than somebody writing them:
    usually close, and never checked by anyone."""


@dataclass(frozen=True)
class Card:
    """What the platform said about an embed, which is what the page shows until it is played.

    Recorded in `embeds.json` and read back by every later build,
    so an offline build writes the same card and a post deleted since still has one.
    """

    author: str = ""
    text: str = ""
    """The video's title, or the post's text."""

    thumbnail: str = ""
    """Where the platform serves the picture, which is downloaded rather than linked:
    linking it would have every reader's browser ask the platform for it,
    which is what click-to-load is for not doing."""

    did: str = ""
    """The Bluesky account's permanent id, which its embed is addressed by
    and its handle is not."""

    mime: str = ""
    """What kind of file a Drive link is, which is the only way to know it is a video."""

    error: str = ""
    """Why there is no card: a looked-up embed that could not be described
    is not asked about again by every build."""


VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
"""What a Drive file has to be to play in a `video` element, and what it is called.

`.mov` plays in Safari and, as H.264, in Chrome; it is here because a phone
records one, and refusing it would only send somebody off to convert it."""


Block = Paragraph | Heading | List | Figure | Table | Embed


# ---- document ------------------------------------------------------


@dataclass
class Footnote:
    footnote_id: str
    number: int
    content: list[Block] = field(default_factory=list)


SLOT = "{}"
"""Where a warning's template takes a value.

Templates are written here rather than read from a document,
so nothing a report says can be mistaken for one.
"""


def filled[T](template: str, values: tuple[T, ...]) -> tuple[str | T, ...]:
    """`template` split at its `{}`, with `values` in their places.

    The words and the values stay separate spans rather than becoming one
    string, because that is what lets each of them be rendered as what it is:
    a value is coloured, or quoted, or struck through, and words are words.
    Interpolating first and looking for the values again afterwards is the
    other way round, and it has to guess.

    Shared by a document's warnings and by the log's own notes, so both say a
    value the same way and neither has to be read twice.
    """
    said = template.split(SLOT)
    if len(said) != len(values) + 1:
        raise ValueError(f"{template!r} has {len(said) - 1} {SLOT} for {len(values)} values")
    parts: list[str | T] = [said[0]]
    for value, rest in zip(values, said[1:], strict=True):
        parts.append(value)
        parts.append(rest)
    return tuple(part for part in parts if part != "")


@dataclass(frozen=True)
class Shown:
    """A value a warning shows rather than says.

    A field name, a filename, a line quoted back.
    Emitters mark it the way they mark code, because it is something exact
    to go and find rather than words being spoken.
    """

    value: str


@dataclass(frozen=True)
class Cut:
    """The part of a value that will not survive.

    Struck through, which is the difference between telling somebody
    a string is too long and showing them where it stops.
    """

    value: str


SPACE = "\u00b7"
"""What a space is drawn as inside a `Highlighted` value.

A space is the one thing a warning cannot quote as itself: HTML collapses a
run of them, `typst` sets it as one, and Markdown is read by something that
does the same, so the reader is shown a line that looks correct and told it
is not. The middle dot is what an editor draws a space with.
"""


@dataclass(frozen=True)
class Highlighted:
    """A shown value with the part it is about picked out of the middle of it.

    Carried as its three pieces rather than as one string, so a terminal can
    mark the middle without having to find it again, and so a value holding
    whatever the middle happens to be is never mistaken for it.
    """

    before: str
    marked: str
    after: str

    @property
    def value(self) -> str:
        """The three pieces as the one value they read as."""
        return f"{self.before}{self.marked}{self.after}"


@dataclass(frozen=True)
class Quoted:
    """A value given a line of its own.

    Long enough that running it into the sentence would leave the reader
    unsure where the sentence ended and the document began.
    """

    spans: tuple[Span, ...]

    def __init__(self, *spans: Span) -> None:
        object.__setattr__(self, "spans", spans)


@dataclass(frozen=True)
class Listed:
    """One line for each of the things a warning is about.

    A warning naming one thing says it in the sentence.
    A warning naming seventeen lists them,
    because seventeen names run together are not a list anybody reads.
    """

    items: tuple[tuple[Span, ...], ...]

    def __init__(self, *items: tuple[Span, ...]) -> None:
        object.__setattr__(self, "items", items)


type Span = str | Shown | Cut | Highlighted
type Part = Span | Quoted | Listed


@dataclass(frozen=True)
class Notice:
    """One warning, in the pieces it is made of.

    Not a marked-up string: a warning is built here and rendered by three
    emitters, and marking it up at one end to recover it by parser at the
    other is how a filename with a backtick in it came out the far end
    having re-paired the spans around it.

    `str` writes the markup and nothing reads it:
    it is what the log prints and what a test asserts against.
    """

    parts: tuple[Part, ...]

    @override
    def __str__(self) -> str:
        return "".join(_written(part) for part in self.parts)


def _written(part: Part) -> str:
    """One part as the log writes it, which is how this project writes prose."""
    match part:
        case Shown(value):
            return f"`{value}`"
        case Cut(value):
            return f"~~{value}~~"
        case Highlighted():
            return f"`{part.value}`"
        case Quoted(spans):
            return "\n> " + "".join(_written(span) for span in spans)
        case Listed(items):
            return "".join("\n- " + "".join(_written(span) for span in item) for item in items)
        case _:
            return part


@dataclass
class Document:
    title: str = ""
    """The headline as plain text, for what holds only text:
    the page's `<title>`, the PDF's metadata, the preview index."""

    headline: list[Inline] = field(default_factory=list)
    """The headline as written, with its underlines and the rest of its formatting,
    for where it is set as the headline. Empty when the headline is not from a
    `Title` paragraph, where `title` is all there is."""

    subtitle: list[Inline] = field(default_factory=list)
    """The `Subtitle`-styled paragraph under the headline, set under it as the standfirst.

    Not the header's `SEO Description:`, which is what a search result previews
    and which nobody reading the document sees under its headline."""

    subtitle_ends_title: bool = False
    """Whether the headline ends in a colon and the subtitle is the rest of it,
    as `Digging Out of a Very Deep Hole:` over `Saving Billions on 125th Street`.
    `title` is then the two together, since that is the report's name."""

    file_title: str = ""
    """What the document is called in Drive, which is not what it is called here.

    The headline is the report's title; this is the working name it is filed under,
    and the only thing `reports.toml` can be checked against."""

    open_suggestions: int = 0
    """Suggestions still open on the tab this was read from.

    Recorded by the fetch, because the response a build reads has them resolved away.
    Zero for a response saved before the fetch counted them, which cannot be helped:
    the count is not in the file to be read."""

    suggestions_accepted: bool = False
    """Whether this was read with its open suggestions accepted, as a preview of them."""

    open_comments: int = 0
    """Comment threads still open on this tab.

    Zero where the fetch could not read them, which is not the same as none:
    the count is carried over from the last build that could."""

    tab_title: str = ""
    """What the tab this was read from is called.

    A `?tab=` id is opaque, so it is not something a person can check by reading it.
    This is the same choice written in words."""
    meta: dict[str, str] = field(default_factory=dict)
    """The doc's leading `Header` section, lowercased keys.
    Unrecognized keys are kept rather than dropped."""

    has_header: bool = False
    """Whether the document had a `Header` section for `meta` to be read from.

    Not the same as an empty `meta`, which is also what a `Header` section
    holding no `Key: value` lines leaves behind.
    The two are different mistakes and want different things said about them:
    a missing section is usually one whose heading is styled as body text,
    where an empty one is a section nobody filled in."""

    blocks: list[Block] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)
    warnings: list[Notice] = field(default_factory=list)

    card: Image | None = None
    """A wide image with the title set into it,
    placed above the headline for whatever links to the report to show as a thumbnail.

    Not part of the report, so not in `blocks`: it publishes as `og:image` and nowhere else."""

    image_files: dict[str, str] = field(default_factory=dict)
    """Docs object id to the filename actually written, extension included.

    Only fetching can know it:
    a Docs `inlineObject` says nothing about what kind of file it is,
    and a vector named alongside a raster is written under a different name entirely.
    `images.download` fills this in as it writes each file,
    and a build that skips the download reads it back from `images.json`,
    which every build that downloaded left behind and which such a build requires.

    An image missing from here is one nothing has ever written,
    and `image_href` refuses to name it rather than guessing at a stem.
    """

    image_shapes: dict[str, tuple[int, int]] = field(default_factory=dict)
    """Docs object id to the pixel size of the file actually written.

    From the same record as `image_files`, and for the same reason:
    Docs says how large an image is placed, not how large it is,
    and the crop applied here changes the shape of the file without the document knowing.
    An SVG has no pixel size to read, so it is one this is empty for.
    """

    unpublished: dict[str, str] = field(default_factory=dict)
    """Docs object id to why its SVG could not be had, for a figure published without one.

    Never the raster instead: it is in the doc only because Docs cannot place an SVG.
    Recorded in `images.json`, for a build that does not download.
    """

    image_alts: dict[str, str] = field(default_factory=dict)
    """Docs object id to the description its SVG gives itself.

    A chart linked on an `SVG:` line is the picture that publishes,
    and its own `<title>` and `<desc>` say what it shows.
    Recorded in `images.json` with the filename, for a build without the file.
    """

    archives: dict[str, Archived] = field(default_factory=dict)
    """Source URL to the snapshot of it, keyed by the original and never by the
    snapshot.

    Filled in from `archive.json`, which is committed, and added to by a build
    that submits the sources not yet in it. A document whose own href already
    points at a snapshot seeds this at parse time, so a link written by hand as
    an archive is one already archived rather than one to archive again.
    """

    cards: dict[str, Card] = field(default_factory=dict)
    """Embed URL to what its platform said about it, from `embeds.json`."""

    media_files: dict[str, str] = field(default_factory=dict)
    """Embed URL to the file written for it: a thumbnail under `IMAGE_DIR`,
    or the video itself under `VIDEO_DIR` for one in Drive or one copied.

    Recorded in `embeds.json` for the same reason as `image_files`:
    the extension is learned by fetching."""

    media_captions: dict[str, Captions] = field(default_factory=dict)
    """Embed URL to the captions its copied video came with, under `VIDEO_DIR`.

    Recorded in `embeds.json`, so an offline build writes the same `<track>`."""

    @property
    def embeds(self) -> list[Embed]:
        """Every embed in the document, in order, deduplicated by URL."""
        seen: dict[str, Embed] = {}
        for block in self._every_block():
            if isinstance(block, Embed):
                seen.setdefault(block.url, block)
        return list(seen.values())

    @property
    def hero(self) -> Figure | None:
        """The figure a report opens with, if it opens with one.

        The document puts it under the headline,
        so it belongs there rather than after a table of contents it should be introducing.

        Recognized by position: nothing else in these reports leads with a figure,
        and when one does and does not mean it,
        that is when a `Hero:` line earns its place beside `Source:` and `Credit:`.
        """
        first = self.blocks[0] if self.blocks else None
        return first if isinstance(first, Figure) else None

    @property
    def body(self) -> list[Block]:
        """Everything after the hero, which is the report proper."""
        return self.blocks[1:] if self.hero is not None else self.blocks

    @property
    def contributors(self) -> list[str]:
        """The people credited on the published page, by surname.

        Read from `Public Contributors:` and nothing else:
        the document carries a separate `Private Contributors:` field
        so that some names do not publish.

        Where Docs cannot resolve a person chip to a display name it renders
        as the address, and the field is written `Alon Levy (alon@example.org)`
        with the name typed and the chip beside it.
        A byline is names, so the address is dropped.

        Sorted, because `etany.org` credits contributors alphabetically
        and the field they are typed into is in whoever-was-added-when order.
        """
        names = self.meta.get("Public Contributors", "")
        listed = [_named(name) for name in names.split(",")]
        return sorted((name for name in listed if name), key=_by_surname)

    @property
    def dateline(self) -> str:
        """The publication date, written out, e.g. `August 19, 2026`.

        The field is a date chip,
        so the document holds whatever short form Docs renders, `Aug 19, 2026`,
        where `etany.org` writes the month out.

        Anything that does not parse as a date is published exactly as written:
        guessing would be worse than showing what the header says.
        """
        return _long_date(self.meta.get("Publish Due Date", ""))

    @property
    def published(self) -> date | None:
        """The publication date, or `None` where the header gives none that parses."""
        return _date(self.meta.get("Publish Due Date", ""))

    @property
    def phase(self) -> str:
        """Where the report is in its own process, when that is worth saying.

        `published` is the state every reader of a published report is looking at,
        so it is the one phase that goes unmentioned.
        Anything else is a draft of some kind reaching someone,
        and that is exactly what they need to be told.
        """
        phase = self.meta.get("Phase", "").strip()
        return "" if phase.casefold() == "published" else phase

    @property
    def slug(self) -> str:
        """The published path, e.g. `/reports/digging-out-deep-hole-sas-west`."""
        return self.meta.get("URL", "")

    def headings(self, level: int | None = None) -> list[Heading]:
        """Every heading in order, or only those at one level.

        The title is not among them: it is `Document.title`, not a block,
        so a table of contents over these never lists the report itself.
        """
        return [
            b for b in self.blocks if isinstance(b, Heading) and (level is None or b.level == level)
        ]

    @property
    def images(self) -> list[Image]:
        """Every image in the document, in order, including inside footnotes.

        Deduplicated by `object_id`: the same image used twice is one file.

        The share card is among them even though it is not in `blocks`:
        `og:image` is a URL like any other and needs the file to be there.
        """
        seen: dict[str, Image] = {}
        if self.card is not None:
            seen[self.card.object_id] = self.card
        for block in self._every_block():
            for image in _images_in(block):
                seen.setdefault(image.object_id, image)
        return list(seen.values())

    @property
    def sources(self) -> list[str]:
        """Every external link the report cites, in the order it cites them.

        Deduplicated by URL, first use first, the way `images` deduplicates by
        object id: one page cited six times is one source, and renumbering it
        because a later section cites it again would renumber everything after.

        Document order and nothing else decides the numbering. Reading it off
        the archive record instead would make the numbers a property of which
        captures happened to have succeeded, and an offline build against a
        partial record would renumber the whole report.
        """
        seen: dict[str, None] = {}
        for block in self._every_block():
            for href in _links_in(block):
                if is_source(href):
                    seen.setdefault(href, None)
        return list(seen)

    def archived(self, source: str) -> Archived | None:
        """Where `source` is archived, with its own fragment put back.

        The record is keyed by the document, so a capture is shared by every
        page of it the report cites. The fragment goes back on the way out,
        which is what makes the archived copy of a claim about page 28 open on
        page 28 rather than on the cover.

        A `#page=` citation is served raw, because the ordinary Wayback URL for
        a PDF is not the PDF. It is an HTML page carrying the capture toolbar
        with the file inside it, so the browser applies `#page=50` to that
        wrapper, which has no page 50, and the reader gets the cover. Asked for
        with `id_`, the same capture comes back as the PDF itself and the
        viewer opens where the citation meant. Measured in a browser, on the
        `R211 Tech Spec.pdf` capture the report already cites: `50 / 819`.

        Only for those. An HTML capture is the archived document itself, so an
        anchor in it already resolves, and the ordinary URL is the one that
        keeps the toolbar and serves the page's images and stylesheets from the
        archive rather than from a live site that may no longer have them.
        """
        base, hash_, fragment = source.partition("#")
        found = self.archives.get(base)
        if found is not None and found.version and hash_:
            found = replace(found, version=f"{found.version}{hash_}{fragment}")
        if found is None or not found.snapshot or not hash_:
            return found
        snapshot = found.snapshot
        capture = _capture(snapshot)
        if fragment.startswith(PDF_PAGE) and capture is not None:
            snapshot = wayback_url(*capture, modifier=UNREWRITTEN)
        return replace(found, snapshot=f"{snapshot}{hash_}{fragment}")

    @property
    def source_uses(self) -> dict[str, int]:
        """How many times each source is cited, which is how many backlinks it has."""
        uses: dict[str, int] = {}
        for block in self._every_block():
            for href in _links_in(block):
                if is_source(href):
                    uses[href] = uses.get(href, 0) + 1
        return uses

    @property
    def figures(self) -> list[Figure]:
        """Every figure in the document, in order, footnotes included.

        Unlike `images`, not the share card:
        it is a picture of the title rather than a figure of the report.
        """
        return [b for b in self._every_block() if isinstance(b, Figure)]

    def text_runs(self) -> Iterator[tuple[list[Inline], Where]]:
        """Every run of inline content in the report, captions and footnotes included.

        What somebody typed, wherever they typed it,
        for the checks that ask whether a line belongs where it sits.

        A footnote is all one context whatever it holds:
        these carry citations, which are written to their own rules
        and are nobody's idea of a `Key: value` line.
        """
        for block in _walk(self.blocks):
            yield from inlines_in(block)
        for footnote in self.footnotes:
            for block in _walk(footnote.content):
                for run, _ in inlines_in(block):
                    yield run, Where.FOOTNOTE

    def _every_block(self) -> Iterator[Block]:
        """Every block of the report, then every block of its footnotes.

        The body first, because that is the order the document is read in.
        Descends into lists and table cells,
        so nothing is missed for sitting inside something else.
        """
        yield from _walk(self.blocks)
        for footnote in self.footnotes:
            yield from _walk(footnote.content)

    def image_href(self, image: Image) -> str:
        """The filename as emitted, which is the name of the file that was written.

        There is no answer for an image nothing wrote.
        The stem is not one: an extension is learned by fetching,
        so `images/img-d4734d4b` is a path no browser serves as an image
        and `typst` will not open at all,
        and a page that links one is a page with a hole in it
        that nothing downstream reports as this.
        """
        written = self.image_files.get(image.object_id)
        if written is None:
            raise ValueError(
                f"image {image.object_id} was never written, so nothing says what it "
                f"is called; an extension is learned by fetching, and `{image.filename}` "
                f"without one is not a picture anything can serve"
            )
        return written

    def playable(self, embed: Embed) -> Card | None:
        """What to show for `embed`, or `None` where it can only be the link it was.

        A card that records a failure is none, and so is a Drive file that is
        not a video, or one whose file was never written: a `video` element
        with nothing to play is worse than the link.
        """
        card = self.cards.get(embed.url)
        if card is None or card.error:
            return None
        if embed.platform is Platform.DRIVE and (
            card.mime not in VIDEO_TYPES or embed.url not in self.media_files
        ):
            return None
        return card

    def served_video(self, embed: Embed) -> str | None:
        """The video file the site serves for `embed`, if it serves one.

        Checked by extension as well, since a copy that failed to download
        leaves the thumbnail an earlier build recorded for the same URL.
        """
        if embed.platform is not Platform.DRIVE and not embed.copy:
            return None
        file = self.media_files.get(embed.url)
        if file is None or Path(file).suffix not in VIDEO_TYPES.values():
            return None
        return file

    def image_aspect(self, image: Image) -> float | None:
        """The written file's width over its height, if that was recorded."""
        size = self.image_shapes.get(image.object_id)
        if size is None or not size[1]:
            return None
        return size[0] / size[1]

    def warn(self, template: str, *values: Part) -> None:
        """Warn, with `{}` in `template` wherever a value goes.

        The template is written here and the values come from the document,
        which is why they are handed over separately rather than formatted in:
        a value is never read as markup, whatever it happens to contain.
        """
        self.warnings.append(Notice(filled(template, values)))


# What a Docs date chip can render, most likely first.
# A chip is a real date, so this is a short list of ways to write one
# rather than an attempt at parsing dates in general.
DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%Y%m%d")


def _long_date(text: str, month: str = "%B") -> str:
    """`Aug 19, 2026` written out, or `text` unchanged if it is not a date.

    `month` is how the month is written: in full by default, `%b` for its three letters.
    """
    parsed = _date(text)
    return f"{parsed:{month}} {parsed.day}, {parsed.year}" if parsed else text


def _date(text: str) -> date | None:
    """`text` as a date in any of `DATE_FORMATS`, or `None` if it is not one."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def addressed(entry: str) -> tuple[str, str] | None:
    """One listed contributor split around the address written beside their name.

    The name, and whatever was written after the closing bracket,
    which is a second contributor whose comma is missing.
    `None` where the entry carries no address, which is the ordinary case:
    a resolved person chip is a name and nothing else.

    Docs writes an address beside a name when it cannot resolve a person chip
    to a display name: the chip renders as the address,
    so the name is typed and the chip put beside it.
    The name is the half worth publishing, and `etany.org` credits names.

    Not an address by any standard, deliberately:
    a bracketed run with no spaces and something either side of an `@`.
    What is being recognized is the Docs spelling, not an email,
    and a stricter reading would drop a name
    over an address this has no business having an opinion about.
    """
    name, bracket, rest = entry.partition("(")
    while bracket:
        address, closed, after = rest.partition(")")
        if closed and _is_address(address.strip()):
            return name.strip(), after.strip()
        # Brackets holding something else, `(chair)` and the like,
        # are part of the name: kept, and scanned past
        # rather than stopping the search for an address behind them.
        name += f"{bracket}{address}{closed}"
        more, bracket, rest = after.partition("(")
        name += more
    return None


def _is_address(address: str) -> bool:
    """Whether a bracketed run is the address Docs writes for an unresolved chip."""
    local, at, domain = address.partition("@")
    return bool(at and local and domain) and not any(c.isspace() for c in address)


def _named(entry: str) -> str:
    """One listed contributor, as a byline writes them.

    Every address goes, not just the first.
    An entry holding two of them is two contributors
    whose separating comma was missed, and the byline is wrong either way;
    leaving the second address in would publish it,
    which is the one outcome worth ruling out.
    """
    names = []
    rest = entry
    while (found := addressed(rest)) is not None:
        name, rest = found
        names.append(name)
    names.append(rest.strip())
    return " ".join(name for name in names if name)


def _by_surname(name: str) -> tuple[str, str]:
    """Sort key for a person's name: last word first, then the whole name.

    The last word is the surname for every name these reports have carried,
    and a display name is all the document gives us.
    It guesses wrong for a surname written in more than one word,
    `van der Berg` sorting under `Berg`, which is wrong quietly and in one place.
    Casefolded so `de Vries` and `De Vries` land together.
    """
    return (name.split()[-1].casefold(), name.casefold())


# ---- traversal -----------------------------------------------------


def _walk(blocks: list[Block]) -> Iterator[Block]:
    """Yield every block, descending into lists and table cells."""
    for block in blocks:
        yield block
        if isinstance(block, Table):
            for row in block.rows:
                for cell in row:
                    yield from _walk(cell)


WAYBACK_HOST = "web.archive.org"
WAYBACK_PATH = "/web/"
"""Where a Wayback URL keeps its captures, before the timestamp and the page."""

MODIFIER = ascii_letters + "_"
"""What may follow the timestamp: `id_` for the unrewritten original,
`im_` for an image.

Says how Wayback serves the capture rather than which capture it is,
so it is read off and dropped.
"""

STAMP_DIGITS = range(4, 15)
"""How long a capture timestamp runs: a bare year through to the second."""


def _capture(href: str) -> tuple[str, str] | None:
    """A Wayback URL read as the timestamp it was taken at and the page it is of.

    The page is taken as written rather than reassembled from its parts.
    It is not escaped where it sits inside the wrapper,
    so `urlsplit` reads its query as the wrapper's own
    and rebuilding from the pieces would drop it.
    """
    origin, found, rest = href.partition(WAYBACK_PATH)
    if not found:
        return None
    wrapper = urlsplit(origin)
    if wrapper.scheme not in ("http", "https") or wrapper.hostname != WAYBACK_HOST:
        return None
    capture, slash, url = rest.partition("/")
    stamp = capture.rstrip(MODIFIER)
    if not slash or not stamp.isdigit() or len(stamp) not in STAMP_DIGITS:
        return None
    if urlsplit(url).scheme not in ("http", "https"):
        return None
    return stamp, url


def wayback_url(timestamp: str, url: str, modifier: str = "") -> str:
    """The Wayback address of one capture of `url`.

    The one place that knows the shape, so the address this builds
    and the address `_capture` reads cannot drift apart.
    """
    return f"https://{WAYBACK_HOST}{WAYBACK_PATH}{timestamp}{modifier}/{url}"


def unwrap_snapshot(href: str) -> tuple[str, Archived | None]:
    """A link split into the page it is of and the capture it is, if it is one.

    A report that cites `web.archive.org/web/.../nypost.com/...` has already
    done by hand what this does: the source is the Post article, and the
    snapshot is the capture already named. Left wrapped it would be a source of
    its own, keyed in the record under a URL that is itself the answer, and the
    same article cited bare elsewhere would be a second source saying the same
    thing.
    """
    found = _capture(href)
    if found is None:
        return href, None
    stamp, url = found
    # Rebuilt rather than kept as written, so that a capture cited with a
    # modifier and the same capture cited without one are one snapshot.
    # Of the document rather than of the page of it named here, because that is
    # what a capture is, and `Document.archived` puts the fragment back.
    return url, Archived(snapshot=wayback_url(stamp, document_url(url)), timestamp=stamp)


PDF_PAGE = "page="
"""The fragment a link to a page of a PDF carries.

An instruction to the PDF viewer rather than an anchor in a document, which is
why it is the one fragment the ordinary Wayback URL swallows.
"""


def cited_page(source: str) -> str | None:
    """The page a `#page=` citation names, as written, or `None` if it names none.

    As written rather than as a number, so that a check can say what is wrong
    with `#page=` or `#page=iv` rather than reading either as no citation at all.
    A viewer reads the fragment as `&`-separated, so `#page=5&zoom=80` is page 5.
    """
    fragment = source.partition("#")[2]
    for part in fragment.split("&"):
        if part.startswith(PDF_PAGE):
            return part.removeprefix(PDF_PAGE)
    return None


UNREWRITTEN = "id_"
"""The modifier asking Wayback for the capture as it was, rather than rewritten
and wrapped in the archive's own page."""


def document_url(url: str) -> str:
    """A link's address without its fragment, which is the thing that is archived.

    A fragment never reaches a server. `#page=28` is an instruction to the PDF
    viewer once the file has arrived, and `#:~:text=` is one to the browser, so
    fifteen citations of fifteen pages of one MTA PDF are fifteen citations of
    one document and one capture of it. Asking for fifteen would spend fifteen
    of the day's captures on the same file and get fifteen snapshots of it,
    taken at fifteen moments.
    """
    return url.partition("#")[0]


def is_source(href: str | None) -> bool:
    """Whether a link is a citation of something outside the report.

    An anchor is a place in this page and `mailto:` is a person, not a source.
    """
    if not href:
        return False
    return href.startswith(("http://", "https://"))


class Where(Enum):
    """Where in the document a run of text sits.

    What is a stray line in one place is the ordinary spelling in another:
    a `Credit:` under a picture is a credit,
    and the same line in a body paragraph is a line somebody lost.
    """

    BODY = "body"
    HEADING = "heading"
    FOOTNOTE = "footnote"
    SOURCE = "source"
    CAPTION = "caption"
    CREDIT = "credit"


def inlines_in(block: Block) -> list[tuple[list[Inline], Where]]:
    """Every run of inline content the block carries, in reading order, and where it sits.

    A figure's `Source:` line is included, unlike `_links_in`:
    what reads these is asking what the document says, not what it publishes,
    and an editorial note is still something somebody typed.
    A table contributes nothing of its own; `_walk` reaches its cells.
    """
    match block:
        case Figure():
            return [
                (content, where)
                for content, where in (
                    (block.source, Where.SOURCE),
                    (block.caption, Where.CAPTION),
                    (block.credit, Where.CREDIT),
                )
                if content
            ]
        case Heading():
            return [(block.content, Where.HEADING)]
        case Paragraph():
            return [(block.content, Where.BODY)]
        case List():
            return [(item.content, Where.BODY) for item in _items(block.items)]
    return []


def _links_in(block: Block) -> list[str]:
    """Every href the block's own inlines carry, in order."""
    match block:
        case Figure():
            # `Figure.source` is left out: it names the original file in Drive
            # for whoever assembles the report, no emitter publishes it, and a
            # Sources entry for a link nothing on the page points at is an
            # entry whose way back into the text does not exist.
            return _hrefs(block.caption) + _hrefs(block.credit)
        case Paragraph() | Heading():
            return _hrefs(block.content)
        case List():
            return [href for item in _items(block.items) for href in _hrefs(item.content)]
        case Embed():
            # A copied video is served from the report, so its download URL
            # is not a source the published page points readers to.
            return [] if block.copy else [block.url]
    return []


def _hrefs(content: list[Inline]) -> list[str]:
    return [i.href for i in content if isinstance(i, Text) and i.href]


def _images_in(block: Block) -> list[Image]:
    match block:
        case Figure():
            return [block.image]
        case Paragraph() | Heading():
            return [i for i in block.content if isinstance(i, Image)]
        case List():
            return [i for item in _items(block.items) for i in item.content if isinstance(i, Image)]
    return []


def _items(items: list[ListItem]) -> Iterator[ListItem]:
    for item in items:
        yield item
        yield from _items(item.children)
