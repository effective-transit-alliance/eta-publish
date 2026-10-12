"""HTML emitted for the Squarespace code block."""

import json
import re
from html.parser import HTMLParser
from typing import override

import pytest
from htpy import a
from paths import FIXTURE_DIR, named_images

from eta_publish.emit.base import shown_url
from eta_publish.emit.html import HtmlEmitter, link_mark, markup, report_page
from eta_publish.nodes import Document, Heading, Paragraph, Shown, Text
from eta_publish.parse import parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


@pytest.fixture
def doc() -> Document:
    parsed = named_images(parse(FIXTURE))
    parsed.image_files["io.1"] = "sas-west-036.png"
    return parsed


@pytest.fixture
def out(doc: Document) -> str:
    return HtmlEmitter(image_base="https://assets.etany.org/sas-west", inline_css=False).emit(doc)


def test_every_footnote_has_a_matching_backlink(out: str) -> None:
    """The defect this whole tool exists to prevent:
    the published SAS West report has a footnote whose `↑` leads nowhere."""
    refs = set(re.findall(r'id="fnref(\d+)"', out))
    notes = set(re.findall(r'id="fn(\d+)"', out))
    backlinks = set(re.findall(r'href="#fnref(\d+)"', out))
    assert refs == notes == backlinks
    assert refs == {"1", "2"}


def test_ids_are_unique() -> None:
    """`fn18-return` appears twice on the published page."""
    emitted = HtmlEmitter().emit(named_images(parse(FIXTURE)))
    ids = re.findall(r'id="([^"]+)"', emitted)
    assert len(ids) == len(set(ids))


def test_the_source_line_is_not_published(out: str) -> None:
    """`Source:` names the original file in Drive, for whoever assembles the report.
    It appears nowhere on the live page and must not leak.

    The published image is named after it, which is a filename rather than the line:
    the note itself, and the extension it was exported under, are both absent."""
    assert "Source:" not in out
    assert "sas-west-036.jpg" not in out


def test_the_caption_and_credit_are_published(out: str) -> None:
    assert '<figcaption class="figure-caption">The SAS West and Phase 2 alignments.' in out
    assert '<figcaption class="figure-credit">Credit: MTA' in out


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
    the whole section is the thing being linked to. The report title identifies
    the document rather than introducing a section, so the contents omit it."""
    return [
        m.group(1) or m.group(2)
        for m in re.finditer(r'<h\d id="([^"]+)"|<section class="[^"]*" id="([^"]+)"', out)
        if (m.group(1) or m.group(2)) != "title"
    ]


def test_the_table_of_contents_links_to_real_anchors(out: str) -> None:
    toc_html = without_marks(re.findall(r'<nav class="toc".*?</nav>', out, re.S)[0])
    linked = set(re.findall(r'href="#([^"]+)"', toc_html))
    targets = set(sections_and_headings(out))
    assert linked and linked <= targets
    assert '<a href="#the-elephants-in-the-room">The Elephants in the Room</a>' in toc_html


def test_the_table_of_contents_lists_every_heading(out: str) -> None:
    """Every heading on the page, in order, footnotes and contributors too."""
    toc_html = without_marks(re.findall(r'<nav class="toc".*?</nav>', out, re.S)[0])
    linked = re.findall(r'href="#([^"]+)"', toc_html)
    assert linked == sections_and_headings(out)


def test_the_table_of_contents_indents_a_subsection(out: str) -> None:
    """A subsection sits in a list inside its section's own entry."""
    toc_html = without_marks(re.findall(r'<nav class="toc".*?</nav>', out, re.S)[0])
    assert (
        '<li><a href="#the-elephants-in-the-room">The Elephants in the Room</a>\n'
        '<ul>\n<li><a href="#ground-conditions">Ground Conditions</a></li>\n'
        "</ul></li>" in toc_html
    )


