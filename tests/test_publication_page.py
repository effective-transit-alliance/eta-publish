"""The publication as a page: `report.html`, which is what the site serves at its directory."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import override

import pytest
from paths import FIXTURE_DIR, HOST, named_images

from eta_publish.build import emit
from eta_publish.check_names import Check
from eta_publish.emit.html import publication_page
from eta_publish.nodes import Document
from eta_publish.parse import parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


class Sources(HTMLParser):
    """Every `src` on the page, read by a parser rather than matched for.

    The output is formatted, so a tag long enough to wrap is spread over
    several lines and there is no one line holding `<img src="...">`.
    What the page says is a question for something that reads HTML.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            self.found += [v for k, v in attrs if k == "src" and v is not None]


def sources(markup: str) -> list[str]:
    parser = Sources()
    parser.feed(markup)
    parser.close()
    return parser.found


@pytest.fixture
def doc() -> Document:
    parsed = named_images(parse(FIXTURE))
    parsed.image_files["io.1"] = "sas-west-036.png"
    return parsed


def test_page_images_resolve_next_to_the_page(doc: Document, tmp_path: Path) -> None:
    """Everything a build writes references its images the same way:
    by the path they sit at, right beside the page."""
    images = tmp_path / "images"
    images.mkdir()
    (images / "sas-west-036.png").write_bytes(b"not really a png")

    emit(doc, tmp_path, site_url=HOST)
    page = (tmp_path / "report.html").read_text()

    # Not the logo in the header bar, which is the build's own asset,
    # linked from the shared `assets/` where the stylesheets are.
    found = [src for src in sources(page) if not src.endswith("/logo.svg")]
    assert found
    for src in found:
        assert not src.startswith("http")
        assert (tmp_path / src).exists(), f"{src} does not resolve next to report.html"

    # A build writes the images it references, so the fragment names them where
    # they were written. Serving them from elsewhere is the emitter's `image_base`,
    # which is not something a build decides.
    fragment = (tmp_path / "report.partial.html").read_text()
    assert sources(fragment)[0] == "images/sas-west-036.png"


def test_warnings_are_shown_where_someone_will_see_them() -> None:
    doc = named_images(parse(FIXTURE))
    doc.warn(Check.UNHANDLED_ELEMENT, "something looked wrong")
    assert "something looked wrong" in publication_page(doc, site_url=HOST)


def test_no_warnings_means_no_warning_box(doc: Document) -> None:
    # The fixture's header carries one unrecognized field on purpose;
    # what is under test is the box, not the warning.
    doc.warnings.clear()
    assert 'class="warnings"' not in publication_page(doc, site_url=HOST)


def test_markdown_images_resolve_next_to_the_archive(doc: Document, tmp_path: Path) -> None:
    """The archive is read from the repository, where the files sit beside it,
    not from whatever host serves the published site."""
    images = tmp_path / "images"
    images.mkdir()
    (images / "sas-west-036.png").write_bytes(b"not really a png")

    emit(doc, tmp_path, site_url=HOST)
    archive = (tmp_path / "report.md").read_text()

    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", archive)
    assert links
    for link in links:
        assert not link.startswith("http")
        assert (tmp_path / link).exists(), f"{link} does not resolve next to report.md"
