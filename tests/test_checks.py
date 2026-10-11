"""What a report has to have before it is published."""

import json
from dataclasses import replace

import pytest
from paths import FIXTURE_DIR

from eta_publish.checks import check, check_pages
from eta_publish.nodes import (
    Archived,
    Block,
    Document,
    Figure,
    Heading,
    Image,
    Inline,
    Paragraph,
    Text,
)
from eta_publish.parse import REQUIRED_FIELDS, parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


@pytest.fixture
def doc() -> Document:
    parsed = parse(FIXTURE)
    parsed.warnings.clear()
    parsed.meta = {field: "something" for field in REQUIRED_FIELDS}
    return parsed


def _labelled(label: str, rest: str) -> list[Inline]:
    """A line whose label is underlined, which is how the document writes one."""
    return [Text(text=label, underline=True), Text(text=rest)]


def test_a_complete_header_is_not_warned_about(doc: Document) -> None:
    check(doc)
    assert doc.warnings == []


def test_a_missing_field_is_named(doc: Document) -> None:
    """By name, rather than as a list of twelve:
    a warning naming one line is a line to go and add."""
    del doc.meta["Discussion Channel"]
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "the `Header` section has no `Discussion Channel:` line"
    ]


def test_seo_is_spelled_the_way_the_document_spells_it(doc: Document) -> None:
    del doc.meta["SEO Description"]
    check(doc)
    assert "`SEO Description:`" in str(doc.warnings[0])


def test_an_empty_field_is_not_a_filled_one(doc: Document) -> None:
    doc.meta["URL"] = "   "
    check(doc)
    assert [str(w) for w in doc.warnings] == ["the `Header` section leaves `URL:` empty"]


def test_an_empty_private_list_is_an_answer(doc: Document) -> None:
    """A report with nobody uncredited has an empty line, and that is the answer."""
    doc.meta["Private Contributors"] = ""
    check(doc)
    assert doc.warnings == []


def test_an_empty_sme_liaison_is_an_answer(doc: Document) -> None:
    """Not every report has a subject-matter expert to check it."""
    doc.meta["SME/Liaison"] = ""
    check(doc)
    assert doc.warnings == []


@pytest.mark.parametrize("field", ["SME/Liaison", "Goals", "Audience"])
def test_the_planning_fields_are_required(doc: Document, field: str) -> None:
    del doc.meta[field]
    check(doc)
    assert [str(w) for w in doc.warnings] == [f"the `Header` section has no `{field}:` line"]


def test_a_document_with_no_header_is_left_to_the_parser(doc: Document) -> None:
    """`parse` has already said so; twelve more warnings would bury it."""
    doc.meta.clear()
    check(doc)
    assert doc.warnings == []


def test_an_seo_description_over_the_limit_shows_what_is_cut(doc: Document) -> None:
    """Which words are lost is the thing to fix,
    and a count of characters over does not say which they are."""
    doc.meta["SEO Description"] = "x" * 300 + " and this is lost"
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "`SEO Description:` is 317 characters, over the 300 a search result shows:\n> "
        + "x" * 300
        + "~~ and this is lost~~"
    ]


def test_an_seo_description_at_the_limit_is_fine(doc: Document) -> None:
    doc.meta["SEO Description"] = "x" * 300
    check(doc)
    assert doc.warnings == []


def figure(*, caption: bool = True, credit: bool = True, named: bool = True) -> Figure:
    return Figure(
        image=Image(object_id="io.9", filename="a-diagram", named=named),
        caption=[Text(text="What it shows.")] if caption else [],
        credit=_labelled("Credit", ": MTA") if credit else [],
    )


def test_a_figure_with_both_is_not_warned_about(doc: Document) -> None:
    doc.blocks = [figure()]
    check(doc)
    assert doc.warnings == []


UNREAD_CREDIT = (
    "the image `a-diagram` has a `Credit:` line under it that is not read as its credit, "
    "because `Credit` is not underlined; underline it in the doc"
)


def test_a_credit_left_as_prose_under_a_figure_says_why(doc: Document) -> None:
    """IBX's lead image: its `Credit:` is not underlined, so it publishes as a
    paragraph, after the table of contents the image is moved above."""
    doc.blocks = [figure(credit=False), Paragraph(content=[Text(text="Credit: MTA")])]
    check(doc)
    assert [str(w) for w in doc.warnings] == [UNREAD_CREDIT]