def test_toc_entries_close_in_order(out: str) -> None:
    """Nesting a list inside an entry is easy to close in the wrong order."""
    toc_html = re.findall(r'<nav class="toc".*?</nav>', out, re.S)[0]
    stack: list[str] = []
    for tag in re.findall(r"</?(?:ul|li)\b", toc_html):
        if tag.startswith("</"):
            assert stack.pop() == tag.removeprefix("</")
        else:
            stack.append(tag.removeprefix("<"))
    assert not stack


def test_nested_lists_nest(out: str) -> None:
    assert re.search(
        r'<div class="list-block" id="list-[0-9a-f]{8}">'
        r"<ul><li>First point<ul><li>Nested point</li></ul></li>"
        r"<li>Second point</li></ul></div>",
        without_marks(out),
    )


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


def test_text_and_urls_are_escaped() -> None:
    """Doc text is prose, but it reaches a published page verbatim."""
    hostile = json.loads(json.dumps(FIXTURE))
    hostile["body"]["content"].append(
        {
            "paragraph": {
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "elements": [
                    {
                        "textRun": {
                            "content": "<script>alert(1)</script>\n",
                            "textStyle": {"link": {"url": 'https://x.test/?a="b'}},
                        }
                    }
                ],
            }
        }
    )
    emitted = HtmlEmitter().emit(named_images(parse(hostile)))
    parsed = read(emitted)
    # The page carries one script of its own, the one that places the footnote
    # tooltips, so the check is that nothing from the document became a second
    # one, rather than that the page has none.
    assert parsed.tags.count("script") == 1
    assert "<script>alert(1)</script>" in "".join(parsed.text), "as text, not as a tag"
    # Which characters the escaping spells out is the builder's business.
    # What has to hold is that the link points where the document pointed.
    assert {"href": 'https://x.test/?a="b'} in parsed.attrs


def test_inline_css_is_optional(doc: Document) -> None:
    assert HtmlEmitter(inline_css=True).emit(doc).startswith("<style>")
    assert not HtmlEmitter(inline_css=False).emit(doc).startswith("<style>")


# Determinism across runs is `test_snapshots.py`'s.
# Comparing an emitter with itself in one process cannot see it:
# hash randomization is fixed for the life of an interpreter,
# so order-dependent output matches itself and still differs from run to run.


def test_tables_scroll_rather_than_overflow(out: str) -> None:
    """Wide comparison tables are common in these reports,
    and a page that scrolls sideways on a phone is worse than a table that does."""
    marked = without_marks(out)
    assert re.search(r'<div class="table-scroll" id="table-[0-9a-f]{8}"><table>', marked)
    # A cell's paragraphs are numbered within the table,
    # not within the section the table sits in.
    assert re.search(r'<td><p id="table-[0-9a-f]{8}-p\d+">Grand Paris Express</p></td>', marked)


def test_the_contributors_section_lists_the_public_contributors(doc: Document) -> None:
    """Alphabetically by surname, which is how `etany.org` credits them."""
    doc.meta["Public Contributors"] = "Khyber Sen, Alon Levy"
    doc.meta["Private Contributors"] = "Someone Unnamed"
    out = HtmlEmitter(inline_css=False).emit(doc)
    assert "<li>Alon Levy</li>\n<li>Khyber Sen</li>" in out
    assert "Someone Unnamed" not in out


def test_the_contributors_section_comes_last(doc: Document) -> None:
    """After the footnotes, which is where the published report credits them."""
    doc.meta["Public Contributors"] = "Khyber Sen"
    out = HtmlEmitter(inline_css=False).emit(doc)
    assert out.index('<section class="footnotes"') < out.index('<section class="contributors"')


def test_a_report_with_no_public_contributors_has_no_contributors(doc: Document) -> None:
    doc.meta.pop("Public Contributors", None)
    assert 'class="contributors"' not in HtmlEmitter(inline_css=False).emit(doc)


def test_the_dateline_is_the_final_due_date(doc: Document) -> None:
    """Written out, which is how `etany.org` dates a report."""
    doc.meta["Publish Due Date"] = "Aug 19, 2026"
    out = HtmlEmitter(inline_css=False).emit(doc)
    assert '<p class="dateline" id="date">August 19, 2026</p>' in without_marks(out)


