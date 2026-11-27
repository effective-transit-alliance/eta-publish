"""Who a byline links to the staff page is what that page lists, read once a build.

`tests/fixture/about-us.html` is `https://www.etany.org/about-us` as it was on 2026-11-23,
cut down to the section that lists the staff, without its pictures and styles.
"""

import json
from pathlib import Path
from typing import override

import pytest
import requests
from paths import FIXTURE, FIXTURE_DIR, HOSTS

from eta_publish import staff
from eta_publish.build import IMAGES_JSON
from eta_publish.naming import UNPUBLISHED_DIR
from eta_publish.site import Publication
from eta_publish.staff import look_up, read_staff, staff_names, write_staff

PAGE = (FIXTURE / "about-us.html").read_text()

SEVEN = (
    "Blair Lorenzo",
    "Yangbo Du",
    "Madison Feinberg",
    "Robert Hale",
    "Alon Levy",
    "William Meehan",
    "Khyber Sen",
)

SAVED = ("Blair Lorenzo", "Khyber Sen")


class Serving(requests.Session):
    """A session that answers every request with one status and page."""

    def __init__(self, status: int, page: str) -> None:
        super().__init__()
        self.status = status
        self.page = page

    @override
    def request(self, *args: object, **kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = self.status
        response.url = staff.ABOUT_US
        response.encoding = "utf-8"
        response._content = self.page.encode()
        return response


class Unreachable(requests.Session):
    """A session whose every request fails to connect."""

    @override
    def request(self, *args: object, **kwargs: object) -> requests.Response:
        raise requests.ConnectionError("could not resolve www.etany.org")


def test_a_heading_outside_the_staff_list_is_not_a_name() -> None:
    page = (
        "<h2>About Us</h2>"
        "<section class='page-section user-items-list-section'>"
        "<section><h2>\n  Ada\n  Lovelace\n</h2></section><br><img src=x>"
        "<h2>Khyber Sen</h2>"
        "</section>"
        "<section class='page-section'><h2>Get Involved</h2></section>"
    )
    assert staff_names(page) == ("Ada Lovelace", "Khyber Sen")


def test_the_page_read_is_what_the_build_links(capsys: pytest.CaptureFixture[str]) -> None:
    assert look_up(SAVED, Serving(200, PAGE)) == SEVEN
    assert staff_names(PAGE) == SEVEN
    assert "could not read the staff" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "http",
    [Unreachable(), Serving(503, "Service Unavailable")],
    ids=["unreachable", "refused"],
)
def test_a_page_that_cannot_be_read_keeps_the_saved_names(
    http: requests.Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert look_up(SAVED, http) == SAVED
    assert "could not read the staff" in capsys.readouterr().err


def test_a_page_listing_no_names_keeps_the_saved_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Markup that changed under the parser says nothing about who left."""
    assert look_up(SAVED, Serving(200, "<html><body><h2>About Us</h2></body></html>")) == SAVED
    assert "could not read the staff" in capsys.readouterr().err


def test_with_nothing_saved_there_are_no_names(tmp_path: Path) -> None:
    assert read_staff(tmp_path) == ()


def test_an_offline_build_links_the_saved_names_and_reads_no_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And saves them again, so the next build has them too."""
    import eta_publish.publish as building
    from eta_publish.publish import Suggestions, publish

    root = tmp_path / "site"
    out = root / UNPUBLISHED_DIR
    last = out / FIXTURE_DIR.relative_to(FIXTURE)
    last.mkdir(parents=True)
    document = json.loads((FIXTURE_DIR / "doc.json").read_text())
    document.update(documentId="abc", tabId="t.1", suggestions="rejected")
    (last / "doc.json").write_text(json.dumps(document))
    (last / IMAGES_JSON).write_text((FIXTURE_DIR / IMAGES_JSON).read_text())
    write_staff(out, SAVED)

    def read(saved: tuple[str, ...]) -> tuple[str, ...]:
        raise AssertionError("an offline build read the staff page")

    monkeypatch.setattr(building, "look_up", read)
    site = publish(
        [Publication(url="https://docs.google.com/document/d/abc/edit?tab=t.1")],
        root,
        Suggestions.REJECTED,
        False,
        False,
        False,
        offline=True,
        archive=False,
        hosts=HOSTS,
    )

    assert site.built[0].doc.staff == SAVED
    assert read_staff(out) == SAVED
