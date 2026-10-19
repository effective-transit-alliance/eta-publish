"""A dark mode for a chart that brings none of its own."""

import io

import resvg_py
from PIL import Image as Pillow

from eta_publish.dark import LOGO_CLASS, with_dark_mode

CHART = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
    b'<rect width="100" height="50" fill="#fff"/>'
    b'<rect x="10" y="10" width="40" height="30" fill="#2a76d6"/>'
    b'<text x="12" y="30" style="fill:#ffffff">57%</text>'
    b'<text x="60" y="30" fill="#333">label</text>'
    b"</svg>"
)


def dark_rules(svg: bytes) -> str:
    rules = svg.decode().partition("@media (prefers-color-scheme: dark)")[2]
    return rules.partition("</style>")[0]


def test_the_greys_swap_and_the_colors_stay() -> None:
    rules = dark_rules(with_dark_mode(CHART, CHART))
    assert '[fill="#fff"]' in rules
    assert '[fill="#333"]' in rules
    assert "#2a76d6" not in rules


def test_light_text_is_left_on_the_color_it_sits_on() -> None:
    rules = dark_rules(with_dark_mode(CHART, CHART))
    assert '[style="fill:#ffffff"]' in rules
    assert ":not(text):not(text *){fill:" in rules.split('[style="fill:#ffffff"]')[1]


def test_the_logo_keeps_its_white() -> None:
    for rule in dark_rules(with_dark_mode(CHART, CHART)).split("}"):
        if "[" in rule:
            assert f":not(.{LOGO_CLASS} *)" in rule


def test_a_chart_with_a_dark_mode_of_its_own_is_left_to_it() -> None:
    own = CHART.replace(b"</svg>", b"<style>@media (prefers-color-scheme: dark){}</style></svg>")
    assert with_dark_mode(own, own) == own


def test_anything_that_ignores_the_rule_draws_the_chart_as_it_was() -> None:
    """`resvg`, which is what the PDF is drawn with."""
    drawn = resvg_py.svg_to_bytes(svg_string=with_dark_mode(CHART, CHART).decode())
    assert Pillow.open(io.BytesIO(bytes(drawn))).convert("RGB").getpixel((90, 45)) == (
        255,
        255,
        255,
    )
