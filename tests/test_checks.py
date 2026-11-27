"""What a publication has to have before it is published.

Each test is one realistic document, built the way a build builds one,
that has a whole kind of problem in it (or none),
and asserts every warning the writer is told, in the order they are told.
"""

from pathlib import Path

from docs_json import (
    build,
    drafted,
    field,
    image,
    link,
    para,
    rich,
    warned,
)

from eta_publish.checks import CHART_FLATNESS, check
from eta_publish.docs_json import JsonObject
from eta_publish.parse import parse
from eta_publish.publish import Suggestions

SEO_LIMIT = 300

SVG = "https://raw.githubusercontent.com/kkysen/automated-metro-data/main/charts/share.svg"


def picture(name: str, flatness: float | None = None) -> dict[str, object]:
    """What `images.json` records of one picture: the file it was written as, and how flat it is."""
    entry: dict[str, object] = {"file": f"{name}.png"}
    if flatness is not None:
        entry["flatness"] = flatness
    return entry


ALTS = {f"io.{n}": f"Alt text {n}" for n in range(1, 11)} | {
    "io.8": "A cross-section of the station box"
}


def figure(
    heading: str, source: str | None, object_id: str, *under: JsonObject
) -> list[JsonObject]:
    """A picture and what is under it, after a heading (a `Source:` line right after another
    figure's credit would be read as that figure's)."""
    return [
        para(heading, "HEADING_2"),
        *([field(f"Source: {source}.png")] if source else []),
        image(object_id),
        *under,
    ]


