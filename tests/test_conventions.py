"""Conventions found in the real SAS West document.

Everything here was read off the actual doc and checked against the published page,
rather than guessed from the fixture.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any, override

import pytest
import requests
from paths import HOST, named_images

from eta_publish.checks import check_described
from eta_publish.docs_json import JsonObject
from eta_publish.emit.html import HtmlEmitter
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.emit.typst import TypstEmitter
from eta_publish.images import crop_svg, download, svg_description
from eta_publish.nodes import (
    Crop,
    Document,
    Figure,
    Heading,
    Image,
    Inline,
    Paragraph,
    Text,
    plain_text,
)
from eta_publish.parse import parse


def para(text: str, style: str = "NORMAL_TEXT") -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": style},
            "elements": [{"textRun": {"content": text + "\n", "textStyle": {}}}],
        }
    }


def field(text: str, style: str = "NORMAL_TEXT") -> JsonObject:
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


def image(object_id: str = "io.1") -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"inlineObjectElement": {"inlineObjectId": object_id}}],
        }
    }


def build(content: list[JsonObject], alt: str = "", crop: JsonObject | None = None) -> Document:
    return named_images(
        parse(
            {
                "title": "SAS West Feasibility Response",
                "body": {"content": content},
                "footnotes": {},
                "lists": {},
                "inlineObjects": {
                    "io.1": {
                        "inlineObjectProperties": {
                            "embeddedObject": {
                                "description": alt,
                                "imageProperties": {
                                    "contentUri": "https://x.invalid/1",
                                    "cropProperties": crop or {},
                                },
                            }
                        }
                    }
                },
            }
        )
    )


def text_of(content: list[Inline]) -> str:
    return "".join(i.text for i in content if isinstance(i, Text))


# ---- `[Image Source](...)` -----------------------------------------

APPENDIX = [
    para("Header", "HEADING_2"),
    field("URL: /reports/x"),
    para("Headline", "TITLE"),
    image(),
    para("A photo inside the Freedom Tunnel, showing room for 4 tracks."),
    field("[Image Source](https://www.flickr.com/photo_download.gne?id=4490800374)"),
    field("[Credit: Logan Hicks](https://www.flickr.com/photos/loganhicks/4490800374/)"),
    para("The Freedom Tunnel was formerly the 4-track West Side Line."),
]


@pytest.fixture
def appendix() -> Document:
    return build(APPENDIX)


def test_image_source_lines_attach_to_the_figure(appendix: Document) -> None:
    """The doc writes `Source: <file>` before an image in the body
    and `[Image Source](<url>)` after the caption in the appendices.
    Both are editorial; neither appears on the published page."""
    figure = next(b for b in appendix.blocks if isinstance(b, Figure))
    assert "Image Source" in text_of(figure.source)
    assert text_of(figure.caption).startswith("A photo inside the Freedom Tunnel")
    assert "Credit: Logan Hicks" in text_of(figure.credit)


def image_source(url: str) -> JsonObject:
    """`Image Source` as the document has it: the whole line is the link."""
    run = {"textRun": {"content": "Image Source\n", "textStyle": {"link": {"url": url}}}}
    return {"paragraph": {"paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}, "elements": [run]}}


@pytest.mark.parametrize(
    ("url", "filename"),
    [
        ("https://upload.wikimedia.org/wikipedia/commons/d/d9/W125irtjeh.JPG", "W125irtjeh"),
        # The page Flickr serves a download from, not a file.
        ("https://www.flickr.com/photo_download.gne?id=4490800374", ""),
    ],
)
def test_an_image_source_link_names_the_image_after_its_file(url: str, filename: str) -> None:
    doc = build([*APPENDIX[:5], image_source(url)])
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.image.named == bool(filename)
    if filename:
        assert figure.image.filename == filename


def test_an_image_source_is_warned_to_be_a_source_line(appendix: Document) -> None:
    """One label in one place: `Source:` above the image takes a URL as well."""
    (warning,) = [str(w) for w in appendix.warnings if "Image Source" in str(w)]
    assert "Source:" in warning
    assert "flickr.com/photo_download.gne" in warning


def test_image_source_does_not_become_a_paragraph(appendix: Document) -> None:
    paragraphs = [text_of(b.content) for b in appendix.blocks if isinstance(b, Paragraph)]
    assert paragraphs == ["The Freedom Tunnel was formerly the 4-track West Side Line."]


@pytest.mark.parametrize(
    "emitter", [HtmlEmitter(site_url=HOST), TypstEmitter(site_url=HOST)], ids=["html", "typst"]
)
def test_image_source_never_reaches_a_published_output(
    emitter: HtmlEmitter | TypstEmitter, appendix: Document
) -> None:
    """`Image Source` appears zero times on the live page."""
    # The page lists its warnings, and one says to write `Source:` instead,
    # which names the label without publishing the note.
    appendix.warnings.clear()
    out = emitter.emit(appendix)
    assert "Image Source" not in out
    assert "flickr.com/photo_download" not in out
    # The label is underlined in the document, so it reaches the page in two runs.
    assert "Logan Hicks" in out


def test_the_description_reaches_the_preview() -> None:
    from eta_publish.emit.html import publication_page

    doc = build(
        [
            para("Header", "HEADING_2"),
            field("SEO Description: Cheaper and shallower."),
            para("Headline", "TITLE"),
        ]
    )
    assert 'content="Cheaper and shallower."' in publication_page(doc, site_url=HOST)


def test_a_credit_line_that_is_not_underlined_is_not_a_credit() -> None:
    """A label is a label because it is underlined.
    Nothing else tells `Credit: MTA` from a caption that happens to say it."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            para("A caption."),
            para("Credit: MTA"),
        ]
    )
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.credit == []


