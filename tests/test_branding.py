"""The ETA logo in the top right corner of a chart credited to ETA, or above it.

The charts here draw no text, so what they say does not depend on the fonts installed,
and the check that fonts are installed is taken as passed.
"""

import re

import pytest

from eta_publish import branding
from eta_publish.branding import (
    GAP_SHARE,
    LOGO_SHARE,
    MARGIN_SHARE,
    SITE_CLASS,
    SITE_COLOR,
    SITE_DARK_COLOR,
    SITE_SHARE,
    credited_to_eta,
    with_logo,
)
from eta_publish.nodes import Crop, Document, Figure, Image, Text


@pytest.fixture(autouse=True)
def _fonts_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(branding, "_fonts_draw", lambda: True)


WIDTH = 400
HEIGHT = 200
SIDE = WIDTH * LOGO_SHARE
MARGIN = SIDE * MARGIN_SHARE
MARK = SIDE * (1 + GAP_SHARE + SITE_SHARE)
"""The logo and `etany.org` under it."""


def chart(*shapes: str, background: str = '<rect width="400" height="200" fill="#fff"/>') -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">'
        f"{background}{''.join(shapes)}</svg>"
    ).encode()


BAR = '<rect x="20" y="120" width="100" height="60" fill="#2a76d6"/>'
"""Well away from the corner."""

CORNER = '<rect x="300" y="10" width="90" height="40" fill="#2a76d6"/>'
"""Right where the logo would go."""


def view(svg: bytes) -> list[float]:
    found = re.search(rb'viewBox="([^"]*)"', svg)
    assert found is not None
    return [float(n) for n in found.group(1).split()]


def logo_at(svg: bytes) -> tuple[float, float]:
    found = re.search(rb'<svg x="([^"]*)" y="([^"]*)" width="[^"]*" height="[^"]*"', svg)
    assert found is not None
    return float(found.group(1)), float(found.group(2))


def branded(data: bytes, crop: Crop | None = None, description: str = "") -> bytes:
    return with_logo(data, data, crop or Crop(), description)


def test_an_empty_corner_takes_the_logo_and_the_chart_keeps_its_size() -> None:
    svg = branded(chart(BAR))
    assert view(svg) == [0, 0, WIDTH, HEIGHT]
    assert logo_at(svg) == pytest.approx((WIDTH - MARGIN - SIDE, MARGIN))


def test_a_corner_with_something_in_it_grows_the_chart_upward() -> None:
    svg = branded(chart(BAR, CORNER))
    grown = MARK + 2 * MARGIN
    # Written to six significant digits, as every number in the wrapper is.
    assert view(svg) == pytest.approx([0, -grown, WIDTH, HEIGHT + grown], abs=1e-3)
    assert logo_at(svg) == pytest.approx((WIDTH - MARGIN - SIDE, MARGIN - grown), abs=1e-3)
    # The strip is the chart's own background, so it reads as more of the chart.
    assert b'fill="#ffffff"' in svg


def test_etany_org_is_set_under_the_logo_and_as_wide() -> None:
    svg = branded(chart(BAR))
    found = re.search(
        rb'<text x="([^"]*)" y="([^"]*)"[^>]* textLength="([^"]*)"[^>]*>etany.org<', svg
    )
    assert found is not None
    x, y, length = (float(n) for n in found.groups())
    assert x == pytest.approx(WIDTH - MARGIN - SIDE, abs=1e-3)
    assert length == pytest.approx(SIDE, abs=1e-3)
    assert MARGIN + SIDE < y <= MARGIN + MARK


def test_something_where_etany_org_would_go_grows_the_chart() -> None:
    """Below the logo's own corner, and still in the way."""
    under = f'<rect x="{WIDTH - MARGIN - SIDE:g}" y="{MARGIN + SIDE + 2:g}" width="20" height="4"/>'
    assert view(branded(chart(BAR, under)))[1] < 0


def test_a_background_with_rounded_corners_is_still_an_empty_corner() -> None:
    rounded = '<rect width="400" height="200" rx="8" fill="#fcfcfb"/>'
    assert view(branded(chart(BAR, background=rounded))) == [0, 0, WIDTH, HEIGHT]


def test_a_transparent_chart_grows_without_painting_a_strip() -> None:
    assert view(branded(chart(BAR, background=""))) == [0, 0, WIDTH, HEIGHT]
    svg = branded(chart(BAR, CORNER, background=""))
    assert view(svg)[1] < 0
    assert b"<rect y=" not in svg


def test_a_chart_sized_in_inches_is_looked_at_at_the_size_it_is() -> None:
    """`resvg` draws a nested chart sized in inches at its `viewBox`'s size,
    leaving its top right corner as empty canvas, which once put the logo on a bar."""
    inches = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="4in" height="2in" viewBox="0 0 100 50">'
        b'<rect width="100" height="50" fill="#fff"/>'
        b'<rect x="70" y="2" width="28" height="12" fill="#2a76d6"/></svg>'
    )
    assert view(branded(inches))[1] < 0


def test_a_chart_that_cannot_be_drawn_grows_rather_than_risk_covering_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreadable(svg: str, zoom: float = 1) -> object:
        raise ValueError("SVG has an invalid size")

    monkeypatch.setattr(branding, "draw_svg", unreadable)
    assert view(branded(chart(BAR)))[1] < 0


def test_a_crop_is_looked_at_as_cropped() -> None:
    """The corner that counts is the cropped chart's, which here trims the bar away."""
    original = chart(BAR, CORNER)
    crop = Crop(right=0.5)
    from eta_publish.images import crop_svg

    assert view(with_logo(crop_svg(original, crop), original, crop)) == [0, 0, WIDTH / 2, HEIGHT]


def test_the_chart_keeps_its_description() -> None:
    svg = branded(chart(BAR), description="Bars & more")
    assert b"<title>Bars &amp; more</title>" in svg


def credited(credit: str) -> bool:
    image = Image(object_id="io.1", filename="chart")
    doc = Document(blocks=[Figure(image=image, credit=[Text(text=credit)])])
    return credited_to_eta(doc, image)


@pytest.mark.parametrize(
    ("credit", "expected"),
    [
        ("Credit: ETA", True),
        ("Credit: ETA (Khyber Sen)", True),
        ("Credit: MTA, ETA (Blair Lorenzo)", False),
        ("Credit: ETAx", False),
        ("ETA", False),
        ("", False),
    ],
)
def test_a_chart_is_credited_to_eta_when_its_credit_starts_with_eta(
    credit: str, expected: bool
) -> None:
    assert credited(credit) is expected


def test_etany_org_turns_lighter_on_a_chart_drawn_dark() -> None:
    svg = branded(chart(BAR)).decode()
    assert f'class="{SITE_CLASS}" fill="{SITE_COLOR}">etany.org<' in svg
    dark = svg.partition("@media (prefers-color-scheme: dark)")[2]
    assert f".{SITE_CLASS}{{fill:{SITE_DARK_COLOR}}}" in dark