def test_a_report_with_no_final_due_date_has_no_dateline(doc: Document) -> None:
    doc.meta.pop("Publish Due Date", None)
    assert 'class="dateline"' not in HtmlEmitter(inline_css=False).emit(doc)


def test_every_block_can_be_linked_to(out: str) -> None:
    """A report is quoted a paragraph at a time, so every block is a target.

    Paragraphs, figures, and tables wherever they sit,
    footnote bodies and table cells included.
    A list nested inside a list item is reached through the list that holds it."""
    for opening in ("<p", "<figure", '<div class="table-scroll"'):
        for tag in re.findall(rf"{re.escape(opening)}[ >][^>]*>?", out):
            assert "id=" in tag, f"{tag} cannot be linked to"


def test_a_paragraph_is_named_by_its_section_and_its_place_in_it(out: str) -> None:
    """`#ground-conditions-p2` says where it is,
    which is what someone reading the link before following it wants to know."""
    assert '<p id="ground-conditions-p1">' in out
    assert re.search(r'<p id="the-elephants-in-the-room-p\d+">', out)


def test_editing_a_paragraph_does_not_move_its_id(doc: Document) -> None:
    """A copy edit is most of what happens to a report after it publishes,
    and a link into the paragraph that was fixed should still land on it."""
    first = re.findall(r'<p id="([^"]+)"', HtmlEmitter(inline_css=False).emit(doc))[0]
    para = next(b for b in doc.blocks if isinstance(b, Paragraph) and b.content)
    para.content = [Text(text="Rewritten.")]
    assert f'<p id="{first}">' in HtmlEmitter(inline_css=False).emit(doc)


def test_inserting_a_paragraph_moves_only_what_follows_it_in_that_section(
    doc: Document,
) -> None:
    """The cost of counting, stated as a test.
    A new paragraph renumbers the rest of its own section and nothing else,
    where hashing moved nothing and a page-wide count would have moved everything below."""
    headings = [b for b in doc.blocks if isinstance(b, Heading)]
    at = doc.blocks.index(headings[-1]) + 1
    before = re.findall(r'<p id="([^"]+)"', HtmlEmitter(inline_css=False).emit(doc))
    doc.blocks.insert(at, Paragraph(content=[Text(text="A paragraph added while editing.")]))
    after = re.findall(r'<p id="([^"]+)"', HtmlEmitter(inline_css=False).emit(doc))
    section = headings[-1].anchor
    assert [i for i in before if not i.startswith(section)] == [
        i for i in after if not i.startswith(section)
    ]


def test_repeated_text_still_gets_unique_ids(doc: Document) -> None:
    same = "The same words twice."
    doc.blocks.extend([Paragraph(content=[Text(text=same)]), Paragraph(content=[Text(text=same)])])
    out = HtmlEmitter(inline_css=False).emit(doc)
    ids = re.findall(r'<p id="([^"]+)"', out)
    assert len(ids) == len(set(ids))


def test_emitting_twice_gives_the_same_ids(doc: Document) -> None:
    """The suffixing counter must not carry over between runs."""
    emitter = HtmlEmitter(inline_css=False)
    assert emitter.emit(doc) == emitter.emit(doc)


def test_the_backlink_sits_inside_the_first_paragraph(out: str) -> None:
    """A paragraph is a block,
    so an arrow placed before one lands on a line of its own
    with the note starting underneath it."""
    for note in re.findall(r'<li id="fn\d+">.*?</li>', out, re.S):
        assert re.match(
            r'<li id="fn\d+"><a class="link-mark"[^>]*></a><p[^>]*><a href="#fnref\d+"', note
        ), note[:160]


def test_a_figure_carries_the_shape_of_its_image(doc: Document) -> None:
    """The ratio a row divides a line by is the written file's own.

    Not the document's:
    Docs says how large an image is placed rather than how large it is,
    and the crop has already changed the shape by the time anything is emitted.
    """
    doc.image_shapes["io.1"] = (400, 250)
    assert 'style="--aspect: 1.600"' in HtmlEmitter(inline_css=False).emit(doc)