def test_a_draft_nobody_has_reviewed(tmp_path: Path) -> None:
    """Every kind of thing a writer is told to fix before publishing, in one document.

    The header is short of lines and unfinished in two fields,
    the pictures are each missing something, the sources are not cited the way they should be,
    and the review is not over.
    """
    seo = "TODO write this " + "x" * SEO_LIMIT
    contributors = (
        "Alon Levy (alon@example.org), Franklin Tang (ft@example.org) Madison Feinberg, "
        "someone@example.org"
    )
    pdf = "https://a.example/a.pdf"
    content = [
        para("The Elephants in the Room", "HEADING_1"),
        # Each picture is missing one thing, or two.
        *figure("No caption", "no-caption", "io.1", field("Credit: MTA")),
        *figure("No credit", "no-credit", "io.2", para("The station box.")),
        *figure("Neither", "bare", "io.3"),
        *figure(
            "Credit not underlined",
            "prose-credit",
            "io.4",
            para("A cross-section."),
            para("Credit: MTA"),
        ),
        *figure("Credit read as the caption", "credit-as-caption", "io.5", para("Credit: MTA")),
        *figure(
            "Phase in the caption",
            "phase",
            "io.6",
            field("Phase: Compositing"),
            field("Credit: MTA"),
        ),
        # No `Source:` line, so each is told apart by its caption or, with none, its alt text.
        *figure(
            "Unnamed", None, "io.7", para("The tunnel from the platform."), field("Credit: MTA")
        ),
        *figure("Unnamed, no caption", None, "io.8", field("Credit: MTA")),
        # Flat enough to be a chart, with no `SVG:` line.
        *figure(
            "Chart credited to ETA",
            "station-lengths",
            "io.9",
            para("Station lengths."),
            field("Credit: ETA"),
        ),
        *figure("Chart with no credit", "station-costs", "io.10", para("Station costs.")),
        para("Fields where there are none", "HEADING_2"),
        field("SEO Description: A 125 St subway should be a slam dunk."),
        field("Sort: A 125 St subway."),
        field("Source: sas-west-036.jpg"),
        para("Prose after a `Source:` line that has no image above it."),
        field("Some prose.\vSource: sas-west-036.jpg"),
        para("Sources", "HEADING_2"),
        rich(
            ("Story", link("https://a.example/story?utm_source=chatgpt.com")),
            ", ",
            ("mail", link("https://a.example/mail?utm_source=x&utm_medium=email&id=7")),
            ", ",
            ("late", link("https://a.example/late?id=7&utm_source=x")),
            ", and ",
            ("another", link("https://b.example/two?utm_campaign=y")),
            ".",
        ),
        rich(
            "Badoe. https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242). ",
            "See (https://a.example/x), and ",
            ("a linked page", link("https://linked.example/")),
            ". At https://a.exam",
            ("ple/y", {"bold": True}),
            ".",
        ),
        rich(
            "See ",
            ("https://a.example/", link("https://a.example/")),
            ("x", {**link("https://a.example/"), "bold": True}),
            " and ",
            ("the ridership figures", link("https://b.example/")),
            ".",
        ),
        rich(
            ("past the end", link(f"{pdf}#page=150")),
            ", ",
            ("the last page", link(f"{pdf}#page=6")),
            ", ",
            ("zero", link(f"{pdf}#page=0")),
            ", and ",
            ("a number", link(f"{pdf}#page=iv&zoom=80")),
            ".",
        ),
    ]
    document = drafted(
        content,
        changes={
            "Discussion Channel": None,
            "Goals": None,
            "Audience": None,
            "Phase": "",
            "SEO Description": seo,
            "Public Contributors": contributors,
        },
        objects=ALTS,
        openSuggestions=3,
        openComments=1,
    )
    site, dest = build(
        tmp_path,
        document,
        images={
            "io.1": picture("no-caption"),
            "io.2": picture("no-credit"),
            "io.3": picture("bare"),
            "io.4": picture("prose-credit"),
            "io.5": picture("credit-as-caption"),
            "io.6": picture("phase"),
            "io.7": picture("unnamed-1"),
            "io.8": picture("unnamed-2"),
            "io.9": picture("station-lengths", 0.97),
            "io.10": picture("station-costs", 0.97),
        },
        archives={pdf: {"snapshot": "s", "timestamp": "t", "pages": 6}},
    )
    assert warned(site) == [
        "a paragraph is broken with `Shift+Enter` rather than `Enter`, so lines that look "
        "separate are one paragraph; give each line its own:\n"
        "- `Some prose.`\n"
        "- `Source: sas-west-036.jpg`",
        "`Source:` line not followed by an image, dropped: `Source: sas-west-036.jpg`",
        "the image `no-caption` has no caption",
        "the image `no-credit` has no `Credit:` line",
        "the image `bare` has no caption",
        "the image `bare` has no `Credit:` line",
        "the image `prose-credit` has a `Credit:` line under it that is not read as "
        "its credit, because `Credit` is not underlined; underline it in the doc",
        "the image `credit-as-caption` has a `Credit:` line under it that is not read "
        "as its credit, because `Credit` is not underlined; underline it in the doc",
        "the image `img-e5f3cc85` has no caption",
        "the image `station-costs` has no `Credit:` line",
        "2 images are unnamed, so each publishes under a hash; give each a `Source:` "
        "line naming its file:\n"
        "- `img-e8909388`: The tunnel from the platform.\n"
        "- `img-e5f3cc85`: A cross-section of the station box",
        "3 suggestions still open on this tab; the build publishes the document "
        "without them, as it reads today",
        "1 comment thread still open on this tab",
        "the `Public Contributors:` line reads `Franklin Tang (ft@example.org) Madison "
        "Feinberg` as one contributor; a comma is missing after the address",
        "the `Public Contributors:` line credits `someone@example.org` by address, as "
        "a person chip Docs couldn't name; type their name before the chip, as `Name "
        "(someone@example.org)`",
        "4 sources still carry the tag it was copied with; take it off the link in the "
        "doc:\n"
        "- `utm_source=chatgpt.com` on "
        "`https://a.example/story?utm_source=chatgpt.com`\n"
        "- `utm_source=x&utm_medium=email` on "
        "`https://a.example/mail?utm_source=x&utm_medium=email&id=7`\n"
        "- `utm_source=x` on `https://a.example/late?id=7&utm_source=x`\n"
        "- `utm_campaign=y` on `https://b.example/two?utm_campaign=y`",
        "3 URLs typed out but not linked; link each in the doc:\n"
        "- `https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242)`\n"
        "- `https://a.example/x`\n"
        "- `https://a.example/y`",
        "1 link shows its URL as its text; give it words in the doc:\n- `https://a.example/x`",
        "`Phase:` is a `Header` field, and this one is outside it: `Phase: Compositing`",
        "`SEO Description:` is a `Header` field, and this one is outside it: `SEO "
        "Description: A 125 St subway should be a slam dunk.`",
        "`Sort:` reads as a field and is not one: `Sort: A 125 St subway.`",
        "`Source:` reads as a field and is not one: `Source: sas-west-036.jpg`",
        "the `Header` section leaves `Phase:` empty",
        "the `Header` section has no `Discussion Channel:` line",
        "the `Header` section has no `Goals:` line",
        "the `Header` section has no `Audience:` line",
        "`SEO Description:` is still marked unfinished",
        "`SEO Description:` is 316 characters, over the 300 a search result shows:\n> "
        "TODO write this " + "x" * 284 + "~~" + "x" * 16 + "~~",
        "the image `station-lengths` is credited to ETA and looks like a chart, but "
        "has no `SVG:` line; link the chart's SVG on one under it, so the SVG "
        "publishes instead of the raster",
        "the image `station-costs` has no credit, so is taken to be ETA's, and looks "
        "like a chart, but has no `SVG:` line; link the chart's SVG on one under it, "
        "so the SVG publishes instead of the raster",
        "3 PDF citations cite a page the PDF does not have:\n"
        "- `https://a.example/a.pdf#page=150` cites page 150 of 6 pages\n"
        "- `https://a.example/a.pdf#page=0` names no page\n"
        "- `https://a.example/a.pdf#page=iv&zoom=80` names no page",
    ]
    # Docs writes the address when it cannot name a person chip; the byline is names.
    assert "alon@example.org" not in (dest / "report.html").read_text()


