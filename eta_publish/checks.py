"""What a report has to have before it is published.

These read a parsed document and say what is missing.
They are separate from `parse.py`, which warns about what it could not read:
a document can parse perfectly and still not be ready,
and the two questions have different answers for the same file.

Every one of these is something to fix in the document rather than in the code,
which is why they are warnings on the document
and appear both in the build log and on the site's index page.
"""

import re
from dataclasses import replace
from itertools import groupby

from .nodes import (
    Cut,
    Document,
    Figure,
    Inline,
    Listed,
    Paragraph,
    Quoted,
    Shown,
    Span,
    Text,
    Where,
    addressed,
    cited_page,
    document_url,
    plain_text,
)
from .parse import (
    CREDIT_LABEL,
    KNOWN_FIELDS,
    REQUIRED_FIELDS,
    is_asset_note,
    is_credit_note,
    is_source_note,
    key_line,
    split_lines,
    starts_with_label,
    unfinished,
)

SEO_LIMIT = 300
"""How long a `SEO Description:` may be.

Past this a search engine truncates it,
so the sentence that decides whether anyone clicks ends mid-word,
and the writer never sees where it was cut.
"""

MAY_BE_EMPTY = frozenset({"Private Contributors", "SME/Liaison"})
"""Fields whose emptiness says something rather than being an omission.

A report with nobody uncredited has an empty `Private Contributors:` line,
and that is the answer, not a missing one.
A report with no subject-matter expert to check it has an empty `SME/Liaison:`.
Every other field empty is a line somebody meant to come back to.
"""


def check(doc: Document) -> None:
    """Warn about everything a published report should not be missing."""
    _check_figures(doc)
    _check_named(doc)
    _check_review(doc)
    _check_contributors(doc)
    _check_tracked(doc)
    _check_bare_urls(doc)
    _check_url_text(doc)
    _check_stray_fields(doc)

    if not doc.meta:
        # `parse` has already said the header is missing or empty.
        # Twelve more warnings saying the same thing would bury it.
        return

    for field in REQUIRED_FIELDS:
        if field not in doc.meta:
            doc.warn("the {} section has no {} line", Shown("Header"), Shown(f"{field}:"))
        elif field not in MAY_BE_EMPTY and not doc.meta[field].strip():
            doc.warn("the {} section leaves {} empty", Shown("Header"), Shown(f"{field}:"))

        if unfinished(doc.meta.get(field, "")):
            # The header is consumed before the body walk that flags these,
            # so `Short: TODO` would otherwise reach the page unremarked.
            doc.warn("{} is still marked unfinished", Shown(f"{field}:"))

    seo = doc.meta.get("SEO Description", "")
    if len(seo) > SEO_LIMIT:
        # The whole description, with the part that will not survive struck
        # through: which words are lost is the thing to fix.
        doc.warn(
            f"{{}} is {len(seo)} characters, over the {SEO_LIMIT} a search result shows:{{}}",
            Shown("SEO Description:"),
            Quoted(seo[:SEO_LIMIT], Cut(seo[SEO_LIMIT:])),
        )


def _check_contributors(doc: Document) -> None:
    """Two contributors with no comma between them, which reads as one person.

    Only detectable where an address was written beside a name,
    because the address is what says the name before it has ended.
    Two bare names run together are two words, and nothing here can tell
    those from a double-barrelled surname.
    """
    for entry in doc.meta.get("Public Contributors", "").split(","):
        found = addressed(entry)
        if found is not None and found[1]:
            doc.warn(
                "the {} line reads {} as one contributor; a comma is missing after the address",
                Shown("Public Contributors:"),
                Shown(entry.strip()),
            )


SAYS_NOTHING_ABOUT_FIELDS = frozenset({Where.HEADING, Where.FOOTNOTE})
"""Where a `Key: value` line is not a field however much it reads like one.

A heading is styled as one, so it is never a field:
`Appendix A: Freedom Tunnel` and `Ruling Grade: The Wrong Place to Scale Back`
are section names, and the report is full of them.

A footnote is a citation, written to a convention of its own
that opens with an author and quotes a headline after it:
`Barbara Russo-Lennon, "Subway spots: MTA's ad blitz ..."`.
"""


