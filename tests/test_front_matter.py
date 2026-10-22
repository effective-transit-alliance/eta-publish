"""The top of the document, shaped the way the real publication is.

In the real doc `Header` is an `h2` while the body sections are `h1`,
and between them sit the headline,
a hero image with caption and credit, and an addendum.
A scan that runs "until the next heading of the same or higher level"
swallows all of it.
"""

import pytest

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Document, Figure, Inline, Paragraph, Text
from eta_publish.parse import parse


def _text(content: list[Inline]) -> str:
    return "".join(i.text for i in content if isinstance(i, Text))


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


def image_para() -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"inlineObjectElement": {"inlineObjectId": "io.hero"}}],
        }
    }


REAL_SHAPE: JsonObject = {
    "title": "SAS West Feasibility Response",
    "body": {
        "content": [
            para("Header", "HEADING_2"),  # deeper than the body sections
            field("Project Manager: Khyber Sen"),
            field("URL: /reports/digging-out-deep-hole-sas-west"),
            field("MTA SAS West Feasibility Study: https://www.mta.info/document/196361"),
            para("Digging Out of a Very Deep Hole: Saving Billions on 125th Street", "TITLE"),
            image_para(),
            para("Composite image of the MTA's station diagram."),
            field("Credit: MTA, ETA (Blair Lorenzo)"),
            para("Addendum: clarifying text was added on August 21, 2026."),
            para("The Elephants in the Room", "HEADING_1"),
            para("On paper, this should be a slam dunk."),
        ]
    },
    "inlineObjects": {
        "io.hero": {
            "inlineObjectProperties": {
                "embeddedObject": {
                    "description": "Composite of the station diagram",
                    "imageProperties": {"contentUri": "https://example.invalid/hero"},
                }
            }
        }
    },
    "footnotes": {},
    "lists": {},
}


@pytest.fixture
def doc() -> Document:
    return parse(REAL_SHAPE)


def test_the_header_section_ends_at_the_headline(doc: Document) -> None:
    assert set(doc.meta) == {"Project Manager", "URL", "MTA SAS West Feasibility Study"}
    assert "addendum" not in doc.meta


def test_the_headline_is_the_title(doc: Document) -> None:
    assert doc.title == "Digging Out of a Very Deep Hole: Saving Billions on 125th Street"


def test_the_hero_image_survives(doc: Document) -> None:
    """A paragraph holding only an image has no text,
    so a front-matter scan that overruns drops it without anything to warn about."""
    figures = [b for b in doc.blocks if isinstance(b, Figure)]
    assert len(figures) == 1
    assert figures[0].image.object_id == "io.hero"
    assert [i.object_id for i in doc.images] == ["io.hero"]


def test_the_hero_caption_and_credit_survive(doc: Document) -> None:
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert _text(figure.caption) == "Composite image of the MTA's station diagram."
    assert _text(figure.credit) == "Credit: MTA, ETA (Blair Lorenzo)"


def test_the_addendum_stays_body_text(doc: Document) -> None:
    """It matches `Key: value`, so an overrunning scan files it as metadata,
    but it is prose on the published page."""
    paragraphs = [
        "".join(i.text for i in b.content if isinstance(i, Text))
        for b in doc.blocks
        if isinstance(b, Paragraph)
    ]
    assert "Addendum: clarifying text was added on August 21, 2026." in paragraphs


def test_prose_ends_the_header_section_even_without_a_headline() -> None:
    doc = parse(
        {
            "title": "x",
            "body": {
                "content": [
                    para("Header", "HEADING_2"),
                    field("URL: /reports/x"),
                    para("This is body prose, not a key."),
                ]
            },
        }
    )
    assert set(doc.meta) == {"URL"}
    assert len(doc.blocks) == 1