def test_a_draft_with_one_of_each(tmp_path: Path) -> None:
    """The warnings that count what they found say so in the singular too."""
    pdf = "https://a.example/a.pdf"
    content = [
        *figure(
            "Unnamed", None, "io.1", para("The tunnel from the platform."), field("Credit: MTA")
        ),
        rich(("Story", link("https://a.example/story?utm_source=chatgpt.com")), "."),
        rich("See (https://a.example/x)."),
        rich(("https://a.example/", link("https://a.example/")), "."),
        rich(("past the end", link(f"{pdf}#page=150")), "."),
    ]
    site, _ = build(
        tmp_path,
        drafted(content, objects={"io.1": "A tunnel"}),
        images={"io.1": picture("unnamed")},
        archives={pdf: {"snapshot": "s", "timestamp": "t", "pages": 6}},
    )
    assert warned(site) == [
        "1 image is unnamed, so each publishes under a hash; "
        "give each a `Source:` line naming its file:\n"
        "- `img-1933bef5`: The tunnel from the platform.",
        "1 source still carries the tag it was copied with; take it off the link in the doc:\n"
        "- `utm_source=chatgpt.com` on `https://a.example/story?utm_source=chatgpt.com`",
        "1 URL typed out but not linked; link it in the doc:\n- `https://a.example/x`",
        "1 link shows its URL as its text; give it words in the doc:\n- `https://a.example/`",
        "1 PDF citation cites a page the PDF does not have:\n"
        "- `https://a.example/a.pdf#page=150` cites page 150 of 6 pages",
    ]


def test_a_document_with_no_header_is_left_to_the_parser() -> None:
    """`parse` has already said so; twelve more warnings would bury it."""
    doc = parse(
        {
            "title": "A Draft",
            "body": {"content": [para("A Draft", "TITLE"), para("Some words.")]},
            "footnotes": {},
            "lists": {},
            "inlineObjects": {},
        }
    )
    parsed = [str(w) for w in doc.warnings]
    check(doc)
    assert parsed == [
        "no front matter found; expected a leading `Header` section with `URL:`, "
        "`SEO Description:`, and `Social Title Card:` lines"
    ]
    assert [str(w) for w in doc.warnings] == parsed


def test_a_finished_publication_previewed_with_its_suggestions_accepted(tmp_path: Path) -> None:
    """Text that looks like each mistake, and is not one, and a header that is complete.

    Nothing here is warned about:
    an empty answer where the publication has none to give, an SEO description at its limit,
    a query that is not a tag, a PDF nobody has counted the pages of,
    a colon that is not a field, and each kind of picture a chart check should let go.
    """
    pdf = "https://a.example/a.pdf"
    content = [
        *figure(
            "A figure with both", "tunnel", "io.1", para("What it shows."), field("Credit: MTA")
        ),
        # `img-` is what an unnamed image is called, and a name a `Source:` line may give one too.
        *figure(
            "Named img", "img-of-the-tunnel", "io.2", para("The tunnel."), field("Credit: MTA")
        ),
        *figure(
            "A chart with its SVG",
            "with-svg",
            "io.3",
            rich(("SVG", {"underline": True}), ": ", ("share.svg", link(SVG))),
            para("Station lengths."),
            field("Credit: ETA"),
        ),
        *figure(
            "A chart someone else drew", "theirs", "io.4", para("Fares."), field("Credit: MTA")
        ),
        *figure("A photograph", "photo", "io.5", para("Fares."), field("Credit: ETA")),
        *figure(
            "Just too varied for a chart", "almost", "io.6", para("Fares."), field("Credit: ETA")
        ),
        *figure("Never measured", "unmeasured", "io.7", para("Fares."), field("Credit: ETA")),
        para("Appendix A: Freedom Tunnel", "HEADING_2"),
        para("The answer was simple: build it shallower."),
        para("Phases of the project: three."),
        para('Barbara Russo-Lennon, "Subway spots: the ad blitz."'),
        rich(
            ("a search", link("https://a.example/search?q=slurry&page=2")),
            ", ",
            ("not a tag", link("https://a.example/story?autm_source=x")),
            ", and ",
            ("a PDF", link(f"{pdf}#page=150&zoom=80")),
            ".",
        ),
    ]
    site, dest = build(
        tmp_path,
        drafted(
            content,
            changes={
                "SME/Liaison": "",
                "Private Contributors": "",
                "SEO Description": "x" * SEO_LIMIT,
                "Public Contributors": "Ada Lovelace, Grace Hopper",
            },
            objects={f"io.{n}": f"Alt text {n}" for n in range(1, 8)},
            openSuggestions=3,
        ),
        images={
            "io.1": picture("tunnel"),
            "io.2": picture("img-of-the-tunnel"),
            "io.3": picture("with-svg", 0.97),
            "io.4": picture("theirs", 0.97),
            "io.5": picture("photo", 0.05),
            "io.6": picture("almost", CHART_FLATNESS - 0.01),
            "io.7": picture("unmeasured"),
        },
        suggestions=Suggestions.ACCEPTED,
    )
    assert warned(site) == []
    # Sorted by surname, not as typed.
    page = (dest / "report.html").read_text()
    assert page.index("Grace Hopper") < page.index("Ada Lovelace")