def _is_figure_note(line: list[Inline]) -> bool:
    """Whether `line` is one of the notes a figure carries."""
    return is_source_note(line) or is_asset_note(line) or is_credit_note(line)


def _check_stray_fields(doc: Document) -> None:
    """A `Key: value` line written somewhere it does not belong.

    The header is consumed before the body, so a `Short:` line that ended up
    under the headline, or inside a caption, is not the header's `Short:`.
    It publishes as a paragraph reading `Short: ...`,
    and the field it was meant to fill is reported missing somewhere else
    in the same build, with nothing saying the two are the same line.

    An unrecognized one is worth the same warning, and for the same reason:
    `Sort:` in the body is a line nothing reads,
    whether it was meant for the header or meant to be prose.

    What counts depends on where it sits.
    Under a picture, `Source:`, `Credit:` and `SVG:` are the ordinary spellings
    rather than strays, so those are left alone there and warned about in prose.

    Only lines whose name is underlined, which is what makes one a field.
    A sentence holding a colon is prose, and saying otherwise
    on every `and then: this` would make the check worth turning off.
    """
    for run, where in doc.text_runs():
        if where in SAYS_NOTHING_ABOUT_FIELDS:
            continue
        for line in split_lines(run):
            if where is not Where.BODY and _is_figure_note(line):
                continue
            found = key_line(line)
            if found is None:
                continue
            text = plain_text(line).strip()
            field = found[0]
            if field in KNOWN_FIELDS:
                doc.warn(
                    "{} is a {} field, and this one is outside it: {}",
                    Shown(f"{field}:"),
                    Shown("Header"),
                    Shown(text),
                )
            else:
                doc.warn(
                    "{} reads as a field and is not one: {}",
                    Shown(f"{field}:"),
                    Shown(text),
                )


def check_described(doc: Document) -> None:
    """Give a figure its SVG's description, and warn about one with none at all.

    After the images, since only the SVG says what is in it:
    a chart linked on an `SVG:` line is what publishes,
    and its `<title>` and `<desc>` describe it the way alt text would.
    """
    for figure in doc.figures:
        # Ahead of the raster's own alt text, and of the caption standing in for it:
        # the raster is only there because Docs cannot place an SVG.
        alt = doc.image_alts.get(figure.image.object_id, "")
        if alt:
            figure.image = replace(figure.image, alt=alt)
        elif not figure.image.alt and not figure.caption:
            doc.warn(
                "the image {} has no alt text and no caption; add a description to it in the doc",
                Shown(figure.image.filename),
            )


def _check_figures(doc: Document) -> None:
    """Every picture is described and attributed, or says which one is not.

    Named by the file it is written as rather than by its Docs object id,
    which nothing in the document shows anybody.
    """
    for block, after in zip(doc.blocks, [*doc.blocks[1:], None], strict=True):
        if not isinstance(block, Figure):
            continue
        named = Shown(block.image.filename)
        if not block.caption:
            doc.warn("the image {} has no caption", named)
        if block.credit:
            continue
        # A label is read only where it is underlined, so an unmarked `Credit:`
        # is the caption when it is the only line under the image, and a
        # paragraph of prose after it otherwise. Either way the image publishes
        # uncredited, with its credit printed under it as something else.
        if starts_with_label(block.caption, CREDIT_LABEL) or (
            isinstance(after, Paragraph) and starts_with_label(after.content, CREDIT_LABEL)
        ):
            doc.warn(
                "the image {} has a {} line under it that is not read as its credit, "
                "because {} is not underlined; underline it in the doc",
                named,
                Shown("Credit:"),
                Shown("Credit"),
            )
        else:
            doc.warn("the image {} has no {} line", named, Shown("Credit:"))


