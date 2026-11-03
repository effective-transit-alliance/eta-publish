"""Typst source, compiled to the publication PDF.

Typst rather than HTML-to-PDF because footnotes belong at the bottom of the page.
HTML can only place them at the end of the document,
and with 21 of them carrying real argument,
that is the difference between a publication and a printout of a web page.

A footnote's body is inlined at the reference site, which is how Typst wants it:
`#footnote[...]` marks the spot and carries the text,
and Typst does the numbering and the placement.
Nothing here keeps a separate list in sync,
which is the failure the HTML output has to guard against explicitly.

The emitted file is a document body that imports `template.typ`,
which carries the house style.
"""

import json
import re
from pathlib import Path
from typing import override

from ..naming import (
    IMAGE_DIR,
    PRINT_DIR,
    VIDEO_DIR,
    print_href,
    video_frame_name,
    warning_poster_name,
)
from ..nodes import (
    Card,
    Document,
    Embed,
    Figure,
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
from .base import Emitter, contributors_note, embed_label, shown_url, warning_markup

# Typst's markup characters.
# `#` and `@` start code and references, and the rest delimit markup,
# so any of them in prose has to be escaped.
ESCAPE = re.compile(r"([\\#$*_`<>@\[\]])")


def escape(text: str) -> str:
    return ESCAPE.sub(r"\\\1", text)


BREAKS = re.compile(r"(?<=[&=,?+])|(?=%)")
"""Where an address can break besides the `/` Typst already breaks it at:
a query string can run longer than a line with no `/` in it at all."""


def breakable(url: str) -> str:
    """`url` escaped, in pieces a line may break between.

    Each piece is a `box`, since Typst may break a line between two boxes.
    Not a zero-width space, which would be in the PDF's text,
    so an address copied out of the PDF would carry it into the browser.
    """
    pieces = [piece for piece in BREAKS.split(url) if piece]
    if len(pieces) == 1:
        return escape(url)
    return "".join(f"#box[{escape(piece)}]" for piece in pieces)


def string(value: str) -> str:
    """A Typst string literal.

    `json.dumps` rather than a pair of `replace` calls:
    a JSON string and a Typst one are quoted and escaped the same way,
    and this one has been tested by more people than we will ever test ours.
    `ensure_ascii=False` keeps the text readable and avoids `\\uXXXX`,
    which JSON writes and Typst does not spell that way.
    """
    return json.dumps(value, ensure_ascii=False)


class TypstEmitter(Emitter):
    extension = ".typ"

    # A blank line between blocks, as Typst separates them.
    separator = "\n\n"

    def __init__(
        self,
        template: str = "template.typ",
        image_dir: str = PRINT_DIR,
        page_url: str = "",
        *,
        site_url: str,
    ) -> None:
        super().__init__()
        self.template = template
        # Where the site serves what the PDF links: the pictures and videos at full size.
        self.site_url = site_url
        # The live page, for a video to open on its figure there; empty where there is none.
        self.page_url = page_url
        self.image_dir = image_dir.rstrip("/")

    @override
    def document(self, doc: Document) -> str:
        """The header block as written, plus what the page publishes.

        Only the fields something renders are passed, one argument each:
        the header also carries a private contributor list and the project's
        internal dates and channels, and this file is committed.
        """
        header = (
            f"#import {string(self.template)}: capped_image, publication, video_warning\n\n"
            f"#show: publication.with(\n"
            f"  title: {string(doc.title)},\n"
            f"  headline: [{self.inlines(doc.headline) if doc.headline else escape(doc.title)}],\n"
            f"  subtitle: {f'[{self.inlines(doc.subtitle)}]' if doc.subtitle else 'none'},\n"
            f"  phase: {string(doc.phase)},\n"
            f"  dateline: {string(doc.dateline)},\n"
            f"  contributors: ({self.contributors(doc)}),\n"
            f"  contributors_note: {string(contributors_note(doc))},\n"
            f"{self.warnings(doc)}"
            f"{self.hero(doc)}"
            f")\n"
        )
        return header + "\n" + self.join([self.blocks(doc.body), self.sources(doc)]) + "\n"

    def hero(self, doc: Document) -> str:
        """The opening figure, passed to the template rather than emitted.

        It belongs above the outline, with the title,
        and the template knows where the outline goes.
        """
        if doc.hero is None:
            return ""
        return f"  hero: [\n{self.blocks([doc.hero])}\n  ],\n"

    def warnings(self, doc: Document) -> str:
        """The build's notes about this publication, for the template to place.

        A warning marks a name with backticks, which Typst also spells with backticks,
        so the message is escaped around them and its names come out as raw.
        """
        if not doc.warnings:
            return ""
        notes = "".join(f"    [{self.marked_up(w)}],\n" for w in doc.warnings)
        return f"  warnings: (\n{notes}  ),\n"

    def marked_up(self, warning: Notice) -> str:
        """One warning as Typst content: names as raw, and what gets cut struck through."""
        return warning_markup(
            warning,
            code=lambda c: f"#raw({string(c)})",
            cut=lambda c: f"#strike[{escape(c)}]",
            text=escape,
            quote=lambda q: f"#quote(block: true)[{q}]",
            bullets=lambda items: "#list(" + "".join(f"[{i}], " for i in items) + ")",
        )

    def contributors(self, doc: Document) -> str:
        """The credited names as a Typst array, so the template can list them."""
        return "".join(f"{string(name)}, " for name in doc.contributors)

    # ---- blocks -----------------------------------------------------

    def sources(self, doc: Document) -> str:
        """Every source the publication cites, with the archived copy beside it.

        A real section with real links: a PDF is the output most likely to
        outlive the pages it cites, and the one a reader cannot hover.
        Each entry carries a label, so the `[12]` in the text is a jump rather
        than a number to go looking for.
        """
        if not doc.sources:
            return ""
        items = [
            f"+ {self.source(doc, source)} <src{n}>"
            for n, source in enumerate(doc.sources, start=1)
        ]
        # Ragged and unhyphenated: justifying a line that a long address
        # ends stretches its spaces wide, and a hyphen inside an address
        # reads as part of it.
        body = "\n".join(items)
        return f"= Sources\n\n#[\n#set par(justify: false)\n#set text(hyphenate: false)\n{body}\n]"

    def source(self, doc: Document, source: str) -> str:
        """One entry: where the source is archived, or that it is not, then the source."""
        shown = f"#link({string(source)})[{breakable(shown_url(source))}]"
        archived = doc.archived(source)
        if archived is None:
            return f"(not archived) {shown}"
        if archived.error and archived.version:
            link = f"#link({string(archived.version)})[{escape(archived.version_date)}]"
            return f"(versioned {link}) {shown}"
        if archived.error:
            return f"(not archived: {escape(archived.reason)}) {shown}"
        return f"(archived #link({string(archived.snapshot)})[{escape(archived.date)}]) {shown}"

    def source_ref(self, href: str) -> str:
        """The `[12]` after a link, which jumps to its entry in Sources."""
        number = self.source_number(href)
        if not number:
            return ""
        return f"#super[#link(<src{number}>)[\\[{number}\\]]]"

    @override
    def heading(self, node: Heading) -> str:
        # Typst counts heading depth from 1,
        # where the tree counts the title as level 1 and the first section as 2.
        return f"{'=' * (node.level - 1)} {self.inlines(node.content)}"

    @override
    def paragraph(self, node: Paragraph) -> str:
        return "\n".join(split(self.inlines(node.content)))

    @override
    def list_(self, node: List) -> str:
        return self.items(node.items, node.kind, depth=0)

    def items(self, items: list[ListItem], kind: ListKind, depth: int) -> str:
        marker = "+" if kind is ListKind.NUMBER else "-"
        lines = []
        for item in items:
            lines.append(f"{'  ' * depth}{marker} {self.inlines(item.content)}")
            if item.children:
                lines.append(self.items(item.children, kind, depth + 1))
        return "\n".join(lines)

    @override
    def figure(self, node: Figure) -> str:
        # As in the HTML, `Figure.source` is not emitted:
        # it names a file in Drive for whoever assembles the publication.
        caption_parts = []
        if node.caption:
            caption_parts.append(self.inlines(node.caption))
        if node.credit:
            caption_parts.append(self.inlines(node.credit))
        # The credit on its own line, as the document writes it and the page
        # shows it. Joined with a space it reads as part of the caption.
        caption = " \\\n  ".join(caption_parts)
        # Published without a picture, as in the HTML, where its SVG could not be had.
        unpublished = node.image.object_id in self.doc.unpublished
        body = "  []," if unpublished else f"  {self.image_call(node.image)},"
        if caption:
            return f"#figure(\n{body}\n  caption: [{caption}],\n)"
        return f"#figure(\n{body}\n)"

    @override
    def embed(self, node: Embed, card: Card) -> str:
        # Nothing here plays anything, so the embed is what it says,
        # linked to where it does play.
        served = self.doc.served_video(node)
        if served is not None:
            # Ours, so named as the document names it and linked to our copy.
            slug = self.doc.slug.strip("/")
            href = f"{self.site_url}/{slug}/{VIDEO_DIR}/{served}" if slug else ""
            if self.page_url:
                # Its figure on the live page, which the page names after the file,
                # so the warning and the captions come before the video does.
                href = f"{self.page_url}#{Path(served).stem}"
            return self.served_video(node, served, href)
        return self.linked_embed(node, embed_label(node, card))

    def served_video(self, node: Embed, file: str, href: str) -> str:
        """A video the site serves, as the page shows it before it plays:
        its warning and the warning card, or else its first frame,
        captioned with its name and credit like a picture.

        Kept to one page, so a page never ends between the warning and what it warns of.
        """
        warning = ""
        if node.warning:
            written = "".join(i.text for i in node.warning if isinstance(i, Text)).strip()
            warning = f"#video_warning[{escape(written)}]\n\n"
            poster = f"{self.image_dir}/{warning_poster_name(node.warning_kind)}"
            alt = f"WARNING: {node.warning_kind}"
        else:
            # Beside the pictures rather than their print copies, since the page shows it too.
            poster = f"{IMAGE_DIR}/{video_frame_name(file)}"
            alt = node.title or "Video"
        call = f"capped_image({string(poster)}, alt: {string(alt)})"
        body = f"link({string(href)})[#{call}]" if href else call
        # Named as the page's caption names it, and linked, since the poster is all that is here.
        title = escape(node.title or "Video")
        name = f"#link({string(href)})[{title}]" if href else title
        cite = "" if node.copy else self.source_ref(node.url)
        caption = " \\\n  ".join(
            [name + cite, *([self.inlines(node.credit)] if node.credit else [])]
        )
        figure = f"#figure(\n  {body},\n  caption: [{caption}],\n)"
        if not warning:
            return figure
        return f"#block(breakable: false)[\n{warning}{figure}\n]"

    @override
    def table(self, node: Table) -> str:
        if not node.rows:
            return ""
        columns = max(len(row) for row in node.rows)
        cells: list[str] = []
        for row in node.rows:
            padded = list(row) + [[]] * (columns - len(row))
            cells += [f"  [{' '.join(self.blocks(cell).split())}]," for cell in padded]
        body = "\n".join(cells)
        return f"#table(\n  columns: {columns},\n{body}\n)"

    # ---- inline -----------------------------------------------------

    @override
    def text(self, node: Text) -> str:
        out = escape(node.text)
        if node.sup:
            out = f"#super[{out}]"
        elif node.sub:
            out = f"#sub[{out}]"
        if node.bold:
            out = f"#strong[{out}]"
        if node.italic:
            out = f"#emph[{out}]"
        if node.underline:
            out = f"#underline[{out}]"
        if node.href:
            out = f"#link({string(node.href)})[{out}]{self.source_ref(node.href)}"
        return out

    @override
    def line_break(self, node: LineBreak) -> str:
        return " \\\n"

    @override
    def footnote_ref(self, node: FootnoteRef) -> str:
        """Typst places and numbers footnotes itself, so the body goes here."""
        note = next((f for f in self.doc.footnotes if f.number == node.number), None)
        if note is None:
            self.doc.warn(f"footnote {node.number} has no definition; omitted from the PDF")
            return ""
        body = " ".join(self.blocks(note.content).split())
        return f"#footnote[{body}]"

    @override
    def image(self, node: Image) -> str:
        return f"#{self.image_call(node)}"

    def image_call(self, node: Image) -> str:
        """The `image` call, which a figure wraps and a bare image does not.

        Written once so the two cannot drift:
        alt text added here once reached inline images only,
        because the figure built its own call.
        """
        href = self.doc.image_href(node)
        # The PDF embeds its own copy and links the document's:
        # what is on the page is what fits in a PDF, and what the link opens
        # is the picture itself, which is the reason for the link.
        path = f"{self.image_dir}/{print_href(href)}"
        alt = f", alt: {string(node.alt)}" if node.alt else ""
        # `capped_image` rather than `image`: the width is the column's,
        # except for a picture tall enough to break the page it opens.
        call = f"capped_image({string(path)}{alt})"
        url = self.image_url(href)
        if not url:
            return call
        # The picture in the PDF is the page's copy, and a reader who wants to
        # read a diagram rather than look at one needs the file itself.
        # A content block, so the call inside it is markup and takes its `#`;
        # the caller prepends the one this whole expression needs.
        return f"link({string(url)})[#{call}]"

    def image_url(self, href: str) -> str:
        """Where this image is published, for the PDF to link to.

        Empty for a document that names no `URL:`,
        which is `eta-publish one` before the publication is on the list:
        it has no published home yet, so there is nothing to point at,
        and a link to where it would go if it had one would be a broken one.
        """
        slug = self.doc.slug.strip("/")
        return f"{self.site_url}/{slug}/{IMAGE_DIR}/{href}" if slug else ""