def test_the_underline_marking_a_label_is_not_published() -> None:
    """It says the line is a label rather than anything to a reader,
    so a figure's credit does not reach the page with a rule under it."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            para("A caption."),
            field("Credit: MTA"),
        ]
    )
    out = HtmlEmitter(site_url=HOST).emit(doc)
    assert '<figcaption class="figure-credit">Credit: MTA</figcaption>' in out
    assert "<u>" not in out


# ---- alt text -------------------------------------------------------


def test_the_caption_becomes_alt_text_when_docs_has_none(appendix: Document) -> None:
    """On the live page the caption appears twice:
    as the image's `alt` and as visible small text beneath it.
    The `alt` drops the opening "A photo", which a screen reader would say again."""
    figure = next(b for b in appendix.blocks if isinstance(b, Figure))
    assert figure.image.alt == "Inside the Freedom Tunnel, showing room for 4 tracks."
    assert figure.caption and plain_text(figure.caption).startswith("A photo inside")


def test_a_real_description_wins_over_the_caption() -> None:
    doc = build(APPENDIX, alt="Four tracks under Riverside Park")
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.image.alt == "Four tracks under Riverside Park"


# ---- found by running against the real document ---------------------


def test_a_qualified_source_line_is_still_editorial() -> None:
    """The real publication writes `Source:`, `Uncropped Source:`, and `[Image Source](...)`.
    All three appear zero times on the published page,
    against 26 occurrences of `Credit:`."""
    for label in ("Source:", "Uncropped Source:", "Cropped Source:"):
        doc = build(
            [
                para("Header", "HEADING_2"),
                field("URL: /reports/x"),
                para("Headline", "TITLE"),
                field(f"{label} sas-west-036.jpg"),
                image(),
                para("A caption."),
            ]
        )
        figure = next(b for b in doc.blocks if isinstance(b, Figure))
        assert label in text_of(figure.source), label
        assert not [b for b in doc.blocks if isinstance(b, Paragraph)], label
        assert label not in HtmlEmitter(site_url=HOST).emit(doc), label


def test_an_image_styled_as_a_heading_becomes_a_figure() -> None:
    """The real doc has one, from inserting an image while a heading style was active.
    Treated as a heading it produced an empty one, whose anchor is a published URL,
    and buried the image inside it."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            para("Tail Tracks", "HEADING_2"),
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "HEADING_3"},
                    "elements": [{"inlineObjectElement": {"inlineObjectId": "io.1"}}],
                }
            },
        ]
    )
    assert [b.anchor for b in doc.blocks if isinstance(b, Heading)] == ["tail-tracks"]
    assert len([b for b in doc.blocks if isinstance(b, Figure)]) == 1
    assert any("styled as a `Heading`" in w for w in map(str, doc.warnings))