def test_a_credit_taken_for_the_caption_says_why(doc: Document) -> None:
    """The only line under the image is the caption, whatever it says."""
    doc.blocks = [replace(figure(credit=False), caption=[Text(text="Credit: MTA")])]
    check(doc)
    assert [str(w) for w in doc.warnings] == [UNREAD_CREDIT]


def test_an_uncaptioned_figure_is_named_by_its_file(doc: Document) -> None:
    """The Docs object id is not something the document shows anybody."""
    doc.blocks = [figure(caption=False)]
    check(doc)
    assert [str(w) for w in doc.warnings] == ["the image `a-diagram` has no caption"]


def test_an_unattributed_figure_is_flagged(doc: Document) -> None:
    """These reports run other people's diagrams on nearly every page."""
    doc.blocks = [figure(credit=False)]
    check(doc)
    assert [str(w) for w in doc.warnings] == ["the image `a-diagram` has no `Credit:` line"]


def test_a_figure_missing_both_says_both(doc: Document) -> None:
    doc.blocks = [figure(caption=False, credit=False)]
    check(doc)
    assert len(doc.warnings) == 2


def test_an_unfinished_header_line_is_flagged(doc: Document) -> None:
    """The body walk never sees the header: it is consumed before that walk begins."""
    doc.meta["Short"] = "TODO write this"
    check(doc)
    assert [str(w) for w in doc.warnings] == ["`Short:` is still marked unfinished"]


def test_open_suggestions_are_flagged(doc: Document) -> None:
    """A build resolves them away, so what publishes looks finished and is not."""
    doc.open_suggestions = 3
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "3 suggestions still open on this tab; "
        "the build publishes the document without them, as it reads today"
    ]


def test_one_open_comment_is_not_called_comments(doc: Document) -> None:
    doc.open_comments = 1
    check(doc)
    assert [str(w) for w in doc.warnings] == ["1 comment thread still open on this tab"]


def test_a_document_under_no_review_says_nothing(doc: Document) -> None:
    check(doc)
    assert doc.warnings == []


def test_an_unnamed_image_is_flagged(doc: Document) -> None:
    """Without a `Source:` line the published URL is a hash of a Docs object id."""
    doc.blocks = [figure(named=False)]
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "1 image is unnamed, so each publishes under a hash; "
        "give each a `Source:` line naming its file:\n- `a-diagram`: What it shows."
    ]


def test_an_unnamed_image_falls_back_to_its_alt_text(doc: Document) -> None:
    """A picture with no caption still has to be told apart from the others."""
    bare = figure(caption=False, named=False)
    bare.image = replace(bare.image, alt="A cross-section of the station box")
    doc.blocks = [bare]
    check(doc)
    listed = str(doc.warnings[-1]).split("\n")[-1]
    assert listed == "- `a-diagram`: A cross-section of the station box"


def test_an_image_a_human_named_img_is_not_unnamed(doc: Document) -> None:
    """`img-` is what an unnamed image is called,
    and also a name a `Source:` line is free to give one."""
    named = figure()
    named.image = replace(named.image, filename="img-of-the-tunnel", named=True)
    doc.blocks = [named]
    check(doc)
    assert doc.warnings == []


def test_an_address_beside_a_name_is_not_published(doc: Document) -> None:
    """A byline is names. Docs writes the address when it cannot resolve
    a person chip to a display name, and the name is typed beside it."""
    doc.meta["Public Contributors"] = "Alon Levy (alon@example.org), Khyber Sen"
    assert doc.contributors == ["Alon Levy", "Khyber Sen"]


def test_a_missing_comma_after_an_address_is_warned_about(doc: Document) -> None:
    """It reads as one contributor, sorted under a surname belonging to neither."""
    doc.meta["Public Contributors"] = "Franklin Tang (ft@example.org) Madison Feinberg, Khyber Sen"
    check(doc)
    assert any("a comma is missing after the address" in w for w in map(str, doc.warnings))


def test_names_without_addresses_are_left_alone(doc: Document) -> None:
    """Two bare names run together are two words,
    and nothing here can tell those from a double-barrelled surname."""
    doc.meta["Public Contributors"] = "Ada Lovelace, Grace Hopper"
    check(doc)
    assert doc.contributors == ["Grace Hopper", "Ada Lovelace"]
    assert not any("comma is missing" in w for w in map(str, doc.warnings))


