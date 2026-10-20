"""HTML two ways: a fragment to embed, and a page to read.

Scoped to `.eta-report` so the same CSS works inlined into the pasted fragment
and injected once site-wide under Custom CSS.
A Squarespace code block applies no styling of its own,
so without this the captions, table of contents, and footnotes
render as undifferentiated body text.
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from string import ascii_lowercase
from typing import cast, override

import htpy
from htpy import Element, Node
from htpy._types import Renderable
from markupsafe import Markup

from ..assets import read
from ..naming import (
    ASSET_DIR,
    CAPTIONS_LANGUAGE,
    IMAGE_DIR,
    SITE,
    VIDEO_DIR,
    WEB_FORMATS,
    content_anchor,
    has_web_copies,
    warning_poster_name,
    web_href,
    web_widths,
)
from ..nodes import (
    VIDEO_TYPES,
    Archived,
    Block,
    Card,
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
    ListItem,
    ListKind,
    Notice,
    Paragraph,
    Platform,
    Table,
    Text,
    plain_text,
)
from .base import (
    CONTRIBUTORS_NOTE,
    PLATFORM_NAMES,
    Emitter,
    shown_url,
    warning_markup,
)

# Only styles what the emitter produces, inheriting the rest from the theme,
# so a report does not fight the site around it.
REPORT_CSS = read("report.css")

# Positions the footnote tooltip, which the stylesheet cannot:
# whether there is room under the reference is a question about the window,
# and the answer changes with the scroll position.
# Without this the tooltip still appears on hover, under the reference,
# and is only in the wrong place near an edge of the screen.
REPORT_JS = read("report.js")


# A Squarespace code block holds 400 KB.
# Warn well before that: the limit is what the editor accepts,
# not what is pleasant to paste, and 200 KB into a textarea is already slow to save.
CODE_BLOCK_LIMIT = 400_000
CODE_BLOCK_WARN = 250_000


type Piece = Renderable | str | int | bool | None | Iterable[Piece]
"""`htpy`'s `Node`, less the callable, which nothing here is.

Leaving it out is what lets `pyrefly` read the file:
it matches an element against every other member of that union on its own,
and against the whole union only once the callable is gone.
The narrowing is this file's, not a doubt about the library.
"""


class Tag(Element):
    """An element that takes the children this file has to give it.

    One place says the narrowing is deliberate, rather than every tag on the page.
    """

    @override
    # A parameter narrowed on purpose, which is worth saying out loud twice
    # rather than turning either checker off over.
    # pyrefly: ignore[bad-override]
    def __getitem__(self, children: Piece) -> Tag:  # ty: ignore[invalid-method-override]
        return super().__getitem__(cast(Node, children))


class Tags:
    """Every tag, by name, as a `Tag`.

    Void elements are not here: `htpy.br` and `htpy.img` hold nothing,
    and a `Tag` would offer to put something in them.
    """

    def __getattr__(self, name: str) -> Tag:
        return Tag(name.rstrip("_"))


tag = Tags()


def joined(separator: Piece, parts: Iterable[Piece]) -> Piece:
    """`parts` with `separator` between them, still as nodes.

    The string equivalent would flatten each part on the way past,
    which is where escaping gets lost.
    """
    out: list[Piece] = []
    for i, part in enumerate(parts):
        if i:
            out.append(separator)
        out.append(part)
    return out


def lines(parts: Iterable[Piece]) -> Piece:
    """One part per line.

    A newline between two blocks is whitespace HTML collapses,
    and it is what makes a diff of a rebuilt report readable.
    """
    return joined("\n", parts)


def markup(node: Piece) -> Markup:
    """A tree of `htpy` nodes as the string the rest of the emitter passes around.

    `Markup` rather than a bare `str` because the difference matters on the way
    back in: a value that has already been escaped must not be escaped again
    when it is placed inside the next element.
    """
    return Markup(htpy.fragment[node])


HTML_H2 = 2
"""The heading level a piece is cut at.