def test_an_unstyled_headline_still_does_not_swallow_the_hero_image() -> None:
    """If the headline is not TITLE-styled,
    it matches `Key: value` and is filed as metadata,
    which `title` reports as a fallback.
    What must not also happen is the image after it disappearing without a word,
    which is what a scan that runs to the next same-or-higher heading does."""
    unstyled = {
        **REAL_SHAPE,
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("URL: /reports/digging-out-deep-hole-sas-west"),
                para("Digging Out of a Very Deep Hole: Saving Billions on 125th Street"),
                image_para(),
                para("The Elephants in the Room", "HEADING_1"),
            ]
        },
    }
    doc = parse(unstyled)
    assert [i.object_id for i in doc.images] == ["io.hero"]
    assert any("`Title`-styled" in w for w in map(str, doc.warnings))


def test_scaffolding_before_the_header_does_not_hide_it() -> None:
    """The real doc opens with a `Draft 2` line before its `Header` heading.
    Bailing on the first text meant no front matter was found at all,
    and `URL:` and the rest landed in the body as prose."""
    doc = parse(
        {
            "title": "SAS West Feasibility Response",
            "body": {
                "content": [
                    para("Draft 2"),
                    para("Header", "HEADING_2"),
                    field("URL: /reports/digging-out-deep-hole-sas-west"),
                    field("Short: A 125 St subway should be a slam dunk."),
                    para("The Real Headline", "TITLE"),
                    para("The Elephants in the Room", "HEADING_1"),
                ]
            },
        }
    )
    assert doc.meta["URL"] == "/reports/digging-out-deep-hole-sas-west"
    assert doc.meta["Short"] == "A 125 St subway should be a slam dunk."
    assert doc.title == "The Real Headline"


def test_dropped_scaffolding_is_reported() -> None:
    """It is production notes rather than the publication, so dropping it is right,
    but it must not leave silently."""
    doc = parse(
        {
            "title": "x",
            "body": {
                "content": [
                    para("Draft 2"),
                    para("Header", "HEADING_2"),
                    field("URL: /reports/x"),
                    para("Headline", "TITLE"),
                ]
            },
        }
    )
    assert any("Draft 2" in w for w in map(str, doc.warnings))


def test_a_document_with_no_header_section_is_left_intact() -> None:
    """The preamble scan must not eat a whole document a paragraph at a time
    when there is no `Header` heading to find."""
    doc = parse(
        {
            "title": "x",
            "body": {
                "content": [para("Just a Headline", "TITLE"), para("Body."), para("More body.")]
            },
        }
    )
    assert len([b for b in doc.blocks if isinstance(b, Paragraph)]) == 2
    assert doc.meta == {}
    assert any("no front matter found" in w for w in map(str, doc.warnings))


def test_a_headline_before_the_header_stops_the_search() -> None:
    """Past the headline the publication has started,
    so there is no header to look for and nothing may be consumed."""
    doc = parse(
        {
            "title": "x",
            "body": {
                "content": [
                    para("Headline", "TITLE"),
                    para("Body."),
                    para("Header", "HEADING_2"),
                    field("URL: /reports/x"),
                ]
            },
        }
    )
    assert doc.meta == {}
    assert len(doc.blocks) == 3


def test_contributors_are_sorted_by_surname() -> None:
    """`etany.org` credits contributors alphabetically,
    and the field they are typed into is in whatever order people were added."""
    doc = Document(meta={"Public Contributors": "Khyber Sen, Alon Levy, Robert Hale"})
    assert doc.contributors == ["Robert Hale", "Alon Levy", "Khyber Sen"]


def test_a_one_word_name_sorts_on_itself() -> None:
    doc = Document(meta={"Public Contributors": "Zoe, Alon Levy"})
    assert doc.contributors == ["Alon Levy", "Zoe"]


def test_the_date_is_written_out() -> None:
    """`etany.org` writes the month out; a Docs chip renders it short."""
    assert Document(meta={"Publish Due Date": "Aug 19, 2026"}).dateline == "August 19, 2026"


def test_a_day_is_not_padded() -> None:
    assert Document(meta={"Publish Due Date": "Aug 1, 2026"}).dateline == "August 1, 2026"


def test_a_date_already_written_out_is_left_alone() -> None:
    assert Document(meta={"Publish Due Date": "August 19, 2026"}).dateline == "August 19, 2026"