# ---- a tracking tag left on a source ---------------------------------


def citing(*hrefs: str) -> list[Block]:
    """A body that is one paragraph of links, each written as words."""
    return [Paragraph(content=[Text(text="a source", href=href) for href in hrefs])]


def test_a_tracking_tag_left_on_a_source_is_flagged(doc: Document) -> None:
    """It publishes where the link was read rather than anything about the page.

    It also costs the source its archived copy in the index, which has no row
    for a URL nothing links to.
    """
    doc.blocks = citing("https://a.example/story?utm_source=chatgpt.com")
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "1 source still carries the tag it was copied with; take it off the link in the doc:\n"
        "- `utm_source=chatgpt.com` on `https://a.example/story?utm_source=chatgpt.com`"
    ]


def test_every_utm_parameter_on_one_source_is_named(doc: Document) -> None:
    """All of them, because taking one off and leaving two is not the fix."""
    doc.blocks = citing("https://a.example/story?utm_source=x&utm_medium=email&id=7")
    check(doc)
    assert "`utm_source=x&utm_medium=email`" in str(doc.warnings[0])


def test_a_tag_after_another_parameter_is_found(doc: Document) -> None:
    """`?id=7&utm_source=x` is the same mistake as `?utm_source=x`."""
    doc.blocks = citing("https://a.example/story?id=7&utm_source=x")
    check(doc)
    assert doc.warnings


def test_an_ordinary_query_is_left_alone(doc: Document) -> None:
    """A parameter that changes the page is part of the source, not a tag on it."""
    doc.blocks = citing("https://a.example/search?q=slurry&page=2")
    check(doc)
    assert doc.warnings == []


def test_a_parameter_that_merely_ends_in_utm_is_not_a_tag(doc: Document) -> None:
    """The prefix is what names these, and `?autm_source=` is not one."""
    doc.blocks = citing("https://a.example/story?autm_source=x")
    check(doc)
    assert doc.warnings == []


def test_all_the_tagged_sources_are_listed_together(doc: Document) -> None:
    """One warning rather than one each: it is one fix repeated."""
    doc.blocks = citing(
        "https://a.example/one?utm_source=x", "https://b.example/two?utm_campaign=y"
    )
    check(doc)
    assert len(doc.warnings) == 1
    assert str(doc.warnings[0]).startswith("2 sources still carry the tag")


def test_a_header_field_in_the_body_is_warned_about(doc: Document) -> None:
    """A `Short:` line under the headline is not the header's `Short:`.

    It publishes as a paragraph, and the field it was meant to fill
    is reported missing elsewhere in the same build.
    """
    doc.blocks = [Paragraph(content=_labelled("Short", ": A 125 St subway should be a slam dunk."))]
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "`Short:` is a `Header` field, and this one is outside it: "
        "`Short: A 125 St subway should be a slam dunk.`"
    ]


def test_a_header_field_in_a_caption_is_warned_about(doc: Document) -> None:
    """`Credit:` and `Phase:` look alike enough in a document
    that one lands where the other belongs."""
    doc.blocks = [
        Figure(
            image=Image(object_id="io.1", filename="x.png", named=True),
            caption=_labelled("Phase", ": Compositing"),
            credit=_labelled("Credit", ": MTA"),
        )
    ]
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "`Phase:` is a `Header` field, and this one is outside it: `Phase: Compositing`"
    ]


def test_an_unrecognized_field_in_the_body_is_warned_about(doc: Document) -> None:
    """`Sort:` in the body is a line nothing reads,
    whether it was meant for the header or meant to be prose."""
    doc.blocks = [Paragraph(content=_labelled("Sort", ": A 125 St subway."))]
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "`Sort:` reads as a field and is not one: `Sort: A 125 St subway.`"
    ]


def test_a_figure_note_is_ordinary_under_a_picture(doc: Document) -> None:
    """`Source:` and `Credit:` are how a figure is written,
    so they are strays only in prose."""
    doc.blocks = [
        Figure(
            image=Image(object_id="io.1", filename="x.png", named=True),
            source=[Text(text="Source: sas-west-036.jpg")],
            caption=[Text(text="The SAS West alignment.")],
            credit=_labelled("Credit", ": MTA"),
        )
    ]
    check(doc)
    assert doc.warnings == []


