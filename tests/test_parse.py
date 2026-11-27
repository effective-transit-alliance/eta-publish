"""Parsing the fixture document into a tree."""

import json

import pytest
from paths import FIXTURE_DIR

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Document, Figure, Heading, Inline, List, ListKind, Paragraph, Text
from eta_publish.parse import Parser, parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


def _text(content: list[Inline]) -> str:
    return "".join(i.text for i in content if isinstance(i, Text))


def _summary(inlines: list[Inline]) -> list[tuple[str, str | None]]:
    """Each run's text and the one thing about it that is not plain: bold or a link."""
    return [
        (i.text, "bold" if i.bold else i.href)
        for i in inlines
        if isinstance(i, Text) and (i.bold or i.href)
    ]


def test_the_fixture_parses_to_the_publication() -> None:
    doc = parse(FIXTURE)

    # The headline comes from the body, not the Drive filename, and holds a colon
    # that a front-matter scan which did not stop at the title would swallow.
    assert doc.title == "Digging Out of a Very Deep Hole: Saving Billions on 125th Street"
    assert doc.title != FIXTURE["title"]
    assert doc.meta == {
        "URL": "/reports/digging-out-deep-hole-sas-west",
        "Short": "A 125 St subway should be a slam dunk.",
        "SEO Description": "Cheaper, shallower, faster.",
        "MTA SAS West Feasibility Study": "https://www.mta.info/document/196361",
    }

    # A short paragraph right after a figure stays a paragraph, not its caption.
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
    assert [(h.level, h.anchor) for h in doc.blocks if isinstance(h, Heading)] == [
        (2, "the-elephants-in-the-room"),
        (3, "ground-conditions"),
    ]

    intro = doc.blocks[1]
    assert isinstance(intro, Paragraph)
    assert _summary(intro.content) == [
        ("$7.7 billion", "bold"),
        ("MTA study", "https://www.mta.info/document/196361"),
    ]

    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert _text(figure.source) == "Source: sas-west-036.jpg"
    assert _text(figure.caption) == "The SAS West and Phase 2 alignments."
    assert _text(figure.credit) == "Credit: MTA"
    assert figure.image.alt == "SAS West alignment map"
    after = doc.blocks[3]
    assert isinstance(after, Paragraph)
    assert _text(after.content) == "That is a lot of money."

    # The list is rebuilt from flat nesting levels.
    node = next(b for b in doc.blocks if isinstance(b, List))
    assert node.kind is ListKind.BULLET
    assert [_text(i.content) for i in node.items] == ["First point", "Second point"]
    assert [_text(c.content) for c in node.items[0].children] == ["Nested point"]

    # Footnotes are numbered in reference order, and their bodies are parsed as blocks.
    assert [(f.number, f.footnote_id) for f in doc.footnotes] == [(1, "fn.a"), (2, "fn.b")]
    body = doc.footnotes[0].content[0]
    assert isinstance(body, Paragraph)
    assert _text(body.content) == "Inflation-adjusted from the 2024 capital plan."

    # `Source: sas-west-036.jpg` is the document saying which file the image is.
    assert [i.object_id for i in doc.images] == ["io.1"]
    assert doc.images[0].filename == "sas-west-036"

    # The `MTA SAS West Feasibility Study:` line is a reference the header carries,
    # kept in `meta` and not a field anything reads.
    assert [str(w) for w in doc.warnings] == [
        "the `Header` section has an unrecognized "
        "`MTA SAS West Feasibility Study:` line; check it for a typo",
    ]


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


def _picture(description: str) -> JsonObject:
    return {
        "inlineObjectProperties": {
            "embeddedObject": {
                "description": description,
                "imageProperties": {"contentUri": "https://example.invalid/" + description},
            }
        }
    }


