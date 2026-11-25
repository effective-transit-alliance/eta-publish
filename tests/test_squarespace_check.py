"""An online build warns where what `report.squarespace.html` copies from etany.org has changed.

Each live page here is made from the copies themselves,
written back the way the live page writes them,
so it is the page the copies were taken from, and changed in one place a test.
"""

import json
from pathlib import Path
from typing import override

import pytest
import requests
from paths import FIXTURE, FIXTURE_DIR, HOSTS
from rich.text import Text

from eta_publish import squarespace_check
from eta_publish.build import IMAGES_JSON
from eta_publish.naming import LIVE_SITE, UNPUBLISHED_DIR
from eta_publish.site import Publication
from eta_publish.squarespace import FONTS, SITE_SCRIPT, STYLESHEETS, mark_current
from eta_publish.squarespace_check import SOURCE, Copy, check_copy, differences

YALDEVI = STYLESHEETS[-1]
"""The one stylesheet a live page imports in a `<style>` rather than links."""

SETTINGS = {"tweak-fixed-header": "true", "tweak-fixed-header-style": "Scroll Back"}
"""The two header settings, as `squarespace.js` has them."""

SHELL = (
    "<body><header><div class='header-nav-item'>"
    f"<a href='{LIVE_SITE}/about-us'>About</a></div>"
    "<img src='https://images.squarespace-cdn.com/logo.png'></header>"
    "<main><!-- publication --></main>"
    "<footer><p>Effective Transit Alliance</p></footer></body>"
)
"""A small `squarespace.html`, its links made absolute as the real one's are."""

LIVE_SHELL = (
    "<body id='collection-1' class='collection-type-page'><header>\n"
    '  <div class="header-nav-item">\n'
    '    <a\n      href="/about-us"\n    >About</a>\n'
    "  </div>\n\n"
    '  <img src="//images.squarespace-cdn.com/logo.png">\n'
    "</header><main><div>the report as pasted</div></main>"
    "<footer>\n  <p>Effective Transit Alliance</p>\n</footer>"
)
"""The same, as the live page writes it: relative links, and its own whitespace."""


def live_page(
    *,
    stylesheets: tuple[str, ...] = STYLESHEETS[:-1],
    yaldevi: str = YALDEVI,
    site_script: str = SITE_SCRIPT,
    settings: dict[str, str] | None = None,
    context: bool = True,
    fonts: str = FONTS,
    shell: str = LIVE_SHELL,
) -> str:
    """A live page with what the copies were taken from, each overridden as given."""
    tweaks = SETTINGS if settings is None else settings
    context_json = json.dumps({"betaFeatureFlags": ["x"], "tweakJSON": tweaks})
    head = [
        fonts,
        "<script>Static = window.Static || {};"
        + (f" Static.SQUARESPACE_CONTEXT = {context_json};" if context else "")
        + " Static.SQUARESPACE_CONTEXT_OTHER = 1;</script>",
        *(f'<link rel="stylesheet" type="text/css" href="{href}"/>' for href in stylesheets),
        f"<style>\n@import url('{yaldevi}');\n</style>",
    ]
    script = f'<script defer="true" src="{site_script}" type="text/javascript"></script>'
    body = shell.replace("</footer>", f"</footer>{script}")
    return "\n".join(["<html><head>", *head, "</head>", body, "</html>"])


COPY = Copy(shell=SHELL)


def said(page: str, copy: Copy = COPY) -> list[str]:
    return [warning.plain for warning in differences(page, copy)]


def test_the_page_the_copies_were_taken_from_differs_in_nothing() -> None:
    assert said(live_page()) == []


def test_the_real_copy_matches_itself_as_the_live_page_marks_it() -> None:
    """The real `squarespace.html`, with the current-page marks the live page has for itself."""
    page = live_page(shell=mark_current(Copy().shell, SOURCE))
    assert said(page, Copy()) == []


def test_a_stylesheet_at_a_new_version_names_both() -> None:
    newer = STYLESHEETS[1].replace("/1858/", "/1859/")
    (warning,) = said(live_page(stylesheets=(STYLESHEETS[0], newer, *STYLESHEETS[2:-1])))
    assert newer in warning
    assert STYLESHEETS[1] in warning
    assert "squarespace.py" in warning


def test_a_stylesheet_no_longer_linked_is_named() -> None:
    (warning,) = said(live_page(stylesheets=STYLESHEETS[1:-1]))
    assert f"no longer links {STYLESHEETS[0]}" in warning


def test_a_changed_font_import_is_a_stylesheet_no_longer_linked() -> None:
    (warning,) = said(live_page(yaldevi=YALDEVI.replace("300;500;600", "400")))
    assert f"no longer links {YALDEVI}" in warning


def test_a_new_site_script_names_both() -> None:
    newer = SITE_SCRIPT.replace("4c177f", "000000")
    (warning,) = said(live_page(site_script=newer))
    assert newer in warning
    assert SITE_SCRIPT in warning


def test_no_site_script_at_all_is_said() -> None:
    other = "https://static1.squarespace.com/static/vta/1/scripts/other.js"
    (warning,) = said(live_page(site_script=other))
    assert "links no site script" in warning


def test_a_changed_header_setting_names_it_and_both_values() -> None:
    (warning,) = said(live_page(settings={**SETTINGS, "tweak-fixed-header-style": "Basic"}))
    assert "sets `tweak-fixed-header-style` to `Basic`" in warning
    assert "`Scroll Back`" in warning
    assert "squarespace.js" in warning


def test_a_header_setting_no_longer_set_is_named() -> None:
    (warning,) = said(live_page(settings={"tweak-fixed-header-style": "Scroll Back"}))
    assert "no longer sets `tweak-fixed-header`" in warning