def test_unfinished_text_is_reported() -> None:
    """The real doc contains `TODO insert PSD image, maybe JFK AirTrain?`,
    which the human publisher removed by hand.
    Nothing removes it here, so the least the build can do is say it is there."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            para("TODO insert PSD image, maybe JFK AirTrain?"),
        ]
    )
    assert any("unfinished text" in w for w in map(str, doc.warnings))


def bolded(*pieces: tuple[str, bool]) -> JsonObject:
    """A paragraph of text runs, each either bold or not."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [
                {"textRun": {"content": text, "textStyle": {"bold": True} if bold else {}}}
                for text, bold in pieces
            ],
        }
    }


def _unfinished(doc: Document) -> list[str]:
    return [w for w in map(str, doc.warnings) if "unfinished text" in w]


def _with_header(*body: JsonObject) -> Document:
    return build(
        [para("Header", "HEADING_2"), field("URL: /reports/x"), para("Headline", "TITLE"), *body]
    )


def test_bold_text_in_brackets_is_unfinished() -> None:
    """A bold bracketed note is a placeholder, as much as a `TODO` is."""
    doc = _with_header(bolded(("Ridership grew ", False), ("[need a source]", True), (".", False)))
    assert _unfinished(doc) == ["unfinished text in the document: `[need a source]`"]


def test_brackets_around_bold_text_need_not_be_bold() -> None:
    doc = _with_header(bolded(("Grew [", False), ("cite", True), ("].", False)))
    assert _unfinished(doc) == ["unfinished text in the document: `[cite]`"]


def test_brackets_that_are_not_all_bold_are_prose() -> None:
    doc = _with_header(
        bolded(("A [quoted ", False), ("emphasis", True), (" aside].", False)),
        bolded(("Plain [brackets] and ", False), ("bold", True), (" apart.", False)),
    )
    assert _unfinished(doc) == []


def test_chart_asset_placeholders_are_editorial() -> None:
    """`SVG:` and `PNG:` name a chart file for whoever assembles the page.
    The live publication carries real download links instead."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            para("Station length as a percentage of platform length."),
            field("SVG: station-length.svg"),
        ]
    )
    assert "SVG:" not in HtmlEmitter(site_url=HOST).emit(doc)
    assert not [b for b in doc.blocks if isinstance(b, Paragraph)]


def test_an_undescribed_image_is_reported() -> None:
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
        ]
    )
    check_described(doc)
    assert any("no alt text and no caption" in w for w in map(str, doc.warnings))


def test_a_caption_labelled_caption_is_warned_about() -> None:
    """Nothing reads a `Caption:` label, so IBX published the word in its caption."""
    doc = build([image(), para("Caption: A rendering."), field("Credit: MTA")])
    [warning] = [w for w in map(str, doc.warnings) if "Caption:" in w]
    assert warning.startswith("the caption of image `img-")
    assert warning.endswith(
        "starts with `Caption:`, which is published as part of it; take it out in the doc"
    )


def test_a_soft_line_break_separates_a_caption_from_its_credit() -> None:
    """The hero image's caption and credit are one paragraph split by Shift+Enter,
    which Docs encodes as a vertical tab inside the run."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            field("Composite image of the station diagram.\v\vCredit: MTA, ETA"),
        ]
    )
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert text_of(figure.caption) == "Composite image of the station diagram."
    assert text_of(figure.credit) == "Credit: MTA, ETA"


def test_a_paragraph_after_a_credit_is_not_the_caption() -> None:
    """IBX's chart of automated lines by year has a `Credit:` and no caption,
    and the paragraph after it is body text, not the chart's caption."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            field("Credit: ETA"),
            para("Moreover, even the MTA IBX staff have told us so."),
        ]
    )
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.caption == []
    assert text_of(figure.credit) == "Credit: ETA"
    after = doc.blocks[-1]
    assert isinstance(after, Paragraph)
    assert text_of(after.content) == "Moreover, even the MTA IBX staff have told us so."


def test_soft_line_breaks_do_not_reach_the_output_as_control_characters() -> None:
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            para("One line.\vAnother line."),
        ]
    )
    for emitted in (HtmlEmitter(site_url=HOST).emit(doc), TypstEmitter(site_url=HOST).emit(doc)):
        assert "\v" not in emitted
    assert "One line.<br>Another line." in HtmlEmitter(site_url=HOST).emit(doc)


def _svg_doc(mime: str = "image/svg+xml", uri: str = "https://drive.google.com/open?id=ABC123"):
    return build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [
                        {"textRun": {"content": "SVG", "textStyle": {"underline": True}}},
                        {"textRun": {"content": ": ", "textStyle": {}}},
                        {
                            "richLink": {
                                "richLinkProperties": {
                                    "title": "chart.svg",
                                    "uri": uri,
                                    "mimeType": mime,
                                }
                            }
                        },
                    ],
                }
            },
            para("A bar graph comparing costs."),
        ]
    )


def test_a_linked_svg_becomes_the_figure_file() -> None:
    """Docs cannot place an SVG,
    so a chart is pasted as a raster and the real file linked beside it.
    Every output here can show the vector."""
    figure = next(b for b in _svg_doc().blocks if isinstance(b, Figure))
    assert figure.image.vector is not None
    assert figure.image.vector.file_id == "ABC123"
    assert figure.image.vector.filename.endswith(".svg")


def test_the_svg_line_is_still_not_published() -> None:
    doc = _svg_doc()
    assert "SVG:" not in HtmlEmitter(site_url=HOST).emit(doc)
    assert "drive.google.com" not in HtmlEmitter(site_url=HOST).emit(doc)


def test_a_source_line_that_links_no_vector_leaves_the_raster() -> None:
    """`SVG: TODO`, which the real publication also contains, is a note."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            field("SVG: TODO"),
        ]
    )
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.image.vector is None


