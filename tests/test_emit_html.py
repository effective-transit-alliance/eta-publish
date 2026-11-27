"""HTML emitted for the Squarespace code block."""

import json
import re
from html.parser import HTMLParser
from typing import override

import pytest
import tinycss2
from paths import FIXTURE_DIR, HOST, named_images

from eta_publish.emit.html import HtmlEmitter, publication_page
from eta_publish.nodes import Document, Heading, Image, Paragraph, Shown, Text
from eta_publish.parse import parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


@pytest.fixture
def doc() -> Document:
    parsed = named_images(parse(FIXTURE))
    parsed.image_files["io.1"] = "sas-west-036.png"
    return parsed


@pytest.fixture
def out(doc: Document) -> str:
    return HtmlEmitter(
        image_base="https://assets.etany.org/sas-west", inline_css=False, site_url=HOST
    ).emit(doc)


def test_every_footnote_has_a_matching_backlink(out: str) -> None:
    """The defect this whole tool exists to prevent:
    the published SAS West report has a footnote whose `↑` leads nowhere."""
    refs = set(re.findall(r'id="fnref(\d+)"', out))
    notes = set(re.findall(r'id="fn(\d+)"', out))
    backlinks = set(re.findall(r'href="#fnref(\d+)"', out))
    assert refs == notes == backlinks
    assert refs == {"1", "2"}


def test_ids_are_unique() -> None:
    """`fn18-return` appears twice on the published page.
    Two paragraphs with the same words are not the same paragraph either."""
    parsed = named_images(parse(FIXTURE))
    same = "The same words twice."
    parsed.blocks.extend(
        [Paragraph(content=[Text(text=same)]), Paragraph(content=[Text(text=same)])]
    )
    emitted = HtmlEmitter(site_url=HOST).emit(parsed)
    ids = re.findall(r'id="([^"]+)"', emitted)
    assert len(ids) == len(set(ids))


def test_images_use_the_image_base_and_resolved_extension(out: str) -> None:
    assert 'src="https://assets.etany.org/sas-west/sas-west-036.png"' in out
    assert 'alt="SAS West alignment map"' in out


MARK = re.compile(r'<a class="link-mark"[^>]*></a>')


def without_marks(html: str) -> str:
    """`html` with the self-links stripped.

    Every block carries one, and a test about what a block contains
    is not about the link to it.
    The links are checked in `test_every_linkable_block_carries_a_link_to_itself`.
    """
    return MARK.sub("", html)


def sections_and_headings(out: str) -> list[str]:
    """The ids the table of contents is allowed to point at, in page order.

    The back matter's id is on its `section`, not on its heading:
    the whole section is the thing being linked to. The publication title identifies
    the document rather than introducing a section, so the contents omit it."""
    return [
        m.group(1) or m.group(2)
        for m in re.finditer(r'<h\d id="([^"]+)"|<section class="[^"]*" id="([^"]+)"', out)
        if (m.group(1) or m.group(2)) != "title"
    ]


def test_the_table_of_contents_lists_every_heading(out: str) -> None:
    """Every heading on the page, in order, footnotes and contributors too."""
    toc_html = without_marks(re.findall(r'<nav class="toc".*?</nav>', out, re.S)[0])
    linked = re.findall(r'href="#([^"]+)"', toc_html)
    assert linked == sections_and_headings(out)
    assert '<a href="#the-elephants-in-the-room">The Elephants in the Room</a>' in toc_html