def test_a_page_with_no_settings_says_so() -> None:
    (warning,) = said(live_page(context=False))
    assert "sets no `Static.SQUARESPACE_CONTEXT`" in warning


def test_the_font_rules_in_another_order_are_the_same_fonts() -> None:
    """As two fetches of the live page on the same day have given them."""
    start, _, rest = FONTS.partition("\n")
    body, _, end = rest.rpartition("\n")
    rules = body.split("}\n")
    shuffled = "}\n".join([rules[1], rules[0], *rules[2:]])
    assert shuffled != body
    assert said(live_page(fonts=f"{start}\n{shuffled}\n{end}")) == []


def test_a_changed_font_rule_is_named_both_ways() -> None:
    first = FONTS.index("font-weight: 400;")
    fonts = f"{FONTS[:first]}font-weight: 500;{FONTS[first + len('font-weight: 400;') :]}"
    added, removed = said(live_page(fonts=fonts))
    assert "font-weight: 500;" in added
    assert "squarespace-fonts.html` does not" in added
    assert "no longer has" in removed
    assert "font-weight: 400;" in removed


def test_new_font_ids_are_named() -> None:
    (warning,) = said(live_page(fonts=FONTS.replace('font-ids="', 'font-ids="0', 1)))
    assert "<style data-sqsp-font-ids=" in warning


def test_no_font_block_is_said() -> None:
    (warning,) = said(live_page(fonts=""))
    assert "has no `<style data-sqsp-font-ids>`" in warning


def test_a_changed_link_in_the_header_names_both_tags() -> None:
    (warning,) = said(live_page(shell=LIVE_SHELL.replace("/about-us", "/about")))
    assert "`<header>`" in warning
    assert f'<a href="{LIVE_SITE}/about">' in warning
    assert f'<a href="{LIVE_SITE}/about-us">' in warning
    assert 'after `<div class="header-nav-item">`' in warning


def test_changed_text_in_the_footer_names_both() -> None:
    (warning,) = said(live_page(shell=LIVE_SHELL.replace("Transit Alliance", "Transit Allies")))
    assert "`<footer>`" in warning
    assert "`Effective Transit Allies` where" in warning
    assert "`Effective Transit Alliance`" in warning


def test_the_navigation_marked_differently_from_how_the_build_marks_it_is_said() -> None:
    """The copy is compared with the marks `mark_current` puts back, so a change in how
    Squarespace marks the current page is a difference too."""
    marked = LIVE_SHELL.replace('"header-nav-item"', '"header-nav-item header-nav-item--active"')
    (warning,) = said(live_page(shell=marked))
    assert "header-nav-item--active" in warning


def test_the_rest_of_the_body_is_not_compared() -> None:
    assert said(live_page(shell=LIVE_SHELL.replace("as pasted", "as pasted later"))) == []


def test_many_differences_are_counted_after_the_first_few() -> None:
    copy = Copy(
        shell="<header>" + "".join(f"<p>{i}</p>" for i in range(9)) + "</header><footer></footer>"
    )
    page = live_page(
        shell="<header>"
        + "".join(f"<p>{i}</p><hr>" for i in range(9))
        + "</header><footer></footer>"
    )
    warnings = said(page, copy)
    assert len(warnings) == squarespace_check.SHOWN_DIFFERENCES + 1
    assert "has 4 more differences" in warnings[-1]


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
        response.url = SOURCE
        response.encoding = "utf-8"
        response._content = self.page.encode()
        return response


class Unreachable(requests.Session):
    """A session whose every request fails to connect."""

    @override
    def request(self, *args: object, **kwargs: object) -> requests.Response:
        raise requests.ConnectionError("could not resolve www.etany.org")


def test_the_check_writes_each_difference(capsys: pytest.CaptureFixture[str]) -> None:
    check_copy(Serving(200, live_page(site_script=SITE_SCRIPT.replace("4c177f", "000000"))), COPY)
    err = capsys.readouterr().err
    assert "links the site's script as" in err
    assert "could not read" not in err


def test_a_matching_page_writes_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    check_copy(Serving(200, live_page()), COPY)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "http",
    [Unreachable(), Serving(503, "Service Unavailable")],
    ids=["unreachable", "refused"],
)
def test_a_page_that_cannot_be_read_is_said_and_the_build_goes_on(
    http: requests.Session, capsys: pytest.CaptureFixture[str]
) -> None:
    check_copy(http)
    err = capsys.readouterr().err
    assert f"could not read {SOURCE}" in err
    assert "was not checked" in err


def test_a_page_that_will_not_compare_is_said_and_the_build_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    check_copy(Serving(200, "<script>Static.SQUARESPACE_CONTEXT = {not json</script>"))
    err = capsys.readouterr().err
    assert "could not read" in err
    assert "JSONDecodeError" in err


def test_a_warning_is_text_to_write() -> None:
    (warning,) = differences(live_page(context=False), COPY)
    assert isinstance(warning, Text)


def test_an_offline_build_does_not_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import eta_publish.publish as building
    from eta_publish.publish import Suggestions, publish

    root = tmp_path / "site"
    last = root / UNPUBLISHED_DIR / FIXTURE_DIR.relative_to(FIXTURE)
    last.mkdir(parents=True)
    document = json.loads((FIXTURE_DIR / "doc.json").read_text())
    document.update(documentId="abc", tabId="t.1", suggestions="rejected")
    (last / "doc.json").write_text(json.dumps(document))
    (last / IMAGES_JSON).write_text((FIXTURE_DIR / IMAGES_JSON).read_text())

    def checked() -> None:
        raise AssertionError("an offline build read etany.org")

    monkeypatch.setattr(building, "check_copy", checked)
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
    assert site.built