def test_a_figure_note_loose_in_the_body_is_warned_about(doc: Document) -> None:
    """Nothing claimed it, so it publishes as a paragraph reading `Source: ...`."""
    doc.blocks = [Paragraph(content=_labelled("Source", ": sas-west-036.jpg"))]
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "`Source:` reads as a field and is not one: `Source: sas-west-036.jpg`"
    ]


def test_a_heading_holding_a_colon_is_not_a_stray_field(doc: Document) -> None:
    """`Appendix A: Freedom Tunnel` is a section name, and the report is full of them."""
    doc.blocks = [
        Heading(level=2, anchor="appendix-a", content=[Text(text="Appendix A: Freedom Tunnel")])
    ]
    check(doc)
    assert doc.warnings == []


def test_prose_holding_a_colon_is_not_a_stray_field(doc: Document) -> None:
    """Warning on every `and then: this` would make the check worth turning off."""
    doc.blocks = [
        Paragraph(content=[Text(text="The answer was simple: build it shallower.")]),
        Paragraph(content=[Text(text="Phases of the project: three.")]),
        Paragraph(content=[Text(text='Barbara Russo-Lennon, "Subway spots: the ad blitz."')]),
    ]
    check(doc)
    assert doc.warnings == []


def _citing(*hrefs: str) -> Document:
    return Document(blocks=[Paragraph(content=[Text(text=href, href=href) for href in hrefs])])


def test_a_page_past_the_end_of_the_pdf_is_named() -> None:
    doc = _citing("https://a.example/a.pdf#page=150", "https://a.example/a.pdf#page=6")
    doc.archives["https://a.example/a.pdf"] = Archived(snapshot="s", timestamp="t", pages=6)
    check_pages(doc)
    assert [str(w) for w in doc.warnings] == [
        "1 PDF citation cites a page the PDF does not have:\n"
        "- `https://a.example/a.pdf#page=150` cites page 150 of 6 pages"
    ]


def test_a_page_that_is_not_a_number_is_named() -> None:
    doc = _citing("https://a.example/a.pdf#page=0", "https://a.example/a.pdf#page=iv&zoom=80")
    check_pages(doc)
    assert len(doc.warnings) == 1
    assert "`https://a.example/a.pdf#page=0` names no page" in str(doc.warnings[0])
    assert "`https://a.example/a.pdf#page=iv&zoom=80` names no page" in str(doc.warnings[0])


def test_an_uncounted_pdf_is_left_alone() -> None:
    doc = _citing("https://a.example/a.pdf#page=150&zoom=80")
    check_pages(doc)
    assert doc.warnings == []


def test_a_url_typed_out_but_not_linked_is_named() -> None:
    doc = Document(
        blocks=[
            Paragraph(
                content=[
                    Text(text="Badoe. https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242). "),
                    Text(text="See (https://a.example/x), and "),
                    Text(text="a linked page", href="https://linked.example/"),
                    Text(text="."),
                ]
            )
        ]
    )
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "2 URLs typed out but not linked; link each in the doc:\n"
        "- `https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242)`\n"
        "- `https://a.example/x`"
    ]


def test_a_url_split_across_styles_is_one_url() -> None:
    doc = Document(
        blocks=[Paragraph(content=[Text(text="At https://a.exam"), Text(text="ple/x", bold=True)])]
    )
    check(doc)
    assert "`https://a.example/x`" in str(doc.warnings[0])


def test_a_link_that_shows_its_url_is_named() -> None:
    doc = Document(
        blocks=[
            Paragraph(
                content=[
                    Text(text="See "),
                    Text(text="https://a.example/", href="https://a.example/"),
                    Text(text="x", href="https://a.example/", bold=True),
                    Text(text=" and "),
                    Text(text="the ridership figures", href="https://b.example/"),
                    Text(text="."),
                ]
            )
        ]
    )
    check(doc)
    assert [str(w) for w in doc.warnings] == [
        "1 link shows its URL as its text; give it words in the doc:\n- `https://a.example/x`"
    ]


def test_open_suggestions_are_warned_about(doc: Document) -> None:
    doc.open_suggestions = 3
    check(doc)
    assert any("3 suggestions still open" in w for w in map(str, doc.warnings))


def test_open_suggestions_are_not_warned_about_in_a_preview_of_them(doc: Document) -> None:
    doc.open_suggestions = 3
    doc.suggestions_accepted = True
    check(doc)
    assert not any("suggestions still open" in w for w in map(str, doc.warnings))