def test_a_figure_of_unrecorded_size_says_nothing_about_its_shape(doc: Document) -> None:
    """A build that skipped the images,
    and the SVG originals that have no pixel size at all.
    The stylesheet's own default stands in, so a row of them is still a row."""
    assert "--aspect" not in HtmlEmitter(inline_css=False).emit(doc)


def test_every_linkable_block_carries_a_link_to_itself(out: str) -> None:
    """Anything with an id is something a reader may want to send someone,
    so the link to it is on the page rather than in its source.

    Except in the back matter and in a table,
    where the paragraphs are not passages of the report:
    a footnote is reached from its reference and left by the arrow back,
    and a cell is part of its table.
    """
    report = re.sub(r'<section class="footnotes".*?</section>', "", out, flags=re.S)
    report = re.sub(r"<td>.*?</td>", "", report, flags=re.S)
    anchors = re.findall(r'<(?:h[1-6]|p|figure|div|nav|section)[^>]* id="([^"]+)"', report)
    assert anchors
    marked = set(re.findall(r'<a class="link-mark"[^>]* href="#([^"]+)"', out))
    for anchor in anchors:
        assert anchor in marked, f"nothing links to {anchor}"


def test_the_footnote_preview_is_hidden_where_nothing_hovers() -> None:
    """The span is in the markup on every device, so hiding it only inside
    `@media (hover: hover)` left a phone displaying every note inline,
    in the middle of the sentence it belongs to."""
    from eta_publish.emit.html import REPORT_CSS

    # Everything the hovering devices are told, dropped.
    # What is left is what a phone reads, and it has to hide the box.
    without_hover = re.sub(r"@media \(hover: hover\) \{.*?\n\}", "", REPORT_CSS, flags=re.S)
    assert ".footnote-ref:hover" not in without_hover
    assert ".eta-report .footnote-tip,\n.eta-report .source-tip { display: none; }" in without_hover


def test_the_footnote_preview_is_shown_where_something_does(out: str) -> None:
    """Hidden by default is only right if hovering still brings it back."""
    from eta_publish.emit.html import REPORT_CSS

    hovering = re.search(r"@media \(hover: hover\) \{.*?\n\}", REPORT_CSS, re.S)
    assert hovering is not None
    assert ".footnote-ref:hover .footnote-tip" in hovering.group()
    assert ".footnote-ref:focus-within .footnote-tip," in hovering.group()
    # A source's box is shown by the same rule, and built by the script.
    assert ".cited:focus-within .source-tip { display: block; }" in hovering.group()


def test_an_empty_shown_value_is_still_marked(doc: Document) -> None:
    """A warning about a value that is not there has to show that it is not there.
    An empty code span carries the same background and padding as any other,
    so it renders as a small box with nothing in it: measured at 8x18 against
    62x18 for one holding `Draft 2`."""
    from eta_publish.nodes import Shown

    doc.warn("the tab is named {}", Shown(""))
    out = HtmlEmitter().emit(doc)
    assert "the tab is named <code></code>" in out


def test_a_footnotes_mark_sits_outside_its_number(out: str) -> None:
    """Beside the arrow back it crowded the one control that was already there,
    so it hangs outside the list's own numbering instead."""
    footnote = re.findall(r'<li id="fn1">.*?</li>', out, re.S)[0]
    assert footnote.index("link-mark") < footnote.index("footnote-back")


def test_the_link_is_not_part_of_the_heading_text(out: str) -> None:
    """The `#` is drawn by the stylesheet:
    quoting a section title must not pick up a character nobody wrote,
    and a reader who cannot see the mark is given the label instead."""
    assert 'aria-label="Link to this section"></a>' in out
    assert "#</a>" not in out


def test_paragraphs_are_numbered_from_one_in_each_section(out: str) -> None:
    """Within the section rather than across the page:
    a paragraph added to the first section would otherwise renumber the last one."""
    for section in ("ground-conditions", "the-elephants-in-the-room"):
        numbers = [int(n) for n in re.findall(rf'<p id="{section}-p(\d+)"', out)]
        assert numbers == list(range(1, len(numbers) + 1))


