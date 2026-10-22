"""Markdown for the committed, diffable archive.

Pandoc-flavored, because CommonMark has no footnotes and these publications run on them.
Where Pandoc and GitHub disagree, GitHub wins:
this file is read in the repository,
and GitHub supports the footnotes that made Pandoc necessary in the first place.

This is not what gets published.
It exists so that every regeneration lands in git as a readable diff:
what changed between draft 6 and draft 7, what the August 21 addendum added.
That is why the output breaks lines at sentences (see `sentences.py`).

The same publication as the page and the PDF, not a different view of it:
the same headline, standfirst, date, and hero, in the same order,
and the same contributors at the end.
The header block is not here.
It is production scaffolding, `Draft Due Date:` and a discussion channel,
and `doc.json` beside this file keeps every field verbatim.
"""

import re
from pathlib import PurePosixPath
from typing import override

from ..naming import ASSET_DIR, IMAGE_DIR, VIDEO_DIR, video_frame_name, warning_poster_name
from ..nodes import (
    Card,
    Document,
    Embed,
    Figure,
    Footnote,
    FootnoteRef,
    Heading,
    Image,
    LineBreak,
    List,
    ListItem,
    ListKind,
    Notice,
    Paragraph,
    Table,
    Text,
)
from ..sentences import split
from .base import CONTRIBUTORS_NOTE, Emitter, embed_label, shown_url, warning_markup


def fence(value: str) -> str:
    """`value` as a Markdown code span, whatever backticks it holds.

    A span is delimited by a run of backticks longer than any run inside it,
    which is what lets a value carrying one be shown rather than escaped.
    A value starting or ending with a backtick takes a space either side,
    which Markdown strips back off.
    """
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    ticks = "`" * (longest + 1)
    padding = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{ticks}{padding}{value}{padding}{ticks}"


# Characters that would otherwise be read as Markdown syntax.
# Escaping is minimal: over-escaping makes the archive harder to read by hand,
# which is most of the point of having it.
ESCAPE = re.compile(r"([\\`*_\[\]|])")


def escape(text: str) -> str:
    return ESCAPE.sub(r"\\\1", text)


def url(href: str) -> str:
    """A link destination, angle-bracketed so parentheses cannot end it.

    These publications cite heavily, and plenty of real URLs contain brackets:
    Wikipedia disambiguation paths, agency PDF links.
    Bare, the first `)` closes the link and the rest of the URL lands in the prose.
    The angle-bracket form is always valid, so it is used unconditionally.
    """
    return "<" + href.replace("<", "%3C").replace(">", "%3E") + ">"


def strip_trailing_space(text: str) -> str:
    """Drop whitespace at the end of every line.

    Two trailing spaces mean a hard line break and any other number means nothing,
    so linters reject the in-between cases, which the document leaves behind
    wherever a sentence ends in one.
    Nothing is lost: a hard break here is a trailing backslash.
    """
    return "\n".join(line.rstrip() for line in text.split("\n"))