def test_a_non_vector_link_is_not_mistaken_for_one() -> None:
    doc = _svg_doc(mime="image/png")
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.image.vector is None
    assert "the `SVG:` line links `chart.svg`, which is not an SVG; the raster is used" in [
        str(w) for w in doc.warnings
    ]


SVG_URL = "https://raw.githubusercontent.com/kkysen/automated-metro-data/main/charts/share.svg"


def _linked_svg_doc(crop: JsonObject | None = None) -> Document:
    url = SVG_URL
    return build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [
                        {"textRun": {"content": "SVG", "textStyle": {"underline": True}}},
                        {"textRun": {"content": ": ", "textStyle": {}}},
                        {"textRun": {"content": url + "\n", "textStyle": {"link": {"url": url}}}},
                    ],
                }
            },
        ],
        crop=crop,
    )


def test_an_svg_linked_outside_drive_becomes_the_figure_file() -> None:
    """IBX's charts are linked from GitHub, not Drive, and as plain links."""
    figure = next(b for b in _linked_svg_doc().blocks if isinstance(b, Figure))
    assert figure.image.vector is not None
    assert figure.image.vector.file_id == ""
    assert figure.image.vector.uri == SVG_URL
    assert figure.image.vector.filename == "share.svg"


def test_a_cropped_linked_svg_is_named_for_its_crop() -> None:
    """The crop is fractions of the raster, which is the whole SVG drawn out,
    so it carries over to the vector, and recropping renames it as it does a raster."""
    plain = next(b for b in _linked_svg_doc().blocks if isinstance(b, Figure))
    cropped = next(
        b for b in _linked_svg_doc(crop={"offsetLeft": 0.1}).blocks if isinstance(b, Figure)
    )
    assert plain.image.vector is not None
    assert cropped.image.vector is not None
    assert plain.image.vector.filename == "share.svg"
    assert cropped.image.vector.filename.startswith("share-")
    assert cropped.image.vector.filename.endswith(".svg")


def test_a_crop_is_mirrored_onto_the_svg() -> None:
    """The original is nested whole, after its XML declaration, and not rewritten."""
    svg = (
        b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
        b'viewBox=\'0 0 760 436\' width="760" height="436"><g/></svg>\n'
    )
    out = crop_svg(svg, Crop(left=0.1, right=0.1, top=0.25, bottom=0.25))
    assert out == (
        b'<?xml version="1.0"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="76 109 608 218" '
        b'width="608" height="218"><svg width="760" height="436">'
        b"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox='0 0 760 436' "
        b'width="760" height="436"><g/></svg></svg></svg>\n'
    )


def test_a_crop_without_a_size_is_taken_from_the_viewbox() -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><g/></svg>'
    out = crop_svg(svg, Crop(top=0.5))
    assert out.startswith(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 50 200 50" '
        b'width="200" height="50"><svg width="200" height="100">'
    )


