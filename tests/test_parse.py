"""Parsing the fixture document into a tree."""

import json

import pytest
from paths import FIXTURE_DIR

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Document, Figure, Heading, Inline, List, ListKind, Paragraph, Text
from eta_publish.parse import Parser, parse, plain

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


@pytest.fixture
def doc() -> Document:
    return parse(FIXTURE)


def _text(content: list[Inline]) -> str:
    return "".join(i.text for i in content if isinstance(i, Text))


def _para(parser: Parser, text: str) -> list[Inline]:
    """Find the fixture paragraph containing `text` and parse its inlines."""
    for item in FIXTURE["body"]["content"]:
        para = item.get("paragraph")
        if para and text in json.dumps(para):
            return parser.inlines(para)
    raise AssertionError(f"no fixture paragraph contains {text!r}")


# ---- inline --------------------------------------------------------


def test_styles_and_links_survive() -> None:
    inlines = _para(Parser(FIXTURE), "7.7 billion")
    assert [i.text for i in inlines if isinstance(i, Text) and i.bold] == ["$7.7 billion"]
    linked = [i for i in inlines if isinstance(i, Text) and i.href]
    assert linked[0].href == "https://www.mta.info/document/196361"


def test_a_repeated_reference_keeps_its_number() -> None:
    parser = Parser(FIXTURE)
    assert parser._footnote_ref({"footnoteId": "fn.a"}).number == 1
    assert parser._footnote_ref({"footnoteId": "fn.a"}).number == 1


# ---- document ------------------------------------------------------


def test_the_headline_comes_from_the_body_not_the_filename(doc: Document) -> None:
    """The Drive filename is a working name.
    The real doc is called `SAS West Feasibility Response`, which is not what publishes."""
    assert doc.title == "Digging Out of a Very Deep Hole: Saving Billions on 125th Street"
    assert doc.title != FIXTURE["title"]


def test_a_title_containing_a_colon_is_not_eaten_as_front_matter(doc: Document) -> None:
    """`Digging Out...: Saving Billions...` matches `Key: value`,
    so a front-matter scan that does not stop at TITLE swallows the headline."""
    assert "digging out of a very deep hole" not in doc.meta
    assert doc.meta["URL"] == "/reports/digging-out-deep-hole-sas-west"


def test_an_unrecognized_header_key_is_kept_and_does_not_end_the_scan(doc: Document) -> None:
    """The real doc has an `MTA SAS West Feasibility Study:` line,
    which a whitelist would have leaked into the body."""
    assert doc.meta["MTA SAS West Feasibility Study"] == "https://www.mta.info/document/196361"
    assert doc.meta["SEO Description"] == "Cheaper, shallower, faster."


def test_the_fixture_raises_only_the_header_field_warnings(doc: Document) -> None:
    """The `MTA SAS West Feasibility Study:` line above is a reference the header
    carries and not a field anything reads."""
    assert [str(w) for w in doc.warnings] == [
        "the `Header` section has an unrecognized "
        "`MTA SAS West Feasibility Study:` line; check it for a typo",
    ]


# ---- blocks --------------------------------------------------------


def test_block_structure(doc: Document) -> None:
    assert [type(b).__name__ for b in doc.blocks] == [
        "Heading",
        "Paragraph",
        "Figure",
        "Paragraph",
        "Table",
        "Heading",
        "List",
        "Paragraph",
    ]


def test_headings_carry_levels_and_anchors(doc: Document) -> None:
    headings = [b for b in doc.blocks if isinstance(b, Heading)]
    assert [(h.level, h.anchor) for h in headings] == [
        (2, "the-elephants-in-the-room"),
        (3, "ground-conditions"),
    ]


def test_a_figure_absorbs_its_source_caption_and_credit(doc: Document) -> None:
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert _text(figure.source) == "Source: sas-west-036.jpg"
    assert _text(figure.caption) == "The SAS West and Phase 2 alignments."
    assert _text(figure.credit) == "Credit: MTA"
    assert figure.image.alt == "SAS West alignment map"


def test_a_short_paragraph_after_a_figure_stays_a_paragraph(doc: Document) -> None:
    """Folding captions by length would swallow body text,
    and a publication with 54 figures has many short paragraphs following one."""
    after = doc.blocks[3]
    assert isinstance(after, Paragraph)
    assert _text(after.content) == "That is a lot of money."


