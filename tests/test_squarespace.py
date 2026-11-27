"""A publication as etany.org shows it: `report.squarespace.html`."""

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import override

import pytest
from paths import FIXTURE_DIR, HOST, named_images

from eta_publish.build import emit
from eta_publish.naming import LIVE_SITE
from eta_publish.nodes import Document
from eta_publish.parse import parse
from eta_publish.squarespace import (
    FONTS,
    ITEM_CLASSES,
    PUBLICATION,
    SCRIPT_SETUP,
    SHELL,
    SITE_SCRIPT,
    STYLESHEETS,
    mark_current,
    squarespace_page,
)

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())

FRAGMENT = '<div class="eta-report"><p id="lede">The publication.</p></div>'

IBX = f"{LIVE_SITE}/reports/ibx-automation"
"""A report the navigation lists, in its Reports folder."""

STATEMENT = f"{LIVE_SITE}/statements/deinterlining"
"""A statement: a post in the blog the navigation links as Statements."""


class Elements(HTMLParser):
    """Every element, with its attributes and the elements it is inside, read by a parser."""

    VOID = frozenset({"br", "img", "input", "link", "meta", "source", "track", "hr", "wbr"})

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, dict[str, str | None], list[tuple[str, dict[str, str | None]]]]]
        self.found = []
        self.open: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)
        self.close()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = (tag, dict(attrs))
        self.found.append((tag, dict(attrs), list(self.open)))
        if tag not in self.VOID:
            self.open.append(element)

    @override
    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i][0] == tag:
                del self.open[i:]
                break


def classes(attrs: dict[str, str | None]) -> list[str]:
    value = attrs.get("class")
    return [] if value is None else value.split()


def current(html: str) -> list[tuple[str | None, str | None]]:
    """What the navigation in `html` marks as where the reader is:
    each link's `href` or folder, and what its `aria-current` says."""
    return [
        (attrs.get("href") or attrs.get("data-href"), attrs.get("aria-current"))
        for _, attrs, _ in Elements(html).found
        if attrs.get("aria-current") is not None
    ]


def active(html: str) -> list[str]:
    """Each navigation entry in `html` marked as the current one, by its class."""
    marked = {f"{kind}--active" for kind in ITEM_CLASSES}
    return [c for _, attrs, _ in Elements(html).found for c in classes(attrs) if c in marked]


def test_the_shell_has_one_place_for_the_publication_and_marks_no_page() -> None:
    """Which page is current is each publication's, so the copied page says none."""
    assert SHELL.count(PUBLICATION) == 1
    assert current(SHELL) == []
    assert active(SHELL) == []


def test_the_shell_names_no_page_relative_to_squarespace() -> None:
    """Served from somewhere other than etany.org, a root-relative link is a link to nothing."""
    for _, attrs, _ in Elements(SHELL).found:
        for name in ("href", "src"):
            value = attrs.get(name)
            assert value is None or not value.startswith("/"), value


def test_the_publication_is_where_the_embed_block_puts_it() -> None:
    """Inside the Embed block, in a Fluid Engine section of the page's `main`,
    between Squarespace's header and its footer."""
    found = Elements(squarespace_page(FRAGMENT, "Title", IBX)).found
    (report,) = [inside for tag, attrs, inside in found if "eta-report" in classes(attrs)]
    around = [(tag, attrs.get("id"), classes(attrs)) for tag, attrs in report]
    assert ("main", "page", ["container"]) in around
    names = [c for _, _, cs in around for c in cs]
    for expected in ("page-section", "fluid-engine", "fe-block", "embed-block"):
        assert expected in names
    assert "embed-block-wrapper" in around[-1][2]
    order = [attrs.get("id") for _, attrs, _ in found if attrs.get("id")]
    assert order.index("header") < order.index("lede") < order.index("footer-sections")


