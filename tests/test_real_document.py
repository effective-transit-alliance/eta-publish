"""Snapshot of the real SAS West report, end to end.

`site/` is literally a publish of the real report,
at the top level because it is the site this project publishes
rather than a test fixture:

    uv run eta-publish all

The report lands under the path its own front matter names,
`reports/digging-out-deep-hole-sas-west/`, next to the index listing it.
That directory holds `doc.json`, the four outputs, `images/`, and `report.pdf`,
and this test asserts the committed outputs
still match what the code produces from the committed response.

`tests/fixture/` is the same directory in miniature,
built from a document nobody fetched, and the two differ by that and nothing else.
Either rebuilds from its own `doc.json` by passing the report directory back.
This is the only test running against a document nobody wrote to make a point,
and every bug that mattered so far
came from this document's shape rather than from a hand-built fixture.

Only the text is committed.
The images are 18 MB and the PDF 19 MB,
and a re-fetch rewrites every image, adding another copy to history permanently.
They are ignored, so the command above is safe to rerun.

`images.json` is the one derived thing kept:
a Docs `inlineObject` carries a `contentUri` with no extension and no mime type,
so the only way to learn an image is a JPEG is to fetch it,
and this test does not use the network.
It records the filename written for each image,
refreshed from `images/` whenever that directory is present.

When a snapshot changes, read the diff:
it is exactly what the change does to a real published report.
Accept it with `pytest --regenerate-snapshots`.
"""

import copy
import json
import re
import tempfile
from pathlib import Path

import pytest
from paths import REAL_DIR as REAL

from eta_publish import format
from eta_publish.archive import read_archive_index
from eta_publish.checks import check as run_checks
from eta_publish.docs_json import JsonObject
from eta_publish.emit.html import HtmlEmitter, report_page
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.emit.typst import TypstEmitter
from eta_publish.naming import IMAGE_DIR
from eta_publish.nodes import Document, Figure, Heading
from eta_publish.parse import parse
from eta_publish.style import style

ASSET_BASE = "../../assets"
"""What a build links from a report at `reports/<slug>/`."""

FILENAMES_PATH = REAL / "images.json"
DOWNLOADED = REAL / "images"
DOC_JSON = json.loads((REAL / "doc.json").read_text())

# The snapshots are a plain publish, so no `--image-base`:
# where images are hosted is still undecided,
# and pinning a placeholder in would make every snapshot line depend on it.
# That the flag is applied when given is covered in `test_preview.py`.


def image_index(regenerate: bool) -> dict[str, JsonObject]:
    """What a real run wrote for each image, read from `images.json`.

    Written by a build rather than by this test:
    a record of what was published rather than of what was asserted.
    The filename and the pixel size are facts only a fetch can learn,
    and the committed page is laid out from the size,
    so a test with no network reads them from here.
    The hash beside them lets CI check that a rebuild fetched the same pictures.
    """
    return json.loads(FILENAMES_PATH.read_text())


def image_files(regenerate: bool) -> dict[str, str]:
    return {object_id: entry["file"] for object_id, entry in image_index(regenerate).items()}


def image_shapes(regenerate: bool) -> dict[str, tuple[int, int]]:
    return {
        object_id: (entry["width"], entry["height"])
        for object_id, entry in image_index(regenerate).items()
        if "width" in entry
    }


@pytest.fixture(scope="module")
def built(regenerate_snapshots: bool) -> Document:
    parsed = parse(DOC_JSON)
    parsed.image_files.update(image_files(regenerate_snapshots))
    parsed.image_shapes.update(image_shapes(regenerate_snapshots))
    # Where each source is archived, from the record a build left here, for the
    # same reason as the image index: it is a fact only the network can learn,
    # and these snapshots are the files a build writes. Without it, regenerating
    # them overwrote the built report with one saying `not archived` 109 times.
    read_archive_index(REAL, parsed)
    # As a build does it, because the page carries the warnings
    # and these snapshots are the pages a build writes.
    # `run_checks` rather than `check`, which is this module's snapshot comparison.
    run_checks(parsed)
    style(parsed)
    return parsed