def runs(*pieces: tuple[str, bool]) -> JsonObject:
    """A paragraph of text runs, each either italic or not."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [
                {"textRun": {"content": text, "textStyle": {"italic": True} if italic else {}}}
                for text, italic in pieces
            ],
        }
    }


def linked(doc: Document) -> list[tuple[str, str | None]]:
    para = next(b for b in doc.blocks if isinstance(b, Paragraph))
    return [(t.text, t.href) for t in para.content if isinstance(t, Text)]


def test_an_italicized_section_name_becomes_a_link() -> None:
    """Docs cannot link to a heading in the same document,
    so the publication italicizes the section's name and means a link by it."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Station Depth", "HEADING_2"),
                    runs(("See ", False), ("Station Depth", True), (" for more.\n", False)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert linked(doc) == [
        ("See ", None),
        ("Station Depth", "#station-depth"),
        (" for more.", None),
    ]


def test_the_italics_come_off_once_it_is_a_link() -> None:
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Fire Code", "HEADING_2"),
                    runs(("Fire Code", True)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    para_node = next(b for b in doc.blocks if isinstance(b, Paragraph))
    assert [t.italic for t in para_node.content if isinstance(t, Text)] == [False]


def test_a_reference_can_precede_the_section_it_names() -> None:
    """The publication links to `Station Depth` long before reaching it."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    runs(("as suggested in ", False), ("Station Depth", True)),
                    para("Station Depth", "HEADING_2"),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert linked(doc)[1] == ("Station Depth", "#station-depth")


def test_a_name_split_across_runs_still_matches() -> None:
    """Docs splits a run wherever styling changes, mid-name included."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Tail Tracks", "HEADING_2"),
                    runs(("Tail ", True), ("Tracks", True)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert [href for _, href in linked(doc)] == ["#tail-tracks", "#tail-tracks"]


def test_case_and_spacing_are_forgiven() -> None:
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Ruling Grade", "HEADING_2"),
                    runs(("ruling  grade", True)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert linked(doc) == [("ruling  grade", "#ruling-grade")]


def test_italics_that_name_no_section_stay_italics() -> None:
    """The real publication italicizes `and` and `tens of billions` for emphasis."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Fire Code", "HEADING_2"),
                    runs(("tens of billions", True)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    para_node = next(b for b in doc.blocks if isinstance(b, Paragraph))
    text = next(t for t in para_node.content if isinstance(t, Text))
    assert text.italic and text.href is None


def test_an_italicized_link_is_left_alone() -> None:
    """Already a link, and to somewhere the author chose."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Fire Code", "HEADING_2"),
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Fire Code",
                                        "textStyle": {
                                            "italic": True,
                                            "link": {"url": "https://nfpa.test/130"},
                                        },
                                    }
                                }
                            ],
                        }
                    },
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert linked(doc) == [("Fire Code", "https://nfpa.test/130")]


def test_a_section_named_before_its_colon_still_matches() -> None:
    """`Appendix A: Freedom Tunnel` is referred to as `Appendix A`,
    which is how the live page links it."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Appendix A: Freedom Tunnel", "HEADING_2"),
                    runs(("see ", False), ("Appendix A", True)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert linked(doc)[1] == ("Appendix A", "#appendix-a-freedom-tunnel")


def test_the_full_name_wins_over_a_shortened_one() -> None:
    """A heading actually called `Appendix A` keeps its own anchor."""
    doc = parse(
        {
            "title": "A publication",
            "body": {
                "content": [
                    para("Appendix A", "HEADING_2"),
                    para("Appendix A: Freedom Tunnel", "HEADING_2"),
                    runs(("Appendix A", True)),
                ]
            },
            "footnotes": {},
            "lists": {},
        }
    )
    assert linked(doc) == [("Appendix A", "#appendix-a")]


def test_a_soft_line_break_is_warned_about_wherever_it_is() -> None:
    """It still publishes as the line break it is; the warning is that Docs
    draws Shift+Enter and Enter almost alike and stores them differently,
    so nobody can see which one a paragraph was written with."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            para("One line.\vAnother line."),
        ]
    )
    warning = next(w for w in map(str, doc.warnings) if "Shift+Enter" in w)
    assert "One line." in warning
    assert "Another line." in warning


def test_a_prose_paragraph_after_a_figure_is_warned_about_once() -> None:
    """A paragraph in the caption slot that turns out to be prose is read twice
    unless the parser keeps what it read, and said everything twice with it."""
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            para("A caption."),
            para("Prose.\vMore prose."),
        ]
    )
    assert sum("Shift+Enter" in w for w in map(str, doc.warnings)) == 1


def test_a_soft_break_with_nothing_on_one_side_is_called_spacing() -> None:
    doc = build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            para("\vA paragraph pushed down the page."),
        ]
    )
    assert any("standing in for blank space" in w for w in map(str, doc.warnings))