def test_nested_lists_are_rebuilt_from_flat_nesting_levels(doc: Document) -> None:
    node = next(b for b in doc.blocks if isinstance(b, List))
    assert node.kind is ListKind.BULLET
    assert [_text(i.content) for i in node.items] == ["First point", "Second point"]
    assert [_text(c.content) for c in node.items[0].children] == ["Nested point"]


# ---- footnotes -----------------------------------------------------


def test_footnotes_are_numbered_in_reference_order(doc: Document) -> None:
    assert [(f.number, f.footnote_id) for f in doc.footnotes] == [(1, "fn.a"), (2, "fn.b")]


def test_footnote_bodies_are_parsed_as_blocks(doc: Document) -> None:
    body = doc.footnotes[0].content[0]
    assert isinstance(body, Paragraph)
    assert _text(body.content) == "Inflation-adjusted from the 2024 capital plan."


def test_an_unreferenced_footnote_is_reported_rather_than_numbered() -> None:
    doc_json = json.loads(json.dumps(FIXTURE))
    orphan: JsonObject = {"content": []}
    doc_json["footnotes"]["fn.orphan"] = orphan
    doc = parse(doc_json)
    assert [f.footnote_id for f in doc.footnotes] == ["fn.a", "fn.b"]
    assert any("fn.orphan" in w for w in map(str, doc.warnings))


# ---- images --------------------------------------------------------


def test_images_are_collected_with_stable_names(doc: Document) -> None:
    assert [i.object_id for i in doc.images] == ["io.1"]
    # `Source: sas-west-036.jpg` is the document saying which file this is.
    assert doc.images[0].filename == "sas-west-036"


def test_an_image_the_document_names_no_source_for_keeps_its_hashed_name() -> None:
    doc_json = json.loads(json.dumps(FIXTURE))
    doc_json["body"]["content"] = [
        item
        for item in doc_json["body"]["content"]
        if "paragraph" not in item or not plain(item["paragraph"]).startswith("Source:")
    ]
    doc = parse(doc_json)
    assert doc.images[0].filename.startswith("img-")


def test_a_source_line_with_no_image_is_reported_not_dropped_silently() -> None:
    doc_json = json.loads(json.dumps(FIXTURE))
    doc_json["body"]["content"].append(_field_para("Source: orphan.jpg"))
    doc = parse(doc_json)
    assert any("orphan.jpg" in w for w in map(str, doc.warnings))


def _text_para(text: str, style: str = "NORMAL_TEXT") -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": style},
            "elements": [{"textRun": {"content": text + "\n", "textStyle": {}}}],
        }
    }


def _field_para(text: str, style: str = "NORMAL_TEXT") -> JsonObject:
    """A paragraph whose labels are underlined, which is how the document writes one.

    The name up to the first colon of each line: a label is a label because it
    is underlined, so a test meaning one has to write it the way the doc does.
    """
    runs: list[JsonObject] = []
    for n, line in enumerate(text.split("\v")):
        if n:
            runs.append({"textRun": {"content": "\v", "textStyle": {}}})
        mark = min((line.find(c) for c in ":]" if c in line), default=-1)
        if mark >= 0:
            runs.append({"textRun": {"content": line[:mark], "textStyle": {"underline": True}}})
        runs.append({"textRun": {"content": line[mark:] if mark >= 0 else line, "textStyle": {}}})
    runs[-1]["textRun"]["content"] += "\n"
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style}, "elements": runs}}


def _linked_para(text: str, url: str) -> JsonObject:
    """A paragraph that is nothing but a link, which is one way a figure names its source.

    A link carries no underline of its own: Docs draws one for every link,
    and the parser drops it for that reason, so the link is what marks the label.
    """
    style = {"link": {"url": url}}
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"textRun": {"content": text + "\n", "textStyle": style}}],
        }
    }


def _image_para(object_id: str) -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"inlineObjectElement": {"inlineObjectId": object_id}}],
        }
    }