def _check_named(doc: Document) -> None:
    """Which pictures the document never said what they are.

    A `Source:` line is what names an image, and the name is the published URL.
    Without one the URL is a hash of a Docs object id:
    it says nothing about the picture,
    and it moves if the image is ever replaced.
    A line that names no file, `Image Source` or `SVG: TODO`,
    leaves the image as unnamed as no line at all.

    One warning for all of them rather than one each:
    they are one fix repeated, seventeen times in SAS West.
    """
    unnamed = [block for block in doc.blocks if isinstance(block, Figure) and not block.image.named]
    if not unnamed:
        return
    # One to a line, each with what the report says the picture is:
    # the difficulty of fixing these is working out which picture
    # `img-6fb0f9c4` is.
    listed = Listed(*((Shown(block.image.filename), _describe(block)) for block in unnamed))
    are = "is" if len(unnamed) == 1 else "are"
    doc.warn(
        f"{plural(len(unnamed), 'image')} {are} unnamed, so each publishes under a "
        f"hash; give each a {{}} line naming its file:{{}}",
        Shown("Source:"),
        listed,
    )


TRACKING = ("utm_",)
"""Query parameters that say where a link was copied from, not what it points at.

`utm_source`, `utm_medium` and the rest are what an analytics tag looks like,
and they arrive by pasting a link out of somewhere that added them.
The prefix rather than a list of names: they are an open set by design,
and anything beginning `utm_` is one of them whatever follows.
"""


def _check_tracked(doc: Document) -> None:
    """Which sources are cited with an analytics tag still on the URL.

    Left on, it is published as part of the citation, and it says where whoever
    added the link was reading rather than anything about the page. SAS West
    cited a `masstransitmag.com` press release as `?utm_source=chatgpt.com`.

    It also costs the source its archived copy, or nearly:
    nothing had ever captured that URL with the parameter on it,
    because nothing links to it that way. The replay drops tracking parameters
    before it looks, so it found the capture anyway, and the index, which does
    not, had no row for it at all. A build before the replay landed published
    that source as `not archived` with two captures of the page sitting there.

    One warning for all of them, like `_check_named`: it is one fix repeated.
    """
    tracked = [
        source
        for source in doc.sources
        if any(f"?{tag}" in source or f"&{tag}" in source for tag in TRACKING)
    ]
    if not tracked:
        return
    listed = Listed(*((Shown(_tag(source)), " on ", Shown(source)) for source in tracked))
    carry = "carries" if len(tracked) == 1 else "carry"
    doc.warn(
        f"{plural(len(tracked), 'source')} still {carry} the tag it was copied with; "
        f"take it off the link in the doc:{{}}",
        listed,
    )


def check_pages(doc: Document) -> None:
    """Which `#page=` citations name a page their PDF does not have.

    Separate from `check`, because the page counts it reads are recorded with
    the archive, and that is read after the document is checked.

    A citation of page 150 of a 6-page PDF cannot open where it says it does,
    and the reader is left on some other page with nothing saying why.
    A PDF nothing has counted yet is left alone:
    there is nothing to check the citation against.

    One warning for all of them, like `_check_named`.
    """
    wrong: list[tuple[Span, ...]] = []
    for source in doc.sources:
        page = cited_page(source)
        if page is None:
            continue
        if not page.isdigit() or int(page) < 1:
            wrong.append((Shown(source), " names no page"))
            continue
        found = doc.archives.get(document_url(source))
        pages = found.pages if found is not None else 0
        if pages and int(page) > pages:
            wrong.append((Shown(source), f" cites page {page} of {plural(pages, 'page')}"))
    if not wrong:
        return
    cites = "cites" if len(wrong) == 1 else "cite"
    doc.warn(
        f"{plural(len(wrong), 'PDF citation')} {cites} a page the PDF does not have:{{}}",
        Listed(*wrong),
    )


BARE_URL = re.compile(r"https?://\S+")

TRAILING = ".,;:!?\"'”’"
"""What ends the sentence a URL sits in rather than the URL."""