class Serving(requests.Session):
    """Answers the SVG link with `svg`, and anything else with a raster nothing should ask for."""

    def __init__(self, svg: bytes) -> None:
        super().__init__()
        self.svg = svg
        self.asked: list[str] = []

    @override
    def get(self, url: str | bytes, **kwargs: Any) -> requests.Response:
        self.asked.append(str(url))
        response = requests.Response()
        response.status_code = 200
        response._content = self.svg if url == SVG_URL else b"\x89PNG"
        return response


def test_a_linked_svg_that_is_not_one_warns_and_publishes_no_picture(tmp_path: Path) -> None:
    """A link that answers with a page instead of the chart is a problem in the doc,
    and the raster is never the stand-in: it is there only because Docs cannot place an SVG."""
    session = Serving(b"<!doctype html><html><body><svg></svg></body></html>")
    doc = _linked_svg_doc()
    download(doc, tmp_path, session=session)
    assert (
        "could not download the vector `share.svg` (it is not an SVG); "
        "the figure is published without a picture"
    ) in [str(w) for w in doc.warnings]
    assert session.asked == [SVG_URL]
    assert "io.1" in doc.unpublished
    assert not list(tmp_path.glob("*.png"))
    html = HtmlEmitter(site_url=HOST).emit(doc)
    assert "<img" not in html
    assert "<figure" in html
    assert "![" not in MarkdownEmitter().emit(doc)
    assert "capped_image(" not in TypstEmitter(site_url=HOST).emit(doc)


def test_an_svg_that_cannot_be_cropped_is_published_whole(tmp_path: Path) -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100%"><g/></svg>'
    doc = _linked_svg_doc(crop={"offsetLeft": 0.1})
    download(doc, tmp_path, session=Serving(svg))
    assert [str(w) for w in doc.warnings] == [
        "could not crop the vector `share.svg` "
        "(it has neither a `viewBox` nor a fixed size to crop by); it is published uncropped"
    ]
    assert (tmp_path / doc.image_files["io.1"]).read_bytes() == svg


def test_a_linked_svg_is_downloaded_again_when_it_changes(tmp_path: Path) -> None:
    """IBX links its charts from a branch, so the URL stays put when a chart is redrawn."""
    old = b'<svg xmlns="http://www.w3.org/2000/svg"><g id="old"/></svg>'
    new = b'<svg xmlns="http://www.w3.org/2000/svg"><g id="new"/></svg>'
    download(_linked_svg_doc(), tmp_path, session=Serving(old))
    doc = _linked_svg_doc()
    download(doc, tmp_path, session=Serving(new))
    assert (tmp_path / doc.image_files["io.1"]).read_bytes() == new


def test_a_saved_response_still_downloads_its_svg_again(tmp_path: Path) -> None:
    """An unedited document is rebuilt from its saved response, which has no image URLs,
    and a chart's link can point somewhere new without the document being edited."""
    old = b'<svg xmlns="http://www.w3.org/2000/svg"><g id="old"/></svg>'
    new = b'<svg xmlns="http://www.w3.org/2000/svg"><g id="new"/></svg>'
    download(_linked_svg_doc(), tmp_path, session=Serving(old))
    doc = _linked_svg_doc()
    for figure in (b for b in doc.blocks if isinstance(b, Figure)):
        figure.image = replace(figure.image, source_uri=None)
    download(doc, tmp_path, session=Serving(new))
    assert (tmp_path / doc.image_files["io.1"]).read_bytes() == new


def test_an_offline_build_uses_the_svg_it_has(tmp_path: Path) -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><g/></svg>'
    download(_linked_svg_doc(), tmp_path, session=Serving(svg))
    doc = _linked_svg_doc()
    session = Serving(b"")
    download(doc, tmp_path, session=session, offline=True)
    assert session.asked == []
    assert (tmp_path / doc.image_files["io.1"]).read_bytes() == svg


def test_a_linked_svg_describes_its_figure() -> None:
    """IBX's charts have no alt text in Docs, but each SVG titles and describes itself,
    and the SVG is the picture that publishes."""
    doc = _linked_svg_doc()
    doc.image_alts["io.1"] = "Share of new lines automated. 135/361 are automated."
    check_described(doc)
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.image.alt == "Share of new lines automated. 135/361 are automated."
    assert not [w for w in map(str, doc.warnings) if "no alt text" in w]