def test_something_that_is_not_a_date_is_published_as_written() -> None:
    """Guessing would be worse than showing what the header block says."""
    assert Document(meta={"Publish Due Date": "when it is ready"}).dateline == "when it is ready"


def test_no_date_is_still_no_dateline() -> None:
    assert Document().dateline == ""


def test_a_title_header_field_does_not_set_the_headline() -> None:
    """One way of saying it. A document carrying both publishes one of them,
    and which one should not be a fact about the parser."""
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Title: A Headline Nobody Sees"),
                para("Ordinary prose."),
            ]
        },
    }
    doc = parse(document)
    assert doc.title == "SAS West Feasibility Response"
    assert any("no `Title`-styled paragraph" in w for w in map(str, doc.warnings))
    assert any("not what the headline comes from" in w for w in map(str, doc.warnings))


def test_a_title_styled_paragraph_wins_and_says_nothing() -> None:
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Title: A Headline Nobody Sees"),
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    assert doc.title == "The Real Headline"
    assert not any("Title" in w for w in map(str, doc.warnings))


def test_a_field_written_twice_says_which_one_won() -> None:
    """A corrected line pasted below the original and a duplicate nobody meant
    look identical, and neither is visible in what gets published."""
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Short: The first answer."),
                field("Short: The second answer."),
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    assert doc.meta["Short"] == "The second answer."
    assert any(
        "more than one `Short:` line" in w
        and "`The second answer.`" in w
        and "`The first answer.`" in w
        for w in map(str, doc.warnings)
    )