`h2` is what a report's sections are: `Heading 1` in the document,
which publishes one level down because the headline is the `h1`.
"""


def link_mark(anchor: str, what: str = "section") -> Tag:
    """The link a block carries to itself.

    Ahead of the block's own content rather than after it,
    so every mark on the page hangs in one column.
    The `#` is the stylesheet's,
    so quoting a heading does not copy a character nobody wrote.
    """
    return tag.a(class_="link-mark", href=f"#{anchor}", aria_label=f"Link to this {what}")


def phase_markup(phase: str) -> str:
    """What a reader of a draft has to be told before reading it.

    Labelled `Phase:`, because the state on its own is a word like `Compositing`
    that means nothing to a reader who does not already know what it is a phase of.

    A function rather than only a method,
    because `report_page` writes it above the headline
    and never walks to it.
    """
    if not phase:
        return ""
    return markup(tag.p(class_="phase")[tag.span(class_="phase-label")["Phase: "], phase])


def player_url(node: Embed, card: Card) -> str:
    """The platform's own player for `node`, which the script loads on click.

    Each is an `iframe` of the platform's, rather than its embed script,
    so nothing of theirs runs in the report's page even once it is playing.
    `youtube-nocookie.com` is YouTube's own address for a player that sets
    no cookie until the video is played.
    """
    match node.platform:
        case Platform.YOUTUBE:
            start = f"&start={node.start}" if node.start else ""
            return f"https://www.youtube-nocookie.com/embed/{node.key}?autoplay=1{start}"
        case Platform.X:
            return f"https://platform.twitter.com/embed/Tweet.html?id={node.key}&dnt=true"
        case Platform.BLUESKY:
            rkey = node.key.split("/", 1)[1]
            return f"https://embed.bsky.app/embed/{card.did}/app.bsky.feed.post/{rkey}"
        case Platform.DRIVE:
            return ""


PDF_ICON = (
    '<svg aria-hidden="true" viewBox="0 0 16 16" width="1em" height="1em" fill="none" '
    'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M3 13h10"/></svg>'
)
"""A download arrow, drawn in the text's color so it follows the site's."""


class HtmlEmitter(Emitter):
    extension = ".html"

    def __init__(
        self,
        image_base: str = "",
        inline_css: bool = True,
        inline_js: bool = True,
        inline_phase: bool = True,
        asset_base: str = "",
        pdf_href: str = "",
        source_brackets: bool = False,
        site_url: str = SITE,
        page_assets: str = "",
    ) -> None:
        super().__init__()
        self.image_base = image_base.rstrip("/")
        # Where the site is served, for what a fragment links there with no `asset_base`.
        self.site_url = site_url
        # Where a page finds the site's assets beside it, as it links its stylesheet;
        # empty for the fragment, whose `asset_base` says where they are.
        self.page_assets = page_assets
        # Turn off once `REPORT_CSS` lives in the site's Custom CSS.
        self.inline_css = inline_css
        # Off for a page, which links one copy; on for the fragment, which
        # is pasted somewhere with nothing to link to.
        self.inline_js = inline_js
        # Where the fragment links what it does not carry: the site's copies.
        # Empty for a page, which links its own.
        self.asset_base = asset_base
        # Off for a page, which writes the phase above the headline itself;
        # on for the fragment, which emits it with the rest of the report.
        self.inline_phase = inline_phase
        # Where the report's PDF is, as the masthead links it; empty for no link.
        self.pdf_href = pdf_href
        # Whether a cited link shows its `[n]` where it hovers. Off, the
        # number is still in the markup, where the backlinks land, and is the
        # first thing in the box the link carries.
        self.source_brackets = source_brackets
        self._in_tip = False
        """Whether what is being emitted is the box a reference carries,
        which is a copy of a note and so cannot carry boxes of its own."""
        self._taken: set[str] = set()
        # A paragraph's id is its section's id and its place in that section,
        # so both reset at every heading.
        self._scope = ""
        self._paragraphs = 0
        self._marked = True
        self._source_uses: dict[str, int] = {}
        """How many times each source has been cited so far in this walk,
        which is which backlink letter the next citation of it gets."""
        self._lead: Piece = None
        """Markup for the next paragraph to open with, inside its own tag.

        A footnote's way back into the text belongs in the first line of the
        note rather than on a line of its own above it.
        The paragraph that takes it clears it, so it is placed once.
        """

    @override
    def join(self, parts: list[str]) -> str:
        """As the base class, but joined as nodes so the markup survives the join.

        The base class joins with a separator, flattening to a plain string,
        which is exactly what the next element would escape on the way in.
        """
        return markup(joined(self.separator, [part for part in parts if part]))

    @override
    def inlines(self, content: list[Inline]) -> str:
        """As `join`, for the run of inline nodes inside a block."""
        return markup([self.inline(node) for node in content])

    def anchor(self, prefix: str, text: str) -> str:
        """An id for a block, unique within the page.

        Two blocks saying exactly the same thing hash the same,
        and the second gets a counted suffix.
        That suffix is positional, which nothing else here is,
        but the blocks are indistinguishable.
        """
        return self.take(content_anchor(prefix, text))

    def take(self, base: str) -> str:
        """`base`, or the first counted variant of it not already used."""
        candidate = base
        n = 1
        while candidate in self._taken:
            n += 1
            candidate = f"{base}-{n}"
        self._taken.add(candidate)
        return candidate

    @override
    def document(self, doc: Document) -> str:
        return self.join(self.wrapped(self.whole(doc)))

    def restart(self, doc: Document) -> None:
        """Forget what the last document allocated.

        Every id on the page is allocated while walking it,
        so a second walk of the same document has to start where the first did
        or it produces the same ids suffixed to avoid themselves.

        Called by `groups`, which is the walk. A report emitted whole and the
        same report emitted in pieces are two walks of one document,
        and the pieces have to carry the ids the whole one published.

        The document is set here as well as by `emit`, because a walk needs it:
        a footnote reference carries a copy of its note, which is read off the
        document rather than passed down the tree.
        """
        self.doc = doc
        self.number_sources(doc)
        self._taken = {
            "title",
            "subtitle",
            "table-of-contents",
            "footnotes",
            "sources",
            "contributors",
        }
        self._source_uses = {}
        self._scope = ""
        self._paragraphs = 0
        self._marked = True
        self._lead = None
        self._taken.update(b.anchor for b in doc.blocks if isinstance(b, Heading))

    def whole(self, doc: Document) -> list[str]:
        """Everything in the report, in one group."""
        return [part for group in self.groups(doc) for part in group]

    def wrapped(self, group: list[str]) -> list[str]:
        """One group as a standalone fragment: what a piece is, and what a report is.

        The stylesheet and the script ride on each, and each is its own
        `.eta-report` div, so consecutive code blocks still pick up the same CSS.
        """
        shell = []
        if self.inline_css:
            shell.append(markup(tag.style[Markup(f"\n{REPORT_CSS}")]))
        elif self.asset_base:
            href = f"{self.asset_base}/report.css"
            shell.append(markup(htpy.link(rel="stylesheet", href=href)))
        # Unlike the stylesheet, which a site can carry once under Custom CSS,
        # this travels with the report: it is small, and a fragment pasted
        # without it puts a tooltip off the edge of the screen.
        if self.inline_js:
            shell.append(markup(tag.script[Markup(f"\n{REPORT_JS}")]))
        elif self.asset_base:
            src = f"{self.asset_base}/report.js"
            shell.append(markup(htpy.script(src=src, defer=True)))
        # The one pair of tags written out rather than built:
        # a group is a list of lines the caller joins, and the wrapper opens
        # before the first and closes after the last, so there is no element
        # here whose children they are. Both hold nothing from the document,
        # which is what makes writing them safe.
        root = "eta-report" if self.source_brackets else "eta-report no-source-brackets"
        return [*shell, Markup(f'<div class="{root}">'), *group, Markup("</div>")]

    def groups(self, doc: Document) -> list[list[str]]:
        """The report in the groups a split cuts it into: one per `h2` in the body.

        Everything ahead of the first heading goes with the first group,
        and the back matter with the last, which is where they read.

        Cut here rather than out of the finished markup:
        the emitter knows which block is a second-level heading,
        where the markup only knows that some line starts with `<h2 id=`.
        """
        self.restart(doc)
        parts = []
        parts.append(self.phase(doc))
        parts.append(self.masthead(doc))
        parts.append(self.toc(doc))

        groups: list[list[str]] = [[part for part in parts if part]]
        for block, markup in self.chunks(doc.body):
            if isinstance(block, Heading) and block.level == HTML_H2:
                groups.append([])
            if markup:
                groups[-1].append(markup)

        back = [
            part
            for part in (self.footnotes(doc), self.sources(doc), self.contributors(doc))
            if part
        ]
        groups[-1].extend(back)
        return [group for group in groups if group]

    def masthead(self, doc: Document) -> str:
        """The headline, standfirst and dateline, beside the hero where there is room.

        The site's own reports set the title beside the picture on a wide
        screen, so this does too, and the stylesheet stacks them on a phone.

        The warnings come between the dateline and the hero,
        because stacked, the hero fills the screen
        and a warning under it is a warning nobody scrolls to;
        side by side, the stylesheet moves them under both.
        In the fragment as well as the page, so that a report pasted into the
        live site with warnings still on it says so at the top.
        """
        text = tag.div(class_="masthead-text")[
            Markup(self.report_title(doc)),
            Markup(self.standfirst(doc)),
            Markup(self.dateline(doc)),
            Markup(self.pdf_link()),
        ]
        hero = self.blocks([doc.hero] if doc.hero is not None else [])
        return markup(
            tag.div(class_="masthead")[
                "\n",
                text,
                "\n",
                Markup(self.warnings(doc)) if doc.warnings else None,
                Markup(hero) if hero else None,
                "\n",
            ]
        )

    def report_title(self, doc: Document) -> str:
        """The headline, which belongs to the fragment as it does the page."""
        headline = self.inlines(doc.headline) if doc.headline else doc.title
        return markup(tag.h1(id="title")[self.mark("title", "title"), headline])

    def standfirst(self, doc: Document) -> str:
        """The document's `Subtitle`, under the headline, and nothing when it has none."""
        if not doc.subtitle:
            return ""
        return markup(
            tag.p(class_="standfirst", id="subtitle")[
                self.mark("subtitle", "standfirst"), Markup(self.inlines(doc.subtitle))
            ]
        )

    def contributors(self, doc: Document) -> str:
        """Who is credited, in a section at the end, the way ETA credits them.

        Not a byline under the title: a report is the work of most of a chapter,
        and nine names above the first paragraph read as a masthead rather than a credit.

        The names come from `Public Contributors:`, in the order the document lists them,
        because the header block is the one place the credits are maintained.
        No `Public Contributors:` means no section at all.
        """
        names = doc.contributors
        if not names:
            return ""
        return markup(
            tag.section(class_="contributors", id="contributors")[
                "\n",
                tag.h2[self.mark("contributors"), "Contributors"],
                "\n",
                tag.p[CONTRIBUTORS_NOTE],
                "\n",
                tag.ul["\n", lines(tag.li[name] for name in names), "\n"],
                "\n",
            ]
        )

    def phase(self, doc: Document) -> str:
        """What a reader of a draft has to be told before reading it.

        Above the dateline rather than below it, because it qualifies the whole page:
        the date a draft is due says nothing useful
        until you know it is a draft you are holding.
        """
        return phase_markup(doc.phase) if self.inline_phase else ""

    def dateline(self, doc: Document) -> str:
        """When the report published, from `Final Due Date:` in the header.

        Plain text rather than a `<time>`,
        which only carries machine-readable meaning with an ISO stamp:
        `date_text` keeps the string the chip displays and drops the timestamp behind it.
        """
        date = doc.dateline
        if not date:
            return ""
        return markup(tag.p(class_="dateline", id="date")[self.mark("date", "date"), date])

    def pdf_link(self) -> str:
        """A link to the report as a PDF, for a reader who wants to print or keep it."""
        if not self.pdf_href:
            return ""
        return markup(
            tag.p(class_="pdf", id="pdf")[
                tag.a(class_="pdf-button", href=self.pdf_href)[Markup(PDF_ICON), "Download PDF"]
            ]
        )

    def warnings(self, doc: Document) -> str:
        """Everything the build has to say about this report, where it will be read.

        A warning names a field, a file, or a line in backticks,
        rendered as code rather than shown with the backticks in it.
        """
        if not doc.warnings:
            return ""
        return markup(
            tag.div(class_="warnings")[
                tag.strong["Warnings"],
                tag.ul[lines(tag.li[self.marked_up(w)] for w in doc.warnings)],
            ]
        )

    def marked_up(self, warning: Notice) -> str:
        """One warning as HTML: names as code, what gets cut struck through,
        and what the warning is pointing at highlighted inside the value.

        The highlight is what a browser has and a file does not:
        a pair of spaces is a space here, however it is written,
        so the dots say how many there are and the mark says which they are.
        """
        return Markup(
            warning_markup(
                warning,
                code=lambda c: markup(tag.code[c]),
                cut=lambda c: markup(tag.s[c]),
                text=lambda t: markup(t),
                quote=lambda q: markup(tag.blockquote[Markup(q)]),
                bullets=lambda items: markup(tag.ul[[tag.li[Markup(i)] for i in items]]),
                marked=lambda before, mark, after: markup(tag.code[before, tag.mark[mark], after]),
            )
        )

    def toc(self, doc: Document) -> str:
        """The sections, as a list rather than the run of pipe-separated links
        the published report uses, which has nowhere to put a subsection.

        Every heading the page shows is listed, the back matter this emitter
        writes included, rather than the published report's top two levels.

        A document with no headings of its own gets no table of contents:
        a table listing only the footnotes is a link.
        """
        headings = doc.headings()
        if not headings:
            return ""
        headings = headings + self.back_matter(doc)
        return markup(
            tag.nav(class_="toc", id="table-of-contents", aria_label="Table of contents")[
                "\n",
                # Collapsed, so a reader reaches the text without scrolling past
                # every heading first; the summary is the one line left showing.
                tag.details[
                    "\n",
                    # A heading, as the back matter's are, so it reads as one of them.
                    tag.summary[
                        tag.h2[
                            self.mark("table-of-contents", "table of contents"), "Table of Contents"
                        ]
                    ],
                    "\n",
                    self.toc_list(headings),
                    "\n",
                ],
                "\n",
            ]
        )

    def back_matter(self, doc: Document) -> list[Heading]:
        """The sections this emitter appends, as headings a table can list.

        At the top level, so they close the appendices rather than joining them:
        the footnotes are not part of the last section,
        whatever level the document gives that section's neighbours.
        """
        sections = []
        if doc.footnotes:
            sections.append(Heading(level=2, anchor="footnotes", content=[Text("Footnotes")]))
        if doc.sources:
            sections.append(Heading(level=2, anchor="sources", content=[Text("Sources")]))
        if doc.contributors:
            sections.append(Heading(level=2, anchor="contributors", content=[Text("Contributors")]))
        return sections

    def toc_list(self, headings: list[Heading]) -> Tag:
        """The headings as nested lists, one level of nesting per level.

        A heading that skips a level, an `h4` directly under an `h2`,
        opens one list rather than two:
        the empty list a strict reading emits is an indent with nothing in it.
        """
        # The shallowest level rather than the first heading's:
        # a document may open with a subsection, and the outermost list has to
        # hold every heading or the ones above it are left with nowhere to go.
        entries, rest = self.toc_level(headings, min(h.level for h in headings))
        assert not rest, "the outermost list holds every heading"
        return entries

    def toc_level(self, headings: list[Heading], depth: int) -> tuple[Tag, list[Heading]]:
        """A list of everything at `depth` or below, and the headings left over.

        A heading deeper than the one before it opens a list under that entry,
        which this calls itself to build;
        one shallower than `depth` ends this list and is handed back
        to whichever call has a level shallow enough to hold it.
        """
        items: list[Piece] = []
        while headings and headings[0].level >= depth:
            heading, headings = headings[0], headings[1:]
            link = tag.a(href=f"#{heading.anchor}")[plain_text(heading.content)]
            if headings and headings[0].level > heading.level:
                nested, headings = self.toc_level(headings, headings[0].level)
                items.append(tag.li[link, "\n", nested])
            else:
                items.append(tag.li[link])
        return tag.ul["\n", lines(items), "\n"], headings

    def source_ref(self, href: str) -> Piece:
        """The `[12]` after a link, which is the way to its entry in Sources.

        Hovering shows the pair, but a phone has no hover and a printed page
        has no links at all, so the way to the archived copy cannot be the
        tooltip. This is the one that always works.

        Bracketed, where a footnote reference is a bare number: the two ride
        at the same height and there are two numbering schemes on one page, so
        the brackets are what tells `[12]` from footnote 12 at a glance.

        Built as a `sup` around an `a`, the same shape `footnote_ref` writes,
        rather than one `a` carrying both, for the symmetry. (`biome` 2.3.14
        also failed to lay out a long caption with the flatter form, with an
        internal error; 2.5.15 lays out either.)

        Inside the box a reference carries it gets no id and does not count as
        a use: that box is a copy of a note emitted a second time, and the
        note's own citation is the one the backlink has to land on.
        """
        number = self.source_number(href)
        if not number:
            return None
        if self._in_tip:
            return tag.sup(class_="source-ref")[
                tag.a(tabindex="-1", href=f"#src{number}")[f"[{number}]"]
            ]
        use = self._source_uses[href] = self._source_uses.get(href, 0) + 1
        return tag.sup(class_="source-ref", id=f"srcref{number}-{use}")[
            tag.a(href=f"#src{number}")[f"[{number}]"]
        ]

    def sources(self, doc: Document) -> str:
        """Every source the report cites, with the archived copy beside it.

        The original first, because that is what the report read and where the
        page still lives while it lives. The capture after it, because that is
        what is left when it does not.
        """
        if not doc.sources:
            return ""
        uses = doc.source_uses
        items = [
            self.source(number, url, uses.get(url, 1))
            for number, url in enumerate(doc.sources, start=1)
        ]
        return markup(
            tag.section(class_="sources", id="sources")[
                "\n",
                tag.h2[self.mark("sources"), "Sources"],
                "\n",
                tag.ol["\n", lines(items), "\n"],
                "\n",
            ]
        )

    def source(self, number: int, url: str, uses: int) -> Tag:
        """One entry: the ways back to it, its archived copy, and the source.

        Each of the three in a box of its own, so that the list can line them
        up in columns: the arrows, then the archives, then the addresses.
        The archive before the address rather than after it, so that it stays
        beside the arrows where a long address would push it onto a line of its own.

        A source cited once gets a bare arrow, as a footnote does. One cited
        six times gets an arrow per citation, lettered, because an arrow that
        can only return to the first of six is wrong five times.
        """
        back: list[Piece] = []
        for use in range(1, uses + 1):
            mark = "\u2191" if uses == 1 else f"\u2191{ascii_lowercase[use - 1]}"
            where = f"citation {use} of this source" if uses > 1 else "this source"
            back.extend(
                [
                    tag.a(
                        href=f"#srcref{number}-{use}",
                        class_="source-back",
                        aria_label=f"Back to {where} in the text",
                    )[mark],
                    " ",
                ]
            )
        return tag.li(id=f"src{number}")[
            tag.span(class_="source-backs")[back],
            tag.span(class_="source-archived")[self.source_archive(self.doc.archived(url))],
            # A space the grid ignores, and the line of text needs.
            " ",
            tag.a(class_="source-url", href=url)[shown_url(url)],
        ]

    def source_archive(self, archived: Archived | None) -> Piece:
        """What is said about the capture: where it is, or that there is none.

        A source nothing has captured says so rather than saying nothing.
        A link with no archive beside it and a link whose archive failed look
        identical on the page otherwise, and they are not the same thing.
        """
        if archived is None:
            return tag.span(class_="source-none")["(not archived)"]
        if archived.error and archived.version:
            return [
                "(versioned ",
                tag.a(class_="source-archive", href=archived.version)[archived.version_date],
                ")",
            ]
        if archived.error:
            return tag.span(class_="source-none")[f"(not archived: {archived.reason})"]
        return [
            "(archived ",
            tag.a(class_="source-archive", href=archived.snapshot)[archived.date],
            ")",
        ]

    def footnotes(self, doc: Document) -> str:
        if not doc.footnotes:
            return ""
        return markup(
            tag.section(class_="footnotes", id="footnotes")[
                "\n",
                tag.h2[self.mark("footnotes"), "Footnotes"],
                "\n",
                tag.ol["\n", lines(self.footnote(f) for f in doc.footnotes), "\n"],
                "\n",
            ]
        )

    def footnote(self, note: Footnote) -> str:
        back = markup(
            [
                tag.a(
                    href=f"#fnref{note.number}",
                    class_="footnote-back",
                    aria_label=f"Back to footnote {note.number} in the text",
                )["↑"],
                " ",
            ]
        )
        # Inside the note's first paragraph, not before it: a paragraph is a
        # block, so an arrow ahead of one sits on a line of its own with the
        # note beginning underneath.
        # Handed to the paragraph to open with rather than spliced into the
        # markup afterwards, which would mean reading the tree back out of it.
        leads = bool(note.content) and isinstance(note.content[0], Paragraph)
        if leads:
            self._lead = back
        body = self.within(f"fn{note.number}", lambda: self.blocks(note.content))
        # The mark hangs outside the footnote's own number
        # rather than beside the arrow, which it crowded.
        mark = self.mark(f"fn{note.number}", "footnote")
        return markup(tag.li(id=f"fn{note.number}")[mark, None if leads else back, body])

    def tip(self, blocks: list[Block]) -> str:
        """A footnote as it reads, for the box its reference carries.

        Inline markup only, though the note is made of blocks:
        the box lives inside a `sup` inside a paragraph,
        where a `p` of its own would end the paragraph around it,
        so each block becomes a line and the lines are separated by breaks.
        A figure or a table has nothing to say in a line and says nothing.
        """
        shown: list[str] = []
        self._in_tip = True
        for block in blocks:
            match block:
                case Paragraph():
                    shown.append(self.inlines(block.content))
                case List():
                    shown.extend(
                        f"{'•' if block.kind is ListKind.BULLET else f'{n}.'} "
                        f"{self.inlines(item.content)}"
                        for n, item in enumerate(block.items, 1)
                    )
                case _:
                    continue
        self._in_tip = False
        return markup(htpy.fragment[joined(htpy.br, [line for line in shown if line])])

    def tip_text(self, blocks: list[Block]) -> str:
        """A footnote as one line of text, for deciding whether it has a box to show.

        Every kind of markup is dropped: what is being asked is whether the
        note says anything, and `tip` is what renders it once the answer is yes.
        """
        words: list[str] = []
        for block in blocks:
            content: list[Inline] = []
            if isinstance(block, Paragraph):
                content = block.content
            elif isinstance(block, List):
                content = [i for item in block.items for i in item.content]
            for node in content:
                if isinstance(node, Text):
                    words.append(node.text)
                elif isinstance(node, LineBreak):
                    words.append(" ")
            words.append(" ")
        return " ".join("".join(words).split())

    # ---- blocks -----------------------------------------------------

    @override
    def blocks(self, blocks: list[Block]) -> str:
        """Blocks in order, with runs of figures kept together in a row.

        The document has no way to say "these two go side by side",
        but it says they belong together
        by putting them one after another with nothing in between.
        A lone figure is left alone.
        """
        return self.join([markup for _, markup in self.chunks(blocks)])

    def chunks(self, blocks: list[Block]) -> list[tuple[Block, str]]:
        """The same markup, each piece paired with the block it starts at.

        What `blocks` joins, and what a split cuts between.
        A run of figures is one chunk paired with the first of them,
        because cutting into a row would leave half of it at the end of a piece.
        """
        out: list[tuple[Block, str]] = []
        i = 0
        while i < len(blocks):
            run = i
            while run < len(blocks) and isinstance(blocks[run], Figure):
                run += 1
            if run - i > 1:
                row = lines(self.block(b) for b in blocks[i:run])
                out.append((blocks[i], markup(tag.div(class_="figure-row")["\n", row, "\n"])))
                i = run
            else:
                out.append((blocks[i], self.block(blocks[i])))
                i += 1
        return out

    def within(self, scope: str, emit: Callable[[], str]) -> str:
        """`emit()`, with the paragraphs inside it numbered from `scope`.

        A footnote and a table cell are made of paragraphs,
        but they are not passages of the report:
        numbering them along with it would put 43 between 12 and 13.
        """
        was = self._scope, self._paragraphs, self._marked
        # And unmarked:
        # a footnote already has a mark and an arrow back to the text,
        # and a table cell has no margin to hang one in.
        # The ids are still there, for a link written by hand.
        self._scope, self._paragraphs, self._marked = scope, 0, False
        try:
            return emit()
        finally:
            self._scope, self._paragraphs, self._marked = was

    def mark(self, anchor: str, what: str = "section") -> Tag:
        return link_mark(anchor, what)

    def link(self, href: str) -> Tag:
        """An `a` for the prose, opened but not yet given what it holds.

        Inside the box a reference carries, every link is a copy of one the
        note already has, and the note is a jump away: the keyboard should
        walk past the copy rather than stop at it.
        """
        return tag.a(tabindex="-1" if self._in_tip else None, href=href)

    @override
    def heading(self, node: Heading) -> str:
        """Every heading carries a link to itself.

        A section of a report this long is what people send each other,
        and the anchor is already there:
        this only gives the reader something to copy it from.
        """
        # The section every paragraph after this one is numbered within,
        # until the next heading opens the next one.
        self._scope, self._paragraphs = node.anchor, 0
        # The level is a number the document chose, so the element is looked up
        # by name.
        heading = getattr(tag, f"h{node.level}")
        return markup(heading(id=node.anchor)[self.mark(node.anchor), self.inlines(node.content)])

    @override
    def paragraph(self, node: Paragraph) -> str:
        """A paragraph is linkable, because a report this long gets quoted
        a paragraph at a time.
        One holding no text is not: nothing to hash, and nothing anyone would link to."""
        lead, self._lead = self._lead, None
        if not plain_text(node.content):
            return markup(tag.p[lead, self.inlines(node.content)])
        self._paragraphs += 1
        counted = f"{self._scope}-p{self._paragraphs}" if self._scope else f"p{self._paragraphs}"
        anchor = self.take(counted)
        mark = self.mark(anchor, "paragraph") if self._marked else None
        return markup(tag.p(id=anchor)[lead, mark, self.inlines(node.content)])

    @override
    def list_(self, node: List) -> str:
        """The list is linkable; its items are not.

        An item is a line rather than a passage,
        and each would want an id derived from a few words a copy edit moves around."""
        listing = tag.ol if node.kind is ListKind.NUMBER else tag.ul
        text = " ".join(plain_text(item.content) for item in node.items)
        items = listing[self.items(node.items, listing)]
        if not text:
            return markup(items)
        # Wrapped, because a list may hold only list items:
        # the mark cannot be a child of the `ul` the way it is a child of a `p`,
        # and inside the first item it would hang beside that item's bullet.
        anchor = self.anchor("list", text)
        return markup(tag.div(class_="list-block", id=anchor)[self.mark(anchor, "list"), items])

    def items(self, items: list[ListItem], listing: Tag) -> Piece:
        out: list[Piece] = []
        for item in items:
            nested = listing[self.items(item.children, listing)] if item.children else None
            out.append(tag.li[self.inlines(item.content), nested])
        return out

    @override
    def figure(self, node: Figure) -> str:
        # `Figure.source` is not emitted:
        # it names the original file in Drive, for whoever assembles the report,
        # and does not appear on the published page.
        # A figure whose SVG could not be had is published without a picture,
        # never with the raster standing in for it.
        unpublished = node.image.object_id in self.doc.unpublished
        # The caption as the picture's `title` too, which a pointer resting on
        # the picture shows, beside the `alt` that says what is in it.
        title = plain_text(node.caption) if node.caption else None
        parts: list[Piece] = [] if unpublished else [self.image(node.image, title)]
        if node.caption:
            parts.append(tag.figcaption(class_="figure-caption")[self.inlines(node.caption)])
        if node.credit:
            parts.append(tag.figcaption(class_="figure-credit")[self.inlines(node.credit)])
        # The stylesheet reads `--aspect` twice:
        # to divide a line between the figures of a row,
        # and to cap how tall any one figure gets.
        aspect = self.doc.image_aspect(node.image)
        shape = f"--aspect: {aspect:.3f}" if aspect is not None else None
        anchor = self.take(node.image.filename)
        return markup(tag.figure(id=anchor, style=shape)[self.mark(anchor, "figure"), parts])

    @override
    def embed(self, node: Embed, card: Card) -> str:
        """A card for the video or post, which becomes the platform's player when clicked.

        A card rather than the player, so reading the report asks nothing of
        YouTube, X, or Bluesky until the reader does. The card is a link to the
        post, so without the script, or in a reader that strips it, it is still
        the way there. The player's address rides on the figure for the script.

        A video in Drive, or one copied from a `Video (Copy):` line, is served
        from here, so it has nobody to keep out and plays where it is.
        """
        file = self.doc.media_files.get(node.url)
        served = self.doc.served_video(node)
        if served is not None:
            return self.served_video(node, served)
        anchor = self.take(f"embed-{node.platform.value}-{node.key.replace('/', '-')}")
        ref = "" if node.copy else self.source_ref(node.url)
        # In a `cited` of its own, the way a link's is, since that is what the
        # script hangs a source's box off; the card is not in it,
        # because the card's hover is a click away from playing.
        if ref is not None:
            ref = tag.span(class_="cited")[ref]
        # Outside the card, so it stays above the player that replaces the card.
        # A notice rather than a heading: the `#` that links to the embed goes
        # on its name, so the warning is not what the embed reads as called.
        warning = (
            tag.p(class_="embed-warning", role="note")[self.inlines(node.warning)]
            if node.warning
            else None
        )
        what = "post" if node.platform in (Platform.X, Platform.BLUESKY) else "video"
        # The citation follows the name, where there is one, as it follows a link.
        title = (
            tag.figcaption(class_="embed-title")[self.mark(anchor, what), node.title, ref]
            if node.title
            else None
        )
        mark = None if title is not None else self.mark(anchor, what)
        if title is not None:
            ref = None
        # Under the name, as an image's credit is under its caption.
        credit = (
            tag.figcaption(class_="figure-credit")[self.inlines(node.credit)]
            if node.credit
            else None
        )
        where = PLATFORM_NAMES[node.platform]
        picture = None
        if file is not None and Path(file).suffix not in VIDEO_TYPES.values():
            picture = htpy.img(src=self.media_src(file, IMAGE_DIR), alt="", loading="lazy")
        verb = "Play on" if node.platform is Platform.YOUTUBE else "View on"
        card_contents = [
            picture,
            # A post's own line breaks as `br`, since the formatter that lays
            # out the page is free to break the text anywhere else.
            tag.span(class_="embed-text")[joined(htpy.br, card.text.split("\n"))],
            tag.span(class_="embed-meta")[
                tag.span(class_="embed-author")[card.author],
                tag.span(class_="embed-play")[f"{verb} {where}"],
            ],
        ]
        card_link = (
            tag.a(class_="embed-card", href=node.url)[card_contents]
            if not node.copy
            else tag.div(class_="embed-card")[card_contents]
        )
        return markup(
            tag.figure(
                id=anchor,
                class_=f"embed embed-{node.platform.value}"
                + (" embed-vertical" if node.vertical else ""),
                data_player=player_url(node, card) if not node.copy else None,
                data_title=f"{card.author} on {where}",
            )[
                mark,
                warning,
                card_link,
                title,
                credit,
                ref,
            ]
        )

    def served_video(self, node: Embed, file: str) -> str:
        """A video the site serves, a copy or one from Drive, as a figure like an image's.

        Not a stand-in for a post elsewhere, so none of an embed's card or
        styling: its anchor is its file's name, its `#` is on the figure,
        and its name is a caption, as an image's are.
        """
        anchor = self.take(Path(file).stem)
        # A copy is ETA's to show, so nothing points back at the post it came from.
        ref = None if node.copy else self.source_ref(node.url)
        cited = tag.span(class_="cited")[ref] if ref else None
        caption = tag.figcaption(class_="figure-caption")[node.title, cited] if node.title else None
        credit = (
            tag.figcaption(class_="figure-credit")[self.inlines(node.credit)]
            if node.credit
            else None
        )
        warning = (
            tag.p(class_="embed-warning", role="note")[self.inlines(node.warning)]
            if node.warning
            else None
        )
        # A video has no `alt`; its name is what it is labeled by, and what
        # resting the pointer on it shows, as a picture's caption is.
        video = tag.video(
            src=self.media_src(file, VIDEO_DIR),
            title=node.title or None,
            aria_label=node.title or None,
            controls=True,
            preload="metadata",
            poster=self.warning_poster(node.warning_kind) if node.warning else None,
        )[
            self.captions_track(node),
            tag.a(href=node.url)["Watch the video"] if not node.copy else None,
        ]
        return markup(
            tag.figure(id=anchor)[
                self.mark(anchor, "video"),
                warning,
                video,
                caption,
                credit,
                cited if caption is None else None,
            ]
        )

    def warning_poster(self, kind: str) -> str:
        """What a video with a `Warning:` shows until it is played, rather than its first frame:
        ETA's logo beside "WARNING: Graphic Content", as the site's own videos open with.

        From the site's assets, beside the stylesheet; a fragment that carries
        its stylesheet inline links the site's copy, since Squarespace has none.
        The stylesheet fills the rest of a video of another shape with its background.
        """
        base = self.page_assets or self.asset_base or f"{self.site_url}/{ASSET_DIR}"
        return f"{base}/{warning_poster_name(kind)}"

    def captions_track(self, node: Embed) -> Element | None:
        """The captions a copied video came with, labelled as recognized where nobody wrote them."""
        captions = self.doc.media_captions.get(node.url)
        if captions is None:
            return None
        label = "English (automatic)" if captions.automatic else "English"
        return tag.track(
            kind="captions",
            src=self.media_src(captions.file, VIDEO_DIR),
            srclang=CAPTIONS_LANGUAGE,
            label=label,
        )

    def media_src(self, file: str, directory: str) -> str:
        """Where an embed's file is served from, beside the images wherever they are."""
        if not self.image_base:
            return f"{directory}/{file}"
        base = self.image_base.removesuffix(IMAGE_DIR).rstrip("/")
        return f"{base}/{directory}/{file}" if base else f"{directory}/{file}"

    @override
    def table(self, node: Table) -> str:
        text = " ".join(
            plain_text(block.content)
            for row in node.rows
            for cell in row
            for block in cell
            if isinstance(block, Paragraph)
        )
        # The anchor first, because the paragraphs in the cells are numbered
        # within the table rather than the section it sits in.
        anchor = self.anchor("table", text) if text else ""
        rows = self.within(
            anchor,
            lambda: markup(
                [tag.tr[[tag.td[self.blocks(cell)] for cell in row]] for row in node.rows]
            ),
        )
        if not anchor:
            return markup(tag.div(class_="table-scroll")[tag.table[rows]])
        return markup(
            tag.div(class_="table-scroll", id=anchor)[self.mark(anchor, "table"), tag.table[rows]]
        )

    # ---- inline -----------------------------------------------------

    @override
    def text(self, node: Text) -> str:
        out: Piece = node.text
        if node.sup:
            out = tag.sup[out]
        elif node.sub:
            out = tag.sub_[out]
        if node.bold:
            out = tag.strong[out]
        if node.italic:
            out = tag.em[out]
        if node.underline:
            out = tag.u[out]
        if node.href:
            link = self.link(node.href)[out]
            ref = self.source_ref(node.href)
            # Held together in one element rather than set side by side: a
            # citation and the link it is of do not wrap apart.
            # (`biome` 2.3.14 also failed with an internal error laying out a
            # `sup` welded to the end of a link long enough to need breaking;
            # 2.5.15 does not.)
            out = tag.span(class_="cited")[link, ref] if ref is not None else link
        return markup(out)

    @override
    def line_break(self, node: LineBreak) -> str:
        return markup(htpy.br)

    @override
    def footnote_ref(self, node: FootnoteRef) -> str:
        # A footnote can itself carry a reference to another one.
        # Inside a box there is nothing to hover, and a note that reaches
        # itself would build a box out of a box without end.
        if self._in_tip:
            return markup(
                tag.sup(class_="footnote-ref")[self.link(f"#fn{node.number}")[node.number]]
            )
        # Matched by the Docs id rather than by the number,
        # which is the identity the parser guarantees on both sides.
        note = next(
            (f for f in self.doc.footnotes if f.footnote_id == node.footnote_id),
            None,
        )
        # A footnote that is a table or a figure has no sentence to show,
        # and an empty box hovering over the text is worse than none.
        tip = self.tip(note.content) if note and self.tip_text(note.content) else ""
        preview = tag.span(class_="footnote-tip", aria_hidden="true")[tip] if tip else None
        return markup(
            tag.sup(id=f"fnref{node.number}", class_="footnote-ref")[
                tag.a(href=f"#fn{node.number}")[node.number], preview
            ]
        )

    @override
    def image(self, node: Image, title: str | None = None) -> str:
        """The picture, at the size of the file that was written.

        `width` and `height` are the file's own pixels, not how wide it is
        shown: the stylesheet still lays it out at `width: 100%`, and what the
        two attributes give the browser is the shape, so it can leave the right
        gap before the file arrives.

        Without them an image is zero pixels tall until it loads, and with 29
        of them loading lazily the report is 1,280 pixels shorter than it will
        be. A reader who opens `#src50` lands where that anchor was before the
        pictures pushed it down.

        An SVG has no pixel size to read, so it is the one this cannot say
        anything about.

        Every picture loads lazily but the hero, which is the first thing on
        the screen: a lazy image is not asked for until the page is laid out
        and it is found to be in view, which for the one picture certain to be
        in view is only a delay. It is asked for first instead.

        A raster is shown through `picture`, from the AVIF and WebP copies at
        `WEB_WIDTHS` that `images.write_web_copies` writes, and is a link to
        the file as the document holds it, for whoever wants to zoom in.
        `sizes` is how wide the stylesheet lets the figure get, so a phone is
        sent the narrow copy; in a row of several it overstates, which costs a
        wider copy than needed and never a blurry one.
        """
        href = self.doc.image_href(node)
        src = f"{self.image_base}/{href}" if self.image_base else href
        shape = self.doc.image_shapes.get(node.object_id)
        width, height = shape if shape else (None, None)
        hero = self.doc.hero is not None and self.doc.hero.image is node
        if width is None or height is None or not has_web_copies(href):
            return markup(
                htpy.img(
                    src=src,
                    alt=node.alt,
                    title=title,
                    loading=None if hero else "lazy",
                    fetchpriority="high" if hero else None,
                    width=width,
                    height=height,
                )
            )
        widths = web_widths(width)

        def copy(w: int, extension: str) -> str:
            name = web_href(href, w, extension)
            return f"{self.image_base}/{name}" if self.image_base else name

        shown = min(46.0, width / height * 34)
        sizes = f"min(100vw, {shown:.1f}rem)"
        sources = [
            htpy.source(
                type=f"image/{extension}",
                srcset=", ".join(f"{copy(w, extension)} {w}w" for w in widths),
                sizes=sizes,
            )
            for extension in WEB_FORMATS
        ]
        largest = widths[-1]
        img = htpy.img(
            src=copy(largest, WEB_FORMATS[-1]),
            alt=node.alt,
            title=title,
            loading=None if hero else "lazy",
            fetchpriority="high" if hero else None,
            width=largest,
            height=round(height * largest / width),
        )
        return markup(tag.a(class_="full-size", href=src)[htpy.picture[[*sources, img]]])