def test_a_messy_document_warns_about_each_problem() -> None:
    """One header and body with a mistake of each kind a writer can make."""
    reference: JsonObject = {"footnoteReference": {"footnoteId": "fn.a"}}
    drawing = _text_para("Before the drawing.")
    drawing["paragraph"]["elements"].append({"inlineObjectElement": {"inlineObjectId": "io.4"}})
    twice = _text_para("A claim")
    twice["paragraph"]["elements"].insert(1, reference)
    twice["paragraph"]["elements"].append(reference)
    doc = parse(
        {
            "body": {
                "content": [
                    _text_para("Header", "HEADING_2"),
                    _field_para("URL: /reports/messy"),
                    _field_para("SEO Description: About it."),
                    _field_para("Short: The short."),
                    _field_para("Excerpt: The excerpt."),
                    _field_para("Mistyped Key: kept"),
                    _text_para("Publication", "TITLE"),
                    _image_para("io.1"),
                    _text_para("Caption one."),
                    _field_para("Source: named.jpg"),
                    _image_para("io.2"),
                    _text_para("Caption two."),
                    _image_para("io.3"),
                    _text_para("Caption three."),
                    _linked_para("Image Source", "https://www.flickr.com/photo_download.gne"),
                    _field_para("Credit: MTA"),
                    drawing,
                    twice,
                    _field_para("Source: orphan.jpg"),
                ]
            },
            "inlineObjects": {
                "io.1": _picture("one"),
                "io.2": _picture("two"),
                "io.3": _picture("three"),
                "io.4": {"inlineObjectProperties": {"embeddedObject": {}}},
            },
            "footnotes": {
                "fn.a": {"content": [_text_para("The note.")]},
                "fn.orphan": {"content": []},
            },
            "lists": {},
        }
    )
    assert [str(w) for w in doc.warnings] == [
        "the `Excerpt:` line is no longer used; rename it `Short:`",
        "the `Header` section has an unrecognized `Mistyped Key:` line; check it for a typo",
        "write `Image Source` as a `Source:` line above the image instead; "
        "it takes a URL as well: `https://www.flickr.com/photo_download.gne`",
        "inline object `io.4` is not a picture (a drawing or chart, perhaps), "
        "so it is missing from every output; replace it with an image",
        "`Source:` line not followed by an image, dropped: `Source: orphan.jpg`",
        "footnote `fn.orphan` is defined but never referenced; omitted",
    ]
    # Header: `Short:` is a field; `Excerpt:` is said to be renamed, not called a typo.
    assert doc.meta["Short"] == "The short."
    assert doc.meta["SEO Description"] == "About it."
    # Figures: a named source, a hashed name, and a source that is only a link.
    figures = [b for b in doc.blocks if isinstance(b, Figure)]
    assert [_text(f.source) for f in figures] == ["Source: named.jpg", "", "Image Source"]
    assert _text(figures[2].credit) == "Credit: MTA"
    assert doc.images[0].filename == "named"
    assert doc.images[1].filename.startswith("img-")
    # The drawing is dropped and the rest of its paragraph stays prose.
    assert [_text(b.content) for b in doc.blocks if isinstance(b, Paragraph)][0] == (
        "Before the drawing."
    )
    # A repeated reference keeps its number, and the unreferenced note is not numbered.
    assert [(f.footnote_id, f.number) for f in doc.footnotes] == [("fn.a", 1)]
    refs = [i for b in doc.blocks if isinstance(b, Paragraph) for i in b.content]
    assert [getattr(i, "number", None) for i in refs if hasattr(i, "footnote_id")] == [1, 1]


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


@pytest.mark.parametrize(
    "shape",
    ["paragraph below", "same paragraph", "no picture"],
)
def test_the_picture_under_social_title_card_is_the_share_card(shape: str) -> None:
    """It is the page's social image, not a figure, and the header goes on after it.

    The picture sits under the line, under a Shift+Enter in the same paragraph
    (which reads the same in Docs), or is missing, which is warned about."""
    field = _field_para("Social Title Card: card.png")
    header = [field]
    if shape == "paragraph below":
        header.append(_image_para("io.1"))
    elif shape == "same paragraph":
        field["paragraph"]["elements"].append({"inlineObjectElement": {"inlineObjectId": "io.1"}})
    doc = _social_card_doc(*header)
    assert doc.meta["Social Title Card"] == "card.png"
    assert doc.meta["SEO Description"] == "About it."
    assert not [b for b in doc.blocks if isinstance(b, Figure)]
    warned = [str(w) for w in doc.warnings if "Social Title Card" in str(w)]
    if shape == "no picture":
        assert doc.card is None
        assert [w for w in warned if "has no picture under it" in w]
    else:
        assert doc.card is not None
        assert doc.card.alt == "The card."
        assert doc.card.filename == "card"
        assert not warned


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


def _run(text: str, style: JsonObject) -> JsonObject:
    return {"textRun": {"content": text, "textStyle": style}}


def _rgb(**channels: float) -> JsonObject:
    return {"foregroundColor": {"color": {"rgbColor": channels}}}


def test_inline_styles_and_links_are_read() -> None:
    parser = Parser(FIXTURE)
    inlines = parser.inlines(
        {
            "elements": [
                _run("bold", {"bold": True}),
                _run("struck", {"strikethrough": True}),
                _run("orange", _rgb(red=1, green=0.6)),
                _run("black", _rgb()),
                # Black on a light page, and readable on a dark one.
                _run("near", _rgb(green=0.02, blue=0.09)),
                # Docs colors every link its own blue, which is not the writer choosing a color.
                _run(
                    "docs blue",
                    {
                        **_rgb(red=0.07, green=0.33, blue=0.8),
                        "link": {"url": "https://example.com/"},
                    },
                ),
                _run(
                    "long",
                    {
                        "link": {
                            "url": "https://archive.ph/20230101120000/https://example.com/page?a=1"
                        }
                    },
                ),
                _run("short", {"link": {"url": "https://archive.is/TVQXL"}}),
            ]
        }
    )
    runs = [i for i in inlines if isinstance(i, Text)]
    assert [(r.text, r.bold, r.strike, r.color, r.href) for r in runs] == [
        ("bold", True, False, None, None),
        ("struck", False, True, None, None),
        ("orange", False, False, "#ff9900", None),
        ("black", False, False, None, None),
        ("near", False, False, None, None),
        ("docs blue", False, False, None, "https://example.com/"),
        # An archive.today link naming its page is that page, which the Wayback Machine archives.
        ("long", False, False, None, "https://example.com/page?a=1"),
        # A short link says nothing of which page it captured, or when, so it is kept.
        ("short", False, False, None, "https://archive.is/TVQXL"),
    ]
    warned = [str(w) for w in parser.doc.warnings]
    assert warned == [
        "`https://archive.ph/20230101120000/https://example.com/page?a=1` is an archive.today link;"
        " link the page itself, `https://example.com/page?a=1`, instead,"
        " archived on `web.archive.org`",
        "`https://archive.is/TVQXL` is an archive.today link, which is undated;"
        " link the page itself instead, archived on `web.archive.org`",
    ]