def test_the_page_carries_the_live_sites_head() -> None:
    """The live site's stylesheets, and the script its header runs on,
    which hides the header on the way down and opens the phone's menu,
    after what it reads from a page is set: the script once, deferred, and the setup before it.
    The fonts a live page declares inline come before the stylesheets."""
    page = squarespace_page(FRAGMENT, "Title", IBX)
    found = Elements(page).found
    linked = [
        attrs.get("href")
        for tag, attrs, _ in found
        if tag == "link" and attrs.get("rel") == "stylesheet"
    ]
    assert linked == list(STYLESHEETS)
    scripts = [attrs for tag, attrs, _ in found if tag == "script"]
    site_scripts = [attrs for attrs in scripts if attrs.get("src") == SITE_SCRIPT]
    assert site_scripts == [{"defer": None, "src": SITE_SCRIPT}]
    assert page.count(SCRIPT_SETUP.strip()) == 1
    assert page.index(SCRIPT_SETUP.strip()) < page.index(SITE_SCRIPT)
    for setting in ('"tweak-fixed-header": "true"', '"tweak-fixed-header-style": "Scroll Back"'):
        assert setting in SCRIPT_SETUP
    assert FONTS.startswith("<style data-sqsp-font-ids=")
    assert page.count(FONTS) == 1
    assert page.index(FONTS) < page.index(STYLESHEETS[0])


def test_the_title_is_as_squarespace_gives_it() -> None:
    page = squarespace_page(FRAGMENT, "Deinterlining", STATEMENT)
    assert "<title>Deinterlining &mdash; Effective Transit Alliance New York</title>" in page


def test_a_report_in_a_folder_marks_it_and_its_folder() -> None:
    """As the live page does: the report's own entry, and the Reports folder holding it,
    in each copy of the header's navigation and in the phone's menu."""
    marked = mark_current(SHELL, IBX)
    assert sorted(current(marked)) == sorted(
        [(IBX, "page")] * 3 + [("/reports", "true")] * 2 + [(f"{LIVE_SITE}/reports", "true")]
    )
    assert sorted(active(marked)) == sorted(
        ["header-nav-item--active"] * 2
        + ["header-nav-folder-item--active"] * 2
        + ["header-menu-nav-item--active"] * 2
    )


def test_a_statement_marks_the_blog_it_is_a_post_in() -> None:
    marked = mark_current(SHELL, STATEMENT)
    assert current(marked) == [(f"{LIVE_SITE}/statements", "page")] * 3
    assert sorted(active(marked)) == sorted(
        ["header-nav-item--active"] * 2 + ["header-menu-nav-item--active"]
    )


def test_a_page_the_navigation_does_not_list_marks_nothing() -> None:
    """A draft is not in the navigation yet, and where it will be is not ours to guess."""
    marked = mark_current(SHELL, f"{LIVE_SITE}/reports/not-out-yet")
    assert current(marked) == []
    assert active(marked) == []


@pytest.fixture
def doc() -> Document:
    parsed = named_images(parse(FIXTURE))
    parsed.image_files["io.1"] = "sas-west-036.png"
    return parsed


def test_a_build_writes_the_fragment_as_pasted_without_its_warnings(
    doc: Document, tmp_path: Path
) -> None:
    """The warnings are for whoever reviews a build, on `report.html`;
    the page as etany.org shows it has what is pasted there, which has none."""
    doc.warn("something looked wrong")
    emit(doc, tmp_path, site_url=HOST)
    page = (tmp_path / "report.squarespace.html").read_text()
    assert "something looked wrong" in (tmp_path / "report.html").read_text()
    assert "something looked wrong" not in page
    assert 'class="warnings"' not in page


def test_only_the_preview_gets_one(doc: Document, tmp_path: Path) -> None:
    """Nothing live links it, so `site/published/` has no copy to take."""
    emit(doc, tmp_path, stem="report.published", site_url=HOST)
    assert not list(tmp_path.glob("*squarespace*"))