# Enough to read the report as it will look, and nothing more.
# A page pasted into Squarespace inherits that site's typography,
# so matching it here would be a guess that goes stale.
PAGE_CSS = read("page.css")


def report_page(
    doc: Document,
    image_base: str = IMAGE_DIR,
    asset_base: str = ASSET_DIR,
    pdf_href: str = "",
    card_base: str = "",
    page_url: str = "",
    source_brackets: bool = False,
) -> str:
    """The whole report as a page,
    which is what a build writes as `index.html` and what the site serves.

    Not the fragment with a wrapper bolted on:
    `report.html` is a `div` to paste into a Squarespace code block,
    which inherits the site's typography and has nowhere to put a warning.

    `card_base` is where the site serves the images, as a URL:
    a link preview fetches the card from wherever the link was posted,
    so `og:image` has to be absolute, and a relative one shows no picture at all.
    `page_url` is this page's own address, as `og:url`: the site's copy, not `etany.org`,
    so that a preview of a draft stays a preview of the draft.
    """
    body = HtmlEmitter(
        image_base=image_base,
        inline_css=False,
        inline_js=False,
        inline_phase=False,
        pdf_href=pdf_href,
        source_brackets=source_brackets,
        page_assets=asset_base,
    ).emit(doc)
    # The share card is what a link to the report unfurls as, and the only place it appears:
    # a picture of the title, which a reader who has arrived does not need.
    card: list[Piece] = []
    # What Squarespace previews in a search result, as its page settings show it.
    description = doc.meta.get("SEO Description", "")
    if doc.card is not None:
        href = doc.image_href(doc.card)
        base = card_base or image_base
        src = f"{base}/{href}" if base else href
        card.append(htpy.meta(property="og:image", content=src))
        # So a preview can lay the card out before it has fetched it,
        # which is what a first share of a link gets otherwise: no picture.
        size = doc.image_shapes.get(doc.card.object_id)
        if size is not None:
            card.append(htpy.meta(property="og:image:width", content=str(size[0])))
            card.append(htpy.meta(property="og:image:height", content=str(size[1])))
        if doc.card.alt:
            card.append(htpy.meta(property="og:image:alt", content=doc.card.alt))
        # The card across the whole preview rather than as a small square beside it,
        # which is what X shows without this.
        card.append(htpy.meta(name="twitter:card", content="summary_large_image"))
    head: list[Piece] = [
        htpy.meta(charset="utf-8"),
        htpy.meta(name="viewport", content="width=device-width, initial-scale=1"),
        # Until the reports are published, nothing here should be findable.
        # `robots.txt` only asks a crawler not to fetch a page,
        # which leaves one already indexed where it is;
        # `noindex` is what takes it back out,
        # and it is the only one of the two that a project page can carry at all,
        # since `robots.txt` is read from the root of the host
        # and these pages are served from a path under it.
        # Remove this, and `site/unpublished/robots.txt`, when the reports go out.
        htpy.meta(name="robots", content="noindex, nofollow"),
        tag.title[doc.title],
        htpy.meta(name="description", content=description),
        # What a link to the report unfurls as, beside the card's picture.
        htpy.meta(property="og:type", content="article"),
        htpy.meta(property="og:site_name", content="Effective Transit Alliance"),
        *([htpy.meta(property="og:url", content=page_url)] if page_url else []),
        htpy.meta(property="og:title", content=doc.title),
        htpy.meta(property="og:description", content=description),
        *card,
        # Linked rather than inlined: every report page carries the same
        # stylesheets and the same script, and `asset_base` is where the
        # build put the one copy, relative to this page.
        *(
            htpy.link(rel="stylesheet", href=f"{asset_base}/{name}")
            for name in ("page.css", "report.css")
        ),
        htpy.script(src=f"{asset_base}/report.js", defer=True),
        *([Markup(phase_markup(doc.phase))] if doc.phase else []),
    ]
    # `<!doctype html>` is not an element and no builder emits one.
    return markup([Markup("<!doctype html>"), "\n", lines(head), "\n", Markup(body), "\n"])