def test_a_bare_image_source_link_is_still_an_editorial_note() -> None:
    """The doc writes this both ways.
    Where the brackets are typed the text reads `[Image Source](<url>)`;
    where the whole paragraph is simply the link,
    it reads `Image Source` and nothing else,
    and both name the file the figure came from rather than saying anything to a reader."""
    doc = parse(
        {
            "body": {
                "content": [
                    _text_para("Publication", "TITLE"),
                    _image_para("io.1"),
                    _text_para("A caption."),
                    _linked_para("Image Source", "https://www.flickr.com/photo_download.gne"),
                    _field_para("Credit: MTA"),
                ]
            },
            "inlineObjects": {
                "io.1": {
                    "inlineObjectProperties": {
                        "embeddedObject": {
                            "description": "alt",
                            "imageProperties": {"contentUri": "https://example.invalid/1"},
                        }
                    }
                }
            },
            "footnotes": {},
            "lists": {},
        }
    )
    figures = [b for b in doc.blocks if isinstance(b, Figure)]
    assert len(figures) == 1
    assert _text(figures[0].source) == "Image Source"
    assert _text(figures[0].credit) == "Credit: MTA"
    assert not [b for b in doc.blocks if isinstance(b, Paragraph)]


def _social_card_doc(*header: JsonObject) -> Document:
    return parse(
        {
            "body": {
                "content": [
                    _text_para("Header", "HEADING_2"),
                    _field_para("URL: /reports/r"),
                    *header,
                    _field_para("SEO Description: About it."),
                    _text_para("Publication", "TITLE"),
                    _text_para("The body."),
                ]
            },
            "inlineObjects": {
                "io.1": {
                    "inlineObjectProperties": {
                        "embeddedObject": {
                            "description": "The card.",
                            "imageProperties": {"contentUri": "https://example.invalid/1"},
                        }
                    }
                }
            },
            "footnotes": {},
            "lists": {},
        }
    )


def test_the_picture_under_social_title_card_is_the_share_card() -> None:
    """It is the page's social image, not a figure, and the header goes on after it."""
    doc = _social_card_doc(_field_para("Social Title Card: card.png"), _image_para("io.1"))
    assert doc.card is not None
    assert doc.card.alt == "The card."
    assert doc.meta["Social Title Card"] == "card.png"
    assert doc.card.filename == "card"
    assert doc.meta["SEO Description"] == "About it."
    assert not [b for b in doc.blocks if isinstance(b, Figure)]
    assert not [w for w in doc.warnings if "Social Title Card" in str(w)]


def test_the_picture_can_share_the_social_title_card_paragraph() -> None:
    """Under a Shift+Enter rather than a paragraph break, which reads the same in Docs."""
    field = _field_para("Social Title Card: card.png")
    field["paragraph"]["elements"].append({"inlineObjectElement": {"inlineObjectId": "io.1"}})
    doc = _social_card_doc(field)
    assert doc.card is not None
    assert doc.meta["Social Title Card"] == "card.png"
    assert not [b for b in doc.blocks if isinstance(b, Figure)]


def test_a_social_title_card_line_with_no_picture_under_it_warns() -> None:
    doc = _social_card_doc(_field_para("Social Title Card: card.png"))
    assert doc.card is None
    assert [w for w in doc.warnings if "has no picture under it" in str(w)]


def test_an_excerpt_line_is_said_to_be_no_longer_used() -> None:
    """Not a typo to check for, as an unknown field is, but a line to rename."""
    doc = _social_card_doc(_field_para("Excerpt: The excerpt."))
    warnings = [str(w) for w in doc.warnings]
    assert "the `Excerpt:` line is no longer used; rename it `Short:`" in warnings
    assert not [w for w in warnings if "unrecognized" in w]


def test_a_short_is_a_header_field() -> None:
    doc = _social_card_doc(_field_para("Short: The short."))
    assert doc.meta["Short"] == "The short."
    assert not [w for w in doc.warnings if "Short" in str(w)]


def test_a_subtitle_finishing_a_headline_that_ends_in_a_colon_is_part_of_the_title() -> None:
    """The publication's name is both halves, though the page sets the second as the standfirst."""
    doc = parse(
        {
            "body": {
                "content": [
                    _text_para("Digging Out of a Very Deep Hole:", "TITLE"),
                    _text_para("Saving Billions on 125th Street", "SUBTITLE"),
                    _text_para("The body."),
                ]
            },
            "inlineObjects": {},
            "footnotes": {},
            "lists": {},
        }
    )
    assert doc.title == "Digging Out of a Very Deep Hole: Saving Billions on 125th Street"
    assert doc.subtitle_ends_title
    assert doc.subtitle