def test_an_svg_describes_itself_by_its_own_title_and_desc() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><title>Share &gt; GoA2, by year</title>'
        b"<desc>135/361 are automated.</desc><g><title>2016: 5/26</title></g></svg>"
    )
    assert svg_description(svg) == "Share > GoA2, by year. 135/361 are automated."


def test_a_crop_of_an_svg_sized_in_another_unit_is_in_pixels() -> None:
    """Only the ratio matters, so any fixed unit will do."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="1in" height="0.5in"><g/></svg>'
    out = crop_svg(svg, Crop(left=0.5))
    assert out.startswith(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="48 0 48 48" '
        b'width="48" height="48"><svg width="96" height="48">'
    )


# ---- a `Source:` in one of our GitHub repos -------------------------

LIVE_BLOB = "https://github.com/effective-transit-alliance/charts/blob/main/out/map.png"
LIVE_RAW = "https://raw.githubusercontent.com/effective-transit-alliance/charts/main/out/map.png"


def _live_doc(url: str, crop: JsonObject | None = None) -> Document:
    return build(
        [
            para("Header", "HEADING_2"),
            field("URL: /reports/x"),
            para("Headline", "TITLE"),
            image(),
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [
                        {"textRun": {"content": "Source", "textStyle": {"underline": True}}},
                        {"textRun": {"content": ": ", "textStyle": {}}},
                        {"textRun": {"content": url + "\n", "textStyle": {"link": {"url": url}}}},
                    ],
                }
            },
        ],
        crop=crop,
    )


def _live_figure(url: str) -> Figure:
    return next(b for b in _live_doc(url).blocks if isinstance(b, Figure))


@pytest.mark.parametrize("url", [LIVE_BLOB, LIVE_RAW, LIVE_BLOB.replace("/blob/", "/raw/")])
def test_a_source_in_our_repos_is_downloaded_from_there(url: str) -> None:
    assert _live_figure(url).image.live_uri == LIVE_RAW


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/someone-else/charts/blob/main/out/map.png",
        "https://github.com/kkysen/automated-metro-data",
        "https://example.com/kkysen/charts/blob/main/map.png",
    ],
)
def test_a_source_anywhere_else_is_only_cited(url: str) -> None:
    figure = _live_figure(url)
    assert figure.image.live_uri == ""
    assert figure.image.vector is None


def test_an_svg_source_in_our_repos_is_the_vector() -> None:
    """The same as an `SVG:` line linking it."""
    figure = _live_figure(
        SVG_URL.replace("raw.githubusercontent.com", "github.com").replace(
            "automated-metro-data/main", "automated-metro-data/blob/main"
        )
    )
    assert figure.image.vector is not None
    assert figure.image.vector.uri == SVG_URL
    assert figure.image.vector.filename == "share.svg"
    assert figure.image.live_uri == ""


def _png(width: int, height: int) -> bytes:
    import io

    from PIL import Image as Pillow

    buffer = io.BytesIO()
    Pillow.new("RGB", (width, height)).save(buffer, "PNG")
    return buffer.getvalue()


class Live(requests.Session):
    """Serves the live source with `live`, or fails it when `live` is `None`."""

    def __init__(self, live: bytes | None) -> None:
        super().__init__()
        self.live = live
        self.asked: list[str] = []

    @override
    def get(self, url: str | bytes, **kwargs: Any) -> requests.Response:
        self.asked.append(str(url))
        response = requests.Response()
        response.url = str(url)
        if url == LIVE_RAW:
            response.status_code = 404 if self.live is None else 200
            response._content = self.live or b""
            # What `raw.githubusercontent.com` says of much it serves.
            response.headers["content-type"] = "text/plain; charset=utf-8"
        else:
            response.status_code = 200
            response._content = _png(10, 10)
            response.headers["content-type"] = "image/png"
        return response


def test_a_live_source_is_published_with_the_documents_crop(tmp_path: Path) -> None:
    from PIL import Image as Pillow

    doc = _live_doc(LIVE_BLOB, crop={"offsetLeft": 0.5})
    session = Live(_png(200, 100))
    download(doc, tmp_path, session=session)
    assert session.asked == [LIVE_RAW, "https://x.invalid/1"]
    with Pillow.open(tmp_path / doc.image_files["io.1"]) as written:
        assert written.size == (100, 100)


def test_a_live_source_that_fails_falls_back_to_the_documents_copy(tmp_path: Path) -> None:
    doc = _live_doc(LIVE_BLOB)
    session = Live(None)
    download(doc, tmp_path, session=session)
    assert session.asked == [LIVE_RAW, "https://x.invalid/1"]
    assert (tmp_path / doc.image_files["io.1"]).read_bytes() == _png(10, 10)
    assert any(f"`{LIVE_RAW}`" in w and "copy in the document" in w for w in map(str, doc.warnings))


def test_a_live_source_unlike_the_documents_copy_warns(tmp_path: Path) -> None:
    doc = _live_doc(LIVE_BLOB)
    download(doc, tmp_path, session=Live(_png(20, 10)))
    assert (tmp_path / doc.image_files["io.1"]).read_bytes() == _png(20, 10)
    assert any("differs from its source" in w for w in map(str, doc.warnings))


def test_a_live_source_matching_the_documents_copy_is_quiet(tmp_path: Path) -> None:
    doc = _live_doc(LIVE_BLOB)
    download(doc, tmp_path, session=Live(_png(10, 10)))
    assert not doc.warnings


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/kkysen/charts/releases/download/v1.2/map.png",
        "https://github.com/kkysen/charts/releases/latest/download/map.png",
    ],
)
def test_a_release_asset_in_our_repos_is_downloaded_from_there(url: str) -> None:
    assert _live_figure(url).image.live_uri == url


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/kkysen/charts/releases/tag/v1.2",
        "https://github.com/kkysen/charts/releases/latest",
        "https://github.com/someone-else/charts/releases/download/v1.2/map.png",
    ],
)
def test_a_release_page_or_someone_elses_asset_is_only_cited(url: str) -> None:
    assert _live_figure(url).image.live_uri == ""


def test_a_live_source_reencoded_in_the_document_is_quiet(tmp_path: Path) -> None:
    """Docs may rewrite a pasted file's bytes; the picture is what is compared."""
    import io

    from PIL import Image as Pillow

    buffer = io.BytesIO()
    Pillow.new("RGB", (10, 10)).save(buffer, "PNG", compress_level=0)
    assert buffer.getvalue() != _png(10, 10)
    doc = _live_doc(LIVE_BLOB)
    download(doc, tmp_path, session=Live(buffer.getvalue()))
    assert not doc.warnings