@pytest.fixture
def doc(built: Document) -> Document:
    """A copy of the one build, so that no test sees what another did to it.

    Building it is most of what these tests cost, about a seventh of a second
    each, and copying it takes a fiftieth of that.
    """
    return copy.deepcopy(built)


def check(name: str, actual: str, regenerate: bool) -> None:
    path = REAL / name
    if regenerate or not path.exists():
        path.write_text(actual)
        if not regenerate:
            pytest.fail(f"{path} did not exist; wrote it, review and commit")
        return
    expected = path.read_text()
    assert actual == expected, (
        f"{path} differs. This is a real published report, so read the diff "
        "before accepting it, then rerun with --regenerate-snapshots."
    )


# ---- snapshots ------------------------------------------------------


def formatted(name: str, source: str) -> str:
    """`source` as a build would leave it on disk.

    Through `format.tree`, the same call the build makes, rather than a
    second way of formatting kept alive for the tests: the committed page is
    the page a build writes, formatter included, and two paths that had to
    agree would be free to stop agreeing without a test noticing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / name
        page.write_text(source, encoding="utf-8")
        format.tree(Path(tmp))
        return page.read_text(encoding="utf-8")


def test_html_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    check(
        "report.html",
        formatted("report.html", HtmlEmitter(image_base=IMAGE_DIR).emit(doc)),
        regenerate_snapshots,
    )


def test_markdown_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    check("report.md", MarkdownEmitter().emit(doc), regenerate_snapshots)


def test_typst_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    check("report.typ", TypstEmitter().emit(doc), regenerate_snapshots)


def test_page_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    check(
        "index.html",
        formatted("index.html", report_page(doc, asset_base=ASSET_BASE)),
        regenerate_snapshots,
    )


# ---- what the document should parse to ------------------------------


def test_the_shape_of_the_report(doc: Document) -> None:
    assert doc.title == "Digging Out of a Very Deep Hole: Saving Billions on 125th Street"
    assert doc.slug == "/reports/digging-out-deep-hole-sas-west"
    assert len(doc.footnotes) == 20
    assert len(doc.images) == 29, "28 figures and the share card"
    assert len([b for b in doc.blocks if isinstance(b, Figure)]) == 28
    assert len([b for b in doc.blocks if isinstance(b, Heading)]) == 21


def test_smart_chips_resolve(doc: Document) -> None:
    """Person and date chips are not text runs.
    Reading only text runs left every one of these empty,
    including the publication date."""
    assert doc.meta["Project Manager"] == "Khyber Sen"
    assert doc.meta["Publish Due Date"] == "Aug 19, 2026"
    # The field has been renamed once, silently, and the date simply stopped
    # appearing. This is the assertion that would have said so.
    assert doc.dateline == "August 19, 2026"
    assert doc.meta["Public Contributors"].startswith("Khyber Sen, Darius Jankauskas")
    assert doc.meta["SEO Description"].startswith("A 125 St subway should be a slam dunk")


KNOWN_WARNINGS = (
    # Written before the header asked for them.
    "the `Header` section has no `SME/Liaison:` line",
    "the `Header` section has no `Goals:` line",
    "the `Header` section has no `Audience:` line",
    "as a `Source:` line above the image instead",
    "unnamed, so each publishes under a hash",
    "suggestions still open on this tab",
    "suggestion still open on this tab",
    "comment threads still open on this tab",
    "comment thread still open on this tab",
    "the tag it was copied with",
    "a search result shows",
    "has no `Credit:` line",
    "unfinished text in the document",
    "rather than `Enter`",
    "standing in for blank space",
    "has an unrecognized",
    "runs past it into the value",
    "URL as its text",
    # Every house-style warning, as one kind. They say what to write and not
    # why, so the words in one are the document's rather than the check's,
    # and there is nothing else in them to match on.
    "style: ",
)
"""Every kind of warning this report has been known to raise.

Kinds rather than the warnings themselves, and a subset rather than an equality:
what varies here is the document, and fixing the document is the point of a
warning. Asserted as a list, this test failed twice in one afternoon for reasons
that were not about the code: once when a new check started firing, and once
when the tag it complained about was taken off the doc, which is the warning
having worked.