class MarkdownEmitter(Emitter):
    extension = ".md"

    # A blank line between blocks, which is Markdown's block separator.
    separator = "\n\n"

    def __init__(self, image_dir: str = IMAGE_DIR) -> None:
        """`image_dir` is relative to the `.md`, which sits beside it.

        Not a published URL prefix:
        the archive is read from the repository, where the files sit next to it,
        rather than from whatever host serves the site.
        """
        super().__init__()
        self.image_dir = image_dir.rstrip("/")

    def href(self, image: Image) -> str:
        name = self.doc.image_href(image)
        return f"{self.image_dir}/{name}" if self.image_dir else name

    @override
    def document(self, doc: Document) -> str:
        parts = [
            self.phase(doc),
            self.title(doc),
            self.dateline(doc),
            self.warnings(doc),
            self.blocks([doc.hero] if doc.hero is not None else []),
            self.blocks(doc.body),
            self.footnotes(doc),
            self.sources(doc),
            self.contributors(doc),
        ]
        return strip_trailing_space(self.join(parts)) + "\n"

    def title(self, doc: Document) -> str:
        """The headline, and the standfirst under it, as the page has them.

        `#` is free: the document's own sections are `##`,
        because the tree counts the title as the level above them.
        """
        if not doc.title:
            return ""
        heading = f"# {escape(doc.title)}"
        # A subtitle that finishes the headline is already in `title`,
        # and a heading cannot end in the colon that splits them.
        if not doc.subtitle or doc.subtitle_ends_title:
            return heading
        return f"{heading}\n\n{self.inlines(doc.subtitle)}"

    def phase(self, doc: Document) -> str:
        """Bold, because the archive has no styling to give it and it is a warning.

        Ahead of the headline, and labelled, because a bare state on its own line
        reads as part of the publication rather than as a note about it.
        """
        return f"**Phase: {escape(doc.phase)}**" if doc.phase else ""

    def warnings(self, doc: Document) -> str:
        """The build's notes about this publication, above it and below the dateline.

        Rendered from the warning's pieces rather than from what `str` makes of
        them, as the other two emitters do: a value is marked because it is a
        value, not because of what it happens to contain.
        """
        if not doc.warnings:
            return ""
        # A warning quotes with `> ` and lists with `- `, which Markdown reads
        # as a quotation and a list only when indented into the item they
        # belong to.
        notes = "\n".join(f"- {self.marked_up(w)}".replace("\n", "\n  ") for w in doc.warnings)
        return f"**Warnings**\n\n{notes}"

    def marked_up(self, warning: Notice) -> str:
        """One warning as Markdown: names as code, and what gets cut struck through."""
        return warning_markup(
            warning,
            code=fence,
            cut=lambda c: f"~~{escape(c)}~~",
            text=escape,
            quote=lambda q: f"\n> {q}",
            bullets=lambda items: "".join(f"\n- {item}" for item in items),
        )

    def dateline(self, doc: Document) -> str:
        """When the publication went out, as the page and the PDF date it."""
        return escape(doc.dateline)

    def contributors(self, doc: Document) -> str:
        """Credited at the end, as they are on the page.

        The front matter above carries `public contributors` as the header writes it,
        which is the field. This is the credit, in the order it publishes in.
        """
        names = doc.contributors
        if not names:
            return ""
        listed = "\n".join(f"- {name}" for name in names)
        return f"## Contributors\n\n{CONTRIBUTORS_NOTE}\n\n{listed}"

    def sources(self, doc: Document) -> str:
        """Every source the publication cites, with the archived copy beside it.

        A heading of its own, unlike the footnotes: those are a thing the
        format provides and collects under a rule, and this is a section the
        publication has.

        Numbered, and nothing more: a Markdown file has no anchors to hang a
        backlink on that GitHub will honour, so the number in the text and the
        number in this list are the whole of the connection, which is how a
        bibliography has always worked.
        """
        if not doc.sources:
            return ""
        items = [
            f"{n}. {self.source(doc, source)}" for n, source in enumerate(doc.sources, start=1)
        ]
        return "## Sources\n\n" + "\n".join(items)

    def source(self, doc: Document, source: str) -> str:
        """One entry: where the source is archived, or that it is not, then the source."""
        shown = f"[{escape(shown_url(source))}]({url(source)})"
        archived = doc.archived(source)
        if archived is None:
            return f"(not archived) {shown}"
        if archived.error and archived.version:
            return f"(versioned [{archived.version_date}]({url(archived.version)})) {shown}"
        if archived.error:
            return f"(not archived: {escape(archived.reason)}) {shown}"
        return f"(archived [{archived.date}]({url(archived.snapshot)})) {shown}"

    def source_ref(self, href: str) -> str:
        """The `[12]` after a link, which is its number in Sources.

        Escaped, because a bare `[12]` beside a link is Markdown's own
        reference-link syntax and would resolve to nothing.
        """
        number = self.source_number(href)
        if not number:
            return ""
        return f"<sup>\\[{number}\\]</sup>"

    def footnotes(self, doc: Document) -> str:
        """The notes themselves, with no heading over them.

        Pandoc and GitHub both collect these at the end under a rule of their own,
        and both build a table of contents from the headings.
        What the format provides, this does not write again.
        """
        return self.join([self.footnote(f) for f in doc.footnotes])

    def footnote(self, note: Footnote) -> str:
        body = self.blocks(note.content)
        # Pandoc continues a footnote across lines when they are indented,
        # so a multi-sentence note keeps its line-per-sentence shape.
        indented = body.replace("\n", "\n    ")
        return f"[^{note.number}]: {indented}"

    # ---- blocks -----------------------------------------------------

    @override
    def heading(self, node: Heading) -> str:
        """Just the heading, with no explicit identifier.

        Pandoc's `{#anchor}` syntax would match the published anchors,
        but GitHub, which is where this file is read, has no attribute syntax
        and renders it as literal text in the heading.
        """
        return f"{'#' * node.level} {self.inlines(node.content)}"

    @override
    def paragraph(self, node: Paragraph) -> str:
        return self.wrap(self.inlines(node.content))

    def wrap(self, text: str) -> str:
        """One line per sentence, so a one-word fix is a one-line diff."""
        return "\n".join(split(text))

    @override
    def list_(self, node: List) -> str:
        return self.items(node.items, node.kind, depth=0)

    def items(self, items: list[ListItem], kind: ListKind, depth: int) -> str:
        lines = []
        for n, item in enumerate(items, start=1):
            marker = f"{n}." if kind is ListKind.NUMBER else "-"
            indent = "  " * depth
            lines.append(f"{indent}{marker} {self.inlines(item.content)}")
            if item.children:
                lines.append(self.items(item.children, kind, depth + 1))
        return "\n".join(lines)

    @override
    def figure(self, node: Figure) -> str:
        """Unlike the published outputs, the archive keeps the `Source:` line.

        It records which file in Drive an image came from, and nothing here is published.
        """
        # Caption and credit are their own lines rather than emphasized:
        # the live publication italicizes neither,
        # and marking them up would put styling in the archive that the publication lacks.
        caption = self.inlines(node.caption)
        # Published without a picture, as in the HTML, where its SVG could not be had.
        lines = (
            []
            if node.image.object_id in self.doc.unpublished
            else [f"![{escape(node.image.alt)}]({url(self.href(node.image))})"]
        )
        if caption:
            lines.append(caption)
        if node.credit:
            lines.append(self.inlines(node.credit))

        # A bare newline is a soft break, which would run the picture, its
        # caption and its credit together on one line.
        # No break before the source line, which is a comment and renders as
        # nothing, so the break would be one to nowhere.
        out = "\\\n".join(lines)
        if node.source:
            out += f"\n<!-- {self.inlines(node.source)} -->"
        return out

    @override
    def embed(self, node: Embed, card: Card) -> str:
        # Nothing here plays anything, so the embed is what it says,
        # linked to where it does play.
        served = self.doc.served_video(node)
        if served is not None:
            return self.served_video(node, served)
        return self.linked_embed(node, embed_label(node, card))

    def served_video(self, node: Embed, file: str) -> str:
        """A video the site serves, as the page shows it before it plays:
        its warning as a quote, the nearest Markdown has to the page's notice,
        then the warning card or else its first frame, linked to the video,
        and its name and credit under it like a picture's caption.
        """
        href = url(f"{VIDEO_DIR}/{file}")
        if node.warning:
            # The page's own card, in the site's assets, which a published copy carries.
            up = "../" * len(PurePosixPath(self.doc.slug.strip("/")).parts)
            poster = f"{up}{ASSET_DIR}/{warning_poster_name(node.warning_kind)}"
            alt = f"WARNING: {node.warning_kind}"
        else:
            poster = f"{self.image_dir}/{video_frame_name(file)}"
            alt = node.title or "Video"
        # Ours, so named as the document names it and linked to our copy.
        cite = "" if node.copy else self.source_ref(node.url)
        lines = [
            f"[![{escape(alt)}]({url(poster)})]({href})",
            f"[{escape(node.title or 'Video')}]({href}){cite}",
            *([self.inlines(node.credit)] if node.credit else []),
        ]
        figure = "\\\n".join(lines)
        if not node.warning:
            return figure
        written = "".join(i.text for i in node.warning if isinstance(i, Text)).strip()
        return self.join([f"> ⚠ **{escape(written)}**", figure])

    @override
    def table(self, node: Table) -> str:
        if not node.rows:
            return ""
        rows = [[" ".join(self.blocks(cell).split()) for cell in row] for row in node.rows]
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        # Markdown tables require a header row, so the first one serves.
        header, *body = rows
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        lines += ["| " + " | ".join(r) + " |" for r in body]
        return "\n".join(lines)

    # ---- inline -----------------------------------------------------

    @override
    def text(self, node: Text) -> str:
        # The run's own edge whitespace goes outside its markers.
        # `**done: **` is not bold: a `**` after a space cannot close,
        # so the asterisks are printed, as SAS West's August 21 note was.
        # A link keeps its text to the words, too, rather than `[saving ]`.
        # A run that is only whitespace is written plain, since `** **` would print too.
        if not node.text.strip():
            return node.text
        core = node.text.strip()
        lead, _, rest = node.text.partition(core)
        out = escape(core)
        # HTML rather than Pandoc's `^x^` and `~x~`, which both accept.
        # GitHub renders `^x^` literally and `~x~` as strikethrough, which is wrong.
        if node.sup:
            out = f"<sup>{out}</sup>"
        elif node.sub:
            out = f"<sub>{out}</sub>"
        if node.bold:
            out = f"**{out}**"
        if node.italic:
            out = f"*{out}*"
        if node.href:
            out = f"[{out}]({url(node.href)}){self.source_ref(node.href)}"
        return f"{lead}{out}{rest}"

    @override
    def line_break(self, node: LineBreak) -> str:
        # A backslash is the unambiguous hard break;
        # two trailing spaces are invisible and get stripped by anything tidying whitespace.
        return "\\\n"

    @override
    def footnote_ref(self, node: FootnoteRef) -> str:
        return f"[^{node.number}]"

    @override
    def image(self, node: Image) -> str:
        return f"![{escape(node.alt)}]({url(self.href(node))})"