def test_a_live_source_docs_shrank_is_quiet(tmp_path: Path) -> None:
    """Docs shrinks a wide paste, so its copy is the picture at a smaller size."""
    import io

    from PIL import Image as Pillow

    def encoded(picture: Pillow.Image) -> bytes:
        buffer = io.BytesIO()
        picture.save(buffer, "PNG")
        return buffer.getvalue()

    gradient = Pillow.linear_gradient("L").convert("RGB").resize((400, 200))
    live = encoded(gradient)

    class Shrunk(Live):
        @override
        def get(self, url: str | bytes, **kwargs: Any) -> requests.Response:
            response = super().get(url, **kwargs)
            if url != LIVE_RAW:
                response._content = encoded(gradient.resize((200, 100)))
            return response

    doc = _live_doc(LIVE_BLOB)
    download(doc, tmp_path, session=Shrunk(live))
    assert not doc.warnings


def test_a_renamed_image_is_found_under_its_old_name(tmp_path: Path) -> None:
    """A saved response has no image URLs, so a picture a code change renamed
    is the file the last build recorded for it, saved under its new name."""
    images = tmp_path / "images"
    images.mkdir()
    (images / "img-0c475eea.jpg").write_bytes(b"card")
    (tmp_path / "images.json").write_text('{"io.card": {"file": "img-0c475eea.jpg"}}')
    doc = Document(card=Image(object_id="io.card", filename="ibx_automation-0c475eea"))
    download(doc, images, session=Serving(b""), offline=True)
    assert doc.image_files["io.card"] == "ibx_automation-0c475eea.jpg"
    assert (images / "ibx_automation-0c475eea.jpg").read_bytes() == b"card"


def test_an_alt_text_saying_image_elsewhere_is_warned_about() -> None:
    """Dropping "image" from "Composite image of" would leave "Composite of",
    which only a person can judge."""
    doc = build([image(), para("Composite image of two stations."), field("Credit: MTA")])
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert figure.image.alt == "Composite image of two stations."
    check_described(doc)
    [warning] = [w for w in map(str, doc.warnings) if "screen reader" in w]
    assert "says `image`" in warning