def test_a_footnote_numbers_its_own_paragraphs(out: str) -> None:
    """Numbering a footnote's paragraphs along with the report
    would put 43 between 12 and 13,
    and nobody could do anything with that number."""
    assert '<p id="fn1-p1">' in out


EVIL = '"><script>alert(1)</script><x y="'


def test_an_attribute_value_comes_back_out_as_it_went_in() -> None:
    """Escaping is wrong in two directions, and a substring check sees neither.

    A value that escapes too little closes its own quotes,
    and a value that escapes too much reaches the page as `&amp;amp;`
    or as an apostrophe nobody typed.
    Both are the same failure to a reader: the attribute does not say
    what the document said. So it is read back and compared.
    """
    values = [EVIL, "a & b", "&amp;", "it's", 'say "hi"', "<>", "\u00e9 \u00a3 \u00b7", ""]
    for value in values:
        parsed = read(markup(a(id=value, title=value)))
        assert parsed.attrs == [{"id": value, "title": value}], value


def test_a_link_to_a_block_says_where_it_points() -> None:
    """`link_mark` builds its own tag, so what that tag says is worth reading back."""
    parsed = read(markup(link_mark(EVIL, EVIL)))
    assert parsed.tags == ["a"]
    assert parsed.attrs == [
        {"class": "link-mark", "href": f"#{EVIL}", "aria-label": f"Link to this {EVIL}"}
    ]


def test_a_hostile_document_opens_no_tag_of_its_own(doc: Document) -> None:
    """The round trip over a whole report, not over one primitive.

    A bug in `attributes` is the small half of this worry
    and the reviewed half; the larger half is a call site
    that wrote a value into an f-string and forgot to escape it.
    Reading the finished page back finds either.
    """
    doc.title = EVIL
    doc.meta["Short"] = EVIL
    doc.meta["SEO Description"] = EVIL
    doc.meta["Public Contributors"] = EVIL
    doc.warn("a warning about {}", Shown(EVIL))
    # Alt text is the document's too, and it reaches the page inside an attribute.
    # An image is frozen, and this is the one place anything writes to one.
    for image in doc.images:
        object.__setattr__(image, "alt", EVIL)
    for output in (HtmlEmitter().emit(doc), report_page(doc)):
        parsed = read(output)
        assert parsed.tags.count("script") == 1, "only the page's own script"
        assert parsed.tags.count("x") == 0, "the document opened no tag"
        assert EVIL in "".join(parsed.text), "the text itself survives, as text"


def test_an_absent_attribute_is_not_an_empty_one() -> None:
    """`None` leaves the attribute out, which is a different page.

    The distinction is the builder's rather than this emitter's,
    and every conditional attribute here is written as one:
    a `tabindex` that is `None` has to be no `tabindex` at all
    rather than `tabindex=""`, which is a real value meaning something else.
    """
    assert markup(a(title=None)) == "<a></a>"
    assert markup(a(title="")) == '<a title=""></a>'
    # Python will not take `class` as an argument name, and HTML will not take
    # anything else.
    assert markup(a(class_="x", aria_label="y")) == '<a class="x" aria-label="y"></a>'


def test_nothing_a_document_says_becomes_markup(doc: Document) -> None:
    """The document is the untrusted half of every page this builds."""
    doc.title = EVIL
    doc.meta["Short"] = EVIL
    doc.meta["SEO Description"] = EVIL
    doc.meta["Public Contributors"] = EVIL
    doc.warn("a warning about {}", Shown(EVIL))
    for output in (HtmlEmitter().emit(doc), report_page(doc)):
        assert "<script>alert(1)</script>" not in output
        assert "alert(1)" in output, "the text itself should survive, escaped"


def test_a_source_is_shown_without_its_www() -> None:
    """Only what is shown: the link still goes where the document said."""
    assert shown_url("https://www.mta.info/document/196361") == "mta.info/document/196361"
    assert shown_url("https://web.archive.org/x/www.a.b") == "web.archive.org/x/www.a.b"