def bled(text: str) -> JsonObject:
    """A paragraph whose underline ran past the colon, as Docs leaves it
    when the writer keeps typing after the name."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"textRun": {"content": text + "\n", "textStyle": {"underline": True}}}],
        }
    }


def test_a_line_that_is_not_underlined_is_not_a_field() -> None:
    """A sentence holding a colon is prose, whatever it looks like.

    This is the whole convention: the name is underlined, and a headline,
    a citation and `The answer was simple: build it shallower` are not."""
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("URL: /reports/x"),
                para("Short: A 125 St subway should be a slam dunk."),
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    assert doc.meta == {"URL": "/reports/x"}
    assert "Short" not in doc.meta


def test_an_underline_running_into_the_value_is_warned_about() -> None:
    """Docs carries the style forward as the writer keeps typing,
    which is the one mistake underlining a name invites."""
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                bled("Short: A 125 St subway should be a slam dunk."),
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    # Still the field it looks like: the underline is what needs fixing.
    assert doc.meta["Short"] == "A 125 St subway should be a slam dunk."
    assert any("runs past it into the value" in w for w in map(str, doc.warnings))


def test_a_linked_value_is_not_a_bled_underline() -> None:
    """Docs underlines every link, so a linked value looks bled and is not."""
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {"textRun": {"content": "URL", "textStyle": {"underline": True}}},
                            {
                                "textRun": {
                                    "content": ": /reports/x\n",
                                    "textStyle": {"link": {"url": "https://eta.info/reports/x"}},
                                }
                            },
                        ],
                    }
                },
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    assert doc.meta["URL"] == "/reports/x"
    assert not [w for w in map(str, doc.warnings) if "runs past it" in w]


def test_distinct_fields_are_not_a_repeat() -> None:
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Draft Due Date: Jul 17, 2026"),
                field("Press Due Date: Jul 21, 2026"),
                field("Publish Due Date: Aug 19, 2026"),
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    assert not any("more than one" in w for w in map(str, doc.warnings))


def test_two_fields_in_one_paragraph_are_two_fields() -> None:
    """A Shift+Enter between two fields reads like a paragraph break and is not one.

    The real brief writes `Short:` and `SEO Description:` that way.
    Taking only the first line of the paragraph would lose the second field,
    and ending the scan there would lose every field after it too.
    """
    document: JsonObject = {
        "title": "Noise Pollution",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Short: Too loud.\vSEO Description: Far too loud."),
                field("URL: /briefs/too-damn-loud"),
                para("The Real Headline", "TITLE"),
            ]
        },
    }
    doc = parse(document)
    assert doc.meta["Short"] == "Too loud."
    assert doc.meta["SEO Description"] == "Far too loud."
    assert doc.meta["URL"] == "/briefs/too-damn-loud"


def test_a_value_that_wraps_keeps_the_rest_of_itself() -> None:
    """A soft break inside one value continues it rather than ending the section."""
    document: JsonObject = {
        "title": "Noise Pollution",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Short: Too loud,\vand too long."),
                field("URL: /briefs/too-damn-loud"),
            ]
        },
    }
    doc = parse(document)
    assert doc.meta["Short"] == "Too loud, and too long."
    assert doc.meta["URL"] == "/briefs/too-damn-loud"


def test_a_shared_paragraph_says_so() -> None:
    """Two fields still publish, and the document is told it does not mean what it looks like."""
    document: JsonObject = {
        "title": "Noise Pollution",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Short: Too loud.\vSEO Description: Far too loud."),
            ]
        },
    }
    doc = parse(document)
    warning = next(w for w in map(str, doc.warnings) if "Shift+Enter" in w)
    assert "Short: Too loud." in warning
    assert "SEO Description: Far too loud." in warning


def _picture_in_the_header(*after: JsonObject) -> Document:
    """A `Header` section with a picture in it, the way Monthly Passes writes one."""
    return parse(
        {
            **REAL_SHAPE,
            "body": {
                "content": [
                    para("Header", "HEADING_2"),
                    field("URL: /reports/monthly-passes"),
                    image_para(),
                    *after,
                    para("Bring Back the Monthly", "HEADING_1"),
                    para("When the MTA retired the MetroCard."),
                ]
            },
        }
    )


def test_a_picture_does_not_end_the_header_section() -> None:
    """The line after it is still a header field, and one nothing recognizes
    is warned about as that rather than as a field somewhere no field goes."""
    doc = _picture_in_the_header(field("Description: Reasonably-priced monthly passes."))
    assert doc.meta["Description"] == "Reasonably-priced monthly passes."
    assert any("unrecognized `Description:`" in str(w) for w in doc.warnings)


def test_the_picture_in_the_header_section_is_still_the_publications() -> None:
    doc = _picture_in_the_header(field("Description: Reasonably-priced monthly passes."))
    assert [b.image.object_id for b in doc.blocks if isinstance(b, Figure)] == ["io.hero"]


def test_a_credit_under_a_picture_in_the_header_is_the_pictures() -> None:
    """It reads like a field, and it is the note of the picture above it."""
    doc = _picture_in_the_header(field("Credit: Blair Lorenzo, ETA"))
    assert "Credit" not in doc.meta
    figure = next(b for b in doc.blocks if isinstance(b, Figure))
    assert _text(figure.credit) == "Credit: Blair Lorenzo, ETA"


def test_the_subtitle_is_the_subtitle_styled_paragraph_under_the_headline() -> None:
    """Not `Short:`, which is what a search result previews."""
    document: JsonObject = {
        "title": "SAS West Feasibility Response",
        "body": {
            "content": [
                para("Header", "HEADING_2"),
                field("Short: The preview."),
                para("The Real Headline", "TITLE"),
                para(""),
                para("The subtitle.", "SUBTITLE"),
                para("The first paragraph."),
            ]
        },
    }
    doc = parse(document)
    assert doc.meta["Short"] == "The preview."
    assert doc.subtitle == [Text("The subtitle.")]
    assert [b for b in doc.blocks if isinstance(b, Paragraph)] == [
        Paragraph(content=[Text("The first paragraph.")])
    ]


def test_a_subtitle_below_the_publication_s_first_words_is_not_the_subtitle() -> None:
    document: JsonObject = {
        "title": "x",
        "body": {
            "content": [
                para("The Real Headline", "TITLE"),
                para("The first paragraph."),
                para("Not a subtitle.", "SUBTITLE"),
            ]
        },
    }
    assert parse(document).subtitle == []
