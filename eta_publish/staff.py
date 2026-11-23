"""Who is on ETA's staff, read off the page that introduces them.

A byline links each contributor on staff to their entry on `ABOUT_US`,
so whether a name links is a question about that page, and the page is what answers it.
Read once a build, by `look_up`, and saved as `STAFF_JSON` beside the publications,
so an offline build links exactly the names the last build that read the page found.
"""

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import override

import requests

from . import console
from .naming import ABOUT_US
from .nodes import Shown

STAFF_JSON = "staff.json"
"""The names `ABOUT_US` lists, in its order, as the last build that read it found them.

At the top of `site/unpublished/`, beside the publications' own `doc.json` and `archives.json`:
like them, it is what a build read from outside, kept so the next build without the network
writes the same pages, and read from the last build and written into the new one.
One file for the whole site rather than one a publication, since it is one page for all of them.
"""

LIST_SECTION = "user-items-list-section"
"""The class of the section the page lists its staff in, one `<h2>` a name.

Squarespace's, for a list of items, and the only one on the page.
"""


class _Names(HTMLParser):
    """The text of each `<h2>` inside a `LIST_SECTION`, in order.

    Only `<section>` is counted to know when the list ends,
    since sections are always closed and an `<img>` or `<br>` never is.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.names: list[str] = []
        self._depth = 0
        """How many sections are open from the list's own inward, zero outside it."""
        self._heading: list[str] | None = None

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "section":
            classes = (dict(attrs).get("class") or "").split()
            if self._depth or LIST_SECTION in classes:
                self._depth += 1
        elif tag == "h2" and self._depth:
            self._heading = []

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self._depth:
            self._depth -= 1
        elif tag == "h2" and self._heading is not None:
            # As a byline writes a name: the page's markup breaks lines inside the tag.
            name = " ".join("".join(self._heading).split())
            if name and name not in self.names:
                self.names.append(name)
            self._heading = None

    @override
    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading.append(data)


def staff_names(page: str) -> tuple[str, ...]:
    """The names the staff page `page` lists, exactly as it writes them, in its order."""
    parser = _Names()
    parser.feed(page)
    parser.close()
    return tuple(parser.names)


def read_staff(directory: Path) -> tuple[str, ...]:
    """The names saved in `directory`'s `STAFF_JSON`, or none if there is no such file."""
    saved = directory / STAFF_JSON
    if not saved.exists():
        return ()
    return tuple(json.loads(saved.read_text()))


def write_staff(directory: Path, names: tuple[str, ...]) -> None:
    """Save `names` as `directory`'s `STAFF_JSON`, for the next build to read."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / STAFF_JSON).write_text(json.dumps(list(names), indent=2) + "\n")


def look_up(saved: tuple[str, ...], http: requests.Session | None = None) -> tuple[str, ...]:
    """The names `ABOUT_US` lists now, or `saved` with a warning if it cannot say.

    Never a failure: a page that would not load, or whose markup no longer holds a list,
    says nothing about who is on staff, and the names the last build read are the best answer.
    The same as a source the archive could not be asked about, which keeps what it had.
    """
    try:
        response = (http or requests.Session()).get(ABOUT_US, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        _kept(saved, str(e) or type(e).__name__)
        return saved
    names = staff_names(response.text)
    if not names:
        _kept(saved, "it heads no entry with a name where the staff are listed")
        return saved
    return names


def _kept(saved: tuple[str, ...], why: str) -> None:
    console.write(
        console.warning(
            "could not read the staff from {} ({}); "
            "contributors are linked to it by the {} names the last build saved in {}",
            console.Linked(ABOUT_US),
            why,
            str(len(saved)),
            Shown(STAFF_JSON),
        )
    )