def _check_bare_urls(doc: Document) -> None:
    """Which URLs the document typed out without linking.

    Each output treats one differently: the HTML prints it as text, Typst links
    it, and the Markdown leaves it for whatever renders it to guess where it
    ends, which for a DOI like `10.1061/(ASCE)0733-9488(2007)133:4(242)` is a
    guess. Nor is it a source, so it is never archived or listed. Linked in
    the document, it is all of those and the same in every output.

    Read off runs of unlinked text only, joined between links, so a URL split
    across two runs by a change of style is still one URL, and the text of a
    link that happens to be its own address is not bare.

    One warning for all of them, like `_check_tracked`.
    """
    bare: list[str] = []
    for runs, _ in doc.text_runs():
        stretch: list[str] = []
        for run in [*runs, None]:
            if isinstance(run, Text) and not run.href:
                stretch.append(run.text)
                continue
            bare.extend(_bare("".join(stretch)))
            stretch = []
    if not bare:
        return
    listed = Listed(*((Shown(url),) for url in bare))
    doc.warn(
        f"{plural(len(bare), 'URL')} typed out but not linked; "
        f"link {'it' if len(bare) == 1 else 'each'} in the doc:{{}}",
        listed,
    )


URL_TEXT = re.compile(r"(https?://|www\.)", re.IGNORECASE)


def _check_url_text(doc: Document) -> None:
    """Which links show their own address rather than words.

    A link is written as text that says what it is, `the 2025 ridership
    figures`, and the address is what clicking it is for. Shown as the URL it
    is a string to read past, and a long one runs across the column.

    A link split across runs by a change of style is one link, so runs are
    taken together while they share an address.

    One warning for all of them, like `_check_tracked`.
    """
    shown: list[str] = []
    for runs, _ in doc.text_runs():
        for href, linked in groupby(runs, key=_href):
            if not href:
                continue
            text = "".join(run.text for run in linked if isinstance(run, Text)).strip()
            if URL_TEXT.match(text):
                shown.append(text)
    if not shown:
        return
    listed = Listed(*((Shown(text),) for text in shown))
    one = len(shown) == 1
    doc.warn(
        f"{plural(len(shown), 'link')} {'shows its' if one else 'show their'} URL as "
        f"{'its' if one else 'their'} text; give {'it' if one else 'each'} words in the doc:{{}}",
        listed,
    )


def _href(run: Inline) -> str | None:
    return run.href if isinstance(run, Text) else None


def _bare(text: str) -> list[str]:
    """The URLs in `text`, without the punctuation of the sentence around them.

    A `)` is the URL's own while it closes a `(` inside it, as the DOIs' do.
    """
    found: list[str] = []
    for match in BARE_URL.finditer(text):
        url = match.group().rstrip(TRAILING)
        while url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1].rstrip(TRAILING)
        found.append(url)
    return found


def _tag(source: str) -> str:
    """The tracking parameters on `source`, for saying which to take off."""
    query = source.partition("?")[2].partition("#")[0]
    return "&".join(
        part for part in query.split("&") if any(part.startswith(tag) for tag in TRACKING)
    )


DESCRIPTION_LIMIT = 70
"""How much of a caption is enough to tell one picture from another."""


def _describe(block: Figure) -> str:
    """What the report says this picture is, for telling it from the others.

    The caption, because that is what a reader is told the picture is.
    Its alt text where there is no caption,
    which is what a reader who cannot see it is told instead.
    """
    description = plain_text(block.caption).strip() or block.image.alt.strip()
    if not description:
        return ""
    if len(description) > DESCRIPTION_LIMIT:
        description = description[:DESCRIPTION_LIMIT].rstrip() + "..."
    return f": {description}"


def _check_review(doc: Document) -> None:
    """Nothing is published with the editing still going on in it.

    A build resolves suggestions away and never sees comments,
    so what publishes from a document under review looks finished
    and is a snapshot of an argument nobody has finished having.

    Both counts are this tab's: the document these reports live in has eight
    tabs and 46 comments open across them, against three on the one that
    publishes, so a count for the file would be a number nobody could act on.
    """
    # A preview with them accepted is a build asked to show them,
    # and says nothing about them that the person asking does not know.
    if doc.open_suggestions and not doc.suggestions_accepted:
        doc.warn(
            f"{plural(doc.open_suggestions, 'suggestion')} still open on this tab; "
            "the build publishes the document without them, as it reads today"
        )
    if doc.open_comments:
        doc.warn(f"{plural(doc.open_comments, 'comment thread')} still open on this tab")


def plural(count: int, thing: str) -> str:
    return f"{count} {thing}" if count == 1 else f"{count} {thing}s"