What is still worth catching is a kind nobody has seen, because that is either
a check that started firing on this report or one that changed its wording.
The exact text of every warning the report publishes is pinned byte for byte
anyway, in the committed `report.md` and `index.html`: they are published on the
page, so the output snapshot is already the assertion that they have not moved.

Counts, image names and lengths are left loose on purpose. A seventeenth image
gaining a `Source:` line is not a thing this test should have an opinion about.
The phrase each one carries is enough to tell it from the others, so these are
substrings rather than patterns: there is nothing here to match loosely, and a
pattern over `\d+` and `(?:is|are)` would only be a way to get the plural wrong.
"""


def test_no_warning_is_of_a_kind_we_have_not_seen(doc: Document) -> None:
    """Each of these is something to fix in the document, not in the code."""
    unknown = [
        first
        for first in (str(w).split("\n")[0] for w in doc.warnings)
        if not any(known in first for known in KNOWN_WARNINGS)
    ]
    assert unknown == [], f"new kind of warning on this report: {unknown}"


def test_every_unnamed_image_is_listed_with_what_it_shows(doc: Document) -> None:
    """A hash names nothing, so the work of fixing these
    is working out which picture `img-6fb0f9c4` is."""
    warning = next(w for w in map(str, doc.warnings) if "unnamed" in w)
    listed = [line for line in warning.split("\n") if line.startswith("- ")]
    unnamed = [b for b in doc.blocks if isinstance(b, Figure) and not b.image.named]
    assert len(listed) == len(unnamed) == 9
    assert listed[0].startswith("- `img-6fb0f9c4`: Composite image of the MTA")
    # Every one says which picture it is, from its caption or its alt text.
    assert all(": " in line for line in listed)


def test_the_seo_warning_quotes_the_description(doc: Document) -> None:
    warning = next(w for w in map(str, doc.warnings) if "SEO Description" in w)
    quoted = warning.split("\n")[1]
    assert quoted.startswith("> A 125 St subway should be a slam dunk")
    assert quoted.endswith("~~")


# ---- properties that must hold for any published report -------------


def test_no_editorial_note_reaches_a_published_output(doc: Document) -> None:
    """`Source:`, `Uncropped Source:`, `Image Source`, and `SVG:`
    name assets for whoever assembles the page.
    Each appears zero times on the live report, against 26 occurrences of `Credit:`.

    The report, not the warnings: a warning quotes the line it is about,
    so `unfinished text in the document: SVG: TODO` says `SVG:` on purpose.
    Both outputs are read with their warnings taken out.
    """
    typst = TypstEmitter().emit(doc)
    # Everything after the `#show: report.with(...)` call, which is the report itself.
    typst_body = re.split(r"^\)$", typst, maxsplit=1, flags=re.MULTILINE)[-1]
    html_body = re.sub(
        r'<div class="warnings">.*?</div>', "", HtmlEmitter().emit(doc), flags=re.DOTALL
    )
    for emitted in (html_body, typst_body):
        for note in ("Source:", "Image Source", "SVG:", "drive.google.com"):
            assert note not in emitted, note
        assert "Credit: MTA" in emitted


def test_the_archive_keeps_the_editorial_notes(doc: Document) -> None:
    archive = MarkdownEmitter().emit(doc)
    assert "<!-- Source:" in archive
    assert "drive.google.com" in archive


def test_html_ids_are_unique_and_every_link_resolves(doc: Document) -> None:
    """The three defects on the live page, none of which can recur here."""
    html = HtmlEmitter().emit(doc)

    ids = re.findall(r'id="([^"]+)"', html)
    assert len(ids) == len(set(ids))

    refs = set(re.findall(r'id="fnref(\d+)"', html))
    notes = set(re.findall(r'id="fn(\d+)"', html))
    backlinks = set(re.findall(r'href="#fnref(\d+)"', html))
    assert refs == notes == backlinks
    assert len(refs) == 20

    targets = set(ids)
    for target in re.findall(r'href="#([^"]+)"', html):
        assert target in targets, target


def test_the_fragment_fits_in_one_code_block(doc: Document) -> None:
    """Squarespace allows 400 KB.
    This is the number the one-paste claim rests on,
    so it is asserted rather than estimated."""
    from eta_publish.emit.html import CODE_BLOCK_LIMIT

    size = len(HtmlEmitter(image_base="https://assets.etany.org/sas-west").emit(doc).encode())
    assert size < CODE_BLOCK_LIMIT
    # Moved from 130,000 when the Sources section landed: 113 entries and a
    # `[n]` on every link is what it costs to make an archived copy reachable
    # without hovering. Laid out, the committed fragment is around 225 KB,
    # which is inside the limit and closing on `CODE_BLOCK_WARN`.
    #
    # And from 200,000 when three more sources turned out to have a capture:
    # 200,438 bytes, which is what looking cost. An archived link is about 150
    # bytes, so the next few captures move this again, and the thing worth
    # noticing here is a jump, not a source.
    #
    # And from 205,000 when the warnings started highlighting the part of a
    # value they are about: `<mark>` around a run of middle dots, 66 bytes a
    # warning and only on the ones that point at characters.
    #
    # And from 210,000 when embedded videos and posts landed: about 3 KB of
    # stylesheet and script that every fragment carries, embeds or none.
    #
    # And from 215,000 when Sources lined up in columns: a `span` around each
    # entry's arrows and another around its archive, about 80 bytes an entry.
    #
    # And from 225,000 when `Image Source` began asking to be `Source:`:
    # twelve warnings, each carrying its URL, about 1.4 KB that goes away
    # again as the document is converted.
    assert size < 230_000, f"grown to {size:,} bytes; still fits, worth a look"


def test_every_image_has_something_describing_it(doc: Document) -> None:
    """Every figure in the report carries alt text or a caption.

    The one image that had neither is the share card,
    which is not a figure and is not in the body at all."""
    undescribed = [
        b.image.object_id
        for b in doc.blocks
        if isinstance(b, Figure) and not b.image.alt and not b.caption
    ]
    assert undescribed == []


def test_the_share_card_is_not_in_the_report(doc: Document) -> None:
    """It is a picture of the title, for whatever unfurls a link to it."""
    assert doc.card is not None
    assert doc.card.object_id == "kix.6v8dr3hm2747"
    assert doc.card.object_id not in [
        b.image.object_id for b in doc.blocks if isinstance(b, Figure)
    ]
    assert doc.card in doc.images, "still has to be downloaded to be linked"


def test_the_report_opens_with_its_hero(doc: Document) -> None:
    """Above the table of contents, which it introduces rather than follows."""
    page = report_page(doc)
    assert page.index("img-6fb0f9c4") < page.index('<nav class="toc"')
    assert page.index('property="og:image"') < page.index('<h1 id="title">')


def test_no_chip_email_reaches_any_output(doc: Document) -> None:
    """A person chip carries an email beside the name.
    The name is what the document displays and what belongs in a report;
    the address is contact information the document happens to hold,
    and publishing it would put a contributor's address on a public page.

    The fixture keeps the real addresses so this tests something.
    """
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", json.dumps(DOC_JSON))
    assert emails, "the fixture should still contain a chip to test against"
    for emitted in (
        HtmlEmitter().emit(doc),
        MarkdownEmitter().emit(doc),
        TypstEmitter().emit(doc),
        report_page(doc),
    ):
        for email in emails:
            assert email not in emitted, email


def test_the_chart_publishes_as_a_vector(doc: Document) -> None:
    """Docs cannot place an SVG,
    so `project_cost_comparison.svg` is pasted into the report as a raster
    and linked beside it.
    All three outputs can show the vector, so all three should."""
    vectors = [i for i in doc.images if i.vector is not None]
    assert [v.vector.title for v in vectors if v.vector] == ["project_cost_comparison.svg"]

    for emitted in (HtmlEmitter().emit(doc), MarkdownEmitter().emit(doc), TypstEmitter().emit(doc)):
        assert vectors[0].vector is not None
        assert vectors[0].vector.filename in emitted