class Read(HTMLParser):
    """The emitted markup as a reader of HTML sees it, rather than as a string.

    An assertion about a substring is written in the same terms the emitter is,
    so a quoting mistake that both make is a mistake neither one shows.
    This is the standard library's parser, which is not the thing under test:
    it undoes the escaping, and what comes back out is compared to what went in.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attrs: list[dict[str, str | None]] = []
        self.tags: list[str] = []
        self.text: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.append(dict(attrs))

    @override
    def handle_data(self, data: str) -> None:
        self.text.append(data)


def read(markup: str) -> Read:
    parser = Read()
    parser.feed(markup)
    parser.close()
    return parser


# Determinism across runs is `test_snapshots.py`'s.
# Comparing an emitter with itself in one process cannot see it:
# hash randomization is fixed for the life of an interpreter,
# so order-dependent output matches itself and still differs from run to run.


def test_the_contributors_section_lists_the_public_contributors(doc: Document) -> None:
    """Alphabetically by surname, which is how `etany.org` credits them."""
    doc.meta["Public Contributors"] = "Grace Hopper, Ada Lovelace"
    doc.meta["Private Contributors"] = "Someone Unnamed"
    out = HtmlEmitter(inline_css=False, site_url=HOST).emit(doc)
    assert "<li>Grace Hopper</li>\n<li>Ada Lovelace</li>" in out
    assert "Someone Unnamed" not in out
    # After the footnotes, which is where the live publication credits them.
    assert out.index('<section class="footnotes"') < out.index('<section class="contributors"')
    doc.meta.pop("Public Contributors")
    assert 'class="contributors"' not in HtmlEmitter(inline_css=False, site_url=HOST).emit(doc)


def test_the_dateline_is_the_final_due_date(doc: Document) -> None:
    """Written out, which is how `etany.org` dates a publication."""
    doc.meta["Publish Due Date"] = "Aug 19, 2026"
    out = HtmlEmitter(inline_css=False, site_url=HOST).emit(doc)
    assert '<p class="dateline" id="date">August 19, 2026</p>' in without_marks(out)
    doc.meta.pop("Publish Due Date")
    assert 'class="dateline"' not in HtmlEmitter(inline_css=False, site_url=HOST).emit(doc)


def test_editing_a_paragraph_does_not_move_its_id(doc: Document) -> None:
    """A copy edit is most of what happens to a publication after it publishes,
    and a link into the paragraph that was fixed should still land on it."""
    first = re.findall(r'<p id="([^"]+)"', HtmlEmitter(inline_css=False, site_url=HOST).emit(doc))[
        0
    ]
    para = next(b for b in doc.blocks if isinstance(b, Paragraph) and b.content)
    para.content = [Text(text="Rewritten.")]
    assert f'<p id="{first}">' in HtmlEmitter(inline_css=False, site_url=HOST).emit(doc)


def test_inserting_a_paragraph_moves_only_what_follows_it_in_that_section(
    doc: Document,
) -> None:
    """The cost of counting, stated as a test.
    A new paragraph renumbers the rest of its own section and nothing else,
    where hashing moved nothing and a page-wide count would have moved everything below."""
    headings = [b for b in doc.blocks if isinstance(b, Heading)]
    at = doc.blocks.index(headings[-1]) + 1
    before = re.findall(r'<p id="([^"]+)"', HtmlEmitter(inline_css=False, site_url=HOST).emit(doc))
    doc.blocks.insert(at, Paragraph(content=[Text(text="A paragraph added while editing.")]))
    after = re.findall(r'<p id="([^"]+)"', HtmlEmitter(inline_css=False, site_url=HOST).emit(doc))
    section = headings[-1].anchor
    assert [i for i in before if not i.startswith(section)] == [
        i for i in after if not i.startswith(section)
    ]


def test_emitting_twice_gives_the_same_ids(doc: Document) -> None:
    """The suffixing counter must not carry over between runs."""
    emitter = HtmlEmitter(inline_css=False, site_url=HOST)
    assert emitter.emit(doc) == emitter.emit(doc)


def test_a_figure_carries_the_shape_of_its_image(doc: Document) -> None:
    """The ratio a row divides a line by is the written file's own.

    Not the document's:
    Docs says how large an image is placed rather than how large it is,
    and the crop has already changed the shape by the time anything is emitted.
    """
    assert "--aspect" not in HtmlEmitter(inline_css=False, site_url=HOST).emit(doc), (
        "unrecorded: a build that skipped the images, or an SVG with no pixel size"
    )
    doc.image_shapes["io.1"] = (400, 250)
    assert 'style="--aspect: 1.600"' in HtmlEmitter(inline_css=False, site_url=HOST).emit(doc)


def test_every_linkable_block_carries_a_link_to_itself(out: str) -> None:
    """Anything with an id is something a reader may want to send someone,
    so the link to it is on the page rather than in its source.

    A publication is quoted a paragraph at a time, so every block is a target:
    paragraphs, figures, and tables wherever they sit,
    footnote bodies and table cells included.

    Except in the back matter and in a table,
    where the paragraphs are not passages of the publication:
    a footnote is reached from its reference and left by the arrow back,
    and a cell is part of its table.
    """
    publication = re.sub(r'<section class="footnotes".*?</section>', "", out, flags=re.S)
    publication = re.sub(r"<td>.*?</td>", "", publication, flags=re.S)
    for opening in ("<p", "<figure", '<div class="table-scroll"'):
        for tag in re.findall(rf"{re.escape(opening)}[ >][^>]*>?", out):
            assert "id=" in tag, f"{tag} cannot be linked to"
    anchors = re.findall(r'<(?:h[1-6]|p|figure|div|nav|section)[^>]* id="([^"]+)"', publication)
    assert anchors
    marked = set(re.findall(r'<a class="link-mark"[^>]* href="#([^"]+)"', out))
    for anchor in anchors:
        assert anchor in marked, f"nothing links to {anchor}"


TIPS = {".eta-report .footnote-tip", ".eta-report .source-tip"}
"""The two preview boxes, as `publication.css` selects them."""


def css_rules(css: str, media: str | None = None) -> list[tuple[set[str], dict[str, str]]]:
    """Each rule's selectors and declarations, parsed rather than matched as text,
    so how the stylesheet is laid out does not matter.

    The top-level rules, or with `media`, those inside the `@media` with that query.
    """
    rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    if media is not None:
        (block,) = (
            rule
            for rule in rules
            if rule.type == "at-rule"
            and rule.lower_at_keyword == "media"
            and " ".join(tinycss2.serialize(rule.prelude).split()) == media
        )
        rules = tinycss2.parse_rule_list(block.content, skip_comments=True, skip_whitespace=True)
    parsed: list[tuple[set[str], dict[str, str]]] = []
    for rule in rules:
        if rule.type != "qualified-rule":
            continue
        selectors = {" ".join(s.split()) for s in tinycss2.serialize(rule.prelude).split(",")}
        declarations = {
            d.lower_name: tinycss2.serialize(d.value).strip()
            for d in tinycss2.parse_declaration_list(
                rule.content, skip_comments=True, skip_whitespace=True
            )
            if d.type == "declaration"
        }
        parsed.append((selectors, declarations))
    return parsed


def test_the_footnote_preview_is_hidden_where_nothing_hovers() -> None:
    """The span is in the markup on every device, so hiding it only inside
    `@media (hover: hover)` left a phone displaying every note inline,
    in the middle of the sentence it belongs to.

    Outside every `@media` is what a phone reads: there the boxes are hidden,
    and nothing there shows one again.
    """
    from eta_publish.emit.html import PUBLICATION_CSS

    rules = css_rules(PUBLICATION_CSS)
    assert any(selectors >= TIPS and d.get("display") == "none" for selectors, d in rules)
    for selectors, declarations in rules:
        if any(s.endswith("-tip") for s in selectors) and "display" in declarations:
            assert declarations["display"] == "none", selectors
    # Hidden by default is only right if hovering still brings it back.
    # A source's box is shown by the same rule, and built by the script.
    shown = {
        ".eta-report .footnote-ref:hover .footnote-tip",
        ".eta-report .footnote-ref:focus-within .footnote-tip",
        ".eta-report .cited:hover .source-tip",
        ".eta-report .cited:focus-within .source-tip",
    }
    assert any(
        selectors >= shown and d.get("display") == "block"
        for selectors, d in css_rules(PUBLICATION_CSS, "(hover: hover)")
    )


def test_an_empty_shown_value_is_still_marked(doc: Document) -> None:
    """A warning about a value that is not there has to show that it is not there.
    An empty code span carries the same background and padding as any other,
    so it renders as a small box with nothing in it: measured at 8x18 against
    62x18 for one holding `Draft 2`."""
    from eta_publish.nodes import Shown

    doc.warn("the tab is named {}", Shown(""))
    out = HtmlEmitter(site_url=HOST).emit(doc)
    assert "the tab is named <code></code>" in out


def test_paragraphs_are_numbered_from_one_in_each_section(out: str) -> None:
    """Within the section rather than across the page:
    a paragraph added to the first section would otherwise renumber the last one."""
    for section in ("ground-conditions", "the-elephants-in-the-room"):
        numbers = [int(n) for n in re.findall(rf'<p id="{section}-p(\d+)"', out)]
        assert numbers == list(range(1, len(numbers) + 1))
    # `#ground-conditions-p1` says where it is,
    # which is what someone reading the link before following it wants to know.
    assert '<p id="ground-conditions-p1">' in out
    # A footnote's paragraphs are numbered within it, not along with the publication:
    # 43 between 12 and 13 is a number nobody could do anything with.
    assert '<p id="fn1-p1">' in out


EVIL = '"><script>alert(1)</script><x y="'


def test_a_hostile_document_opens_no_tag_of_its_own(doc: Document) -> None:
    """The round trip over a whole publication, not over one primitive.

    A bug in `attributes` is the small half of this worry
    and the reviewed half; the larger half is a call site
    that wrote a value into an f-string and forgot to escape it.
    Reading the finished page back finds either.
    """
    doc.title = EVIL
    doc.meta["Short"] = EVIL
    doc.subtitle = [Text(EVIL)]
    doc.meta["SEO Description"] = EVIL
    doc.meta["Public Contributors"] = EVIL
    doc.warn("a warning about {}", Shown(EVIL))
    # Alt text is the document's too, and it reaches the page inside an attribute.
    # An image is frozen, and this is the one place anything writes to one.
    for image in doc.images:
        object.__setattr__(image, "alt", EVIL)
    # A link's address is the document's too: what has to hold is that
    # it points where the document pointed, whichever characters get spelled out.
    href = "https://x.test/?a=\"b&c='d'"
    doc.blocks.append(Paragraph([Text(text="a link", href=href)]))
    for output in (HtmlEmitter(site_url=HOST).emit(doc), publication_page(doc, site_url=HOST)):
        parsed = read(output)
        assert parsed.tags.count("script") == 1, "only the page's own script"
        assert parsed.tags.count("x") == 0, "the document opened no tag"
        assert EVIL in "".join(parsed.text), "the text itself survives, as text"
        assert any(attrs.get("href") == href for attrs in parsed.attrs)
    # Escaping is wrong in two directions, and a substring check sees neither:
    # too little closes the attribute's quotes, too much reaches the page as
    # `&amp;amp;` or as an apostrophe nobody typed.
    # Both are the same failure to a reader, so each value is read back and compared.
    for value in ("a & b", "&amp;", "it's", 'say "hi"', "<>", "\u00e9 \u00a3 \u00b7"):
        doc.meta["SEO Description"] = value
        for image in doc.images:
            object.__setattr__(image, "alt", value)
        parsed = read(publication_page(doc, site_url=HOST))
        descriptions = [
            attrs["content"] for attrs in parsed.attrs if attrs.get("name") == "description"
        ]
        assert descriptions == [value], value
        assert any(attrs.get("alt") == value for attrs in parsed.attrs), value


def test_a_linked_fragment_links_the_sites_copies(doc: Document) -> None:
    """Linked, not carried, unless built to embed them."""
    from eta_publish.build import fragment_emitter

    linked = fragment_emitter("images", "https://example.org/assets", site_url=HOST).emit(doc)
    assert "<style>" not in linked
    assert 'href="https://example.org/assets/publication.css"' in linked
    assert 'src="https://example.org/assets/publication.js" defer' in linked
    embedded = fragment_emitter("images", "", site_url=HOST).emit(doc)
    assert "<style>" in embedded
    assert "<link" not in embedded


def test_the_page_describes_itself_the_way_squarespace_would(doc: Document) -> None:
    """With the SEO description alone: a Squarespace page has no excerpt to fall back to."""
    doc.meta["Short"] = "The short."
    doc.meta["SEO Description"] = "The SEO description."
    page = publication_page(doc, site_url=HOST)
    assert 'name="description" content="The SEO description."' in page
    assert 'property="og:description" content="The SEO description."' in page
    assert "The short." not in page


def test_the_masthead_links_the_pdf_where_it_is_given(doc: Document) -> None:
    pdf = f"{HOST}/reports/sas-west/report.pdf"
    out = HtmlEmitter(pdf_href=pdf, site_url=HOST).emit(doc)
    assert f'<a class="pdf-button" href="{pdf}">' in out
    assert "Download PDF</a>" in out
    assert 'href="report.pdf"' in publication_page(doc, pdf_href="report.pdf", site_url=HOST)


def test_the_masthead_links_no_pdf_unless_given(doc: Document) -> None:
    assert 'class="pdf-button"' not in HtmlEmitter(site_url=HOST).emit(doc)


def test_the_share_card_is_absolute_and_sized_for_a_link_preview(doc: Document) -> None:
    """A preview fetches the card from wherever the link was posted,
    and shows a picture only when `og:image` is absolute."""
    doc.card = Image(object_id="io.card", filename="card")
    doc.image_files["io.card"] = "card.jpg"
    doc.image_shapes["io.card"] = (1200, 628)
    page = publication_page(
        doc,
        card_base="https://example.invalid/r/images",
        page_url="https://example.invalid/r/",
        site_url=HOST,
    )
    assert 'property="og:url" content="https://example.invalid/r/"' in page
    assert 'property="og:image" content="https://example.invalid/r/images/card.jpg"' in page
    assert 'property="og:image:width" content="1200"' in page
    assert 'property="og:image:height" content="628"' in page
    assert 'name="twitter:card" content="summary_large_image"' in page
    assert 'property="og:type" content="article"' in page


def test_source_brackets_are_out_of_the_text_by_default(doc: Document, out: str) -> None:
    """Off, the `[n]` stays in the markup for the backlinks, and the root says to hide it."""
    assert '<div class="eta-report no-source-brackets">' in out
    assert 'id="srcref1-1"' in out
    shown = HtmlEmitter(inline_css=False, source_brackets=True, site_url=HOST).emit(doc)
    assert '<div class="eta-report">' in shown
