"""A dark mode for a chart that brings none of its own.

Most charts are drawn for a white page: a white background, black or grey text and lines.
On a dark page that is a white box.
A chart is given a `prefers-color-scheme: dark` stylesheet that swaps each of its greys,
white through black, for the grey at the same place on a dark page's scale,
so its background turns dark and its text light.
Every other color is a color the chart chose to mean something, a bar or a line,
and is left as it is.
So is light text: on a chart drawn for a white page it can only be read
where it sits on one of those colors, like a value written inside its bar.

Nothing of the drawing is rewritten: the stylesheet picks out what to swap by the
`fill`, `stroke`, or `style` it is drawn with, which a stylesheet overrides,
and anything that ignores the stylesheet, the PDF included, draws the chart as it was.

A chart with a dark mode of its own is left to it.
"""

import re

from .images import svg_size

LOGO_CLASS = "eta-logo"
"""What the logo is marked with, so its white glyphs are not swapped with the chart's white."""

LIGHTEST = 0x1A
"""What white becomes: a dark grey, a little lighter than a dark page,
so the chart still reads as one."""

DARKEST = 0xEA
"""What black becomes: the light grey a dark page sets its text in."""

SPREAD = 10
"""How far apart a color's channels can be and it still be a grey,
for the greys that are a little warm or cool, like a gridline's `#e1e0d9`.
Not much further: a blue-grey bar like `#9aa3ad` is a color the chart chose."""

_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0)}

_PAINTED = re.compile(r'\s(fill|stroke)\s*=\s*"([^"]*)"')
_STYLE = re.compile(r'\sstyle\s*=\s*"([^"]*)"')


def with_dark_mode(data: bytes, original: bytes) -> bytes:
    """`data` with its greys swapped on a dark page, unless `original` has a dark mode already.

    `original` is the chart as it was downloaded, since `data` may carry the logo's own
    dark rule, which is not the chart's.
    """
    if b"prefers-color-scheme" in original:
        return data
    text = data.decode(errors="replace")
    rules: list[str] = []
    for prop, value in sorted(set(_PAINTED.findall(text))):
        swap = _dark(value)
        if swap is not None:
            dark, light = swap
            rules.append(f"{_selector(prop, value, light)}{{{prop}:{dark}!important}}")
    for style in sorted(set(_STYLE.findall(text))):
        # Light and dark apart, since only the light ones leave text alone.
        swapped: dict[bool, list[str]] = {True: [], False: []}
        for prop, value in _declarations(style):
            swap = _dark(value) if prop in ("fill", "stroke") else None
            if swap is not None:
                dark, light = swap
                swapped[light].append(f"{prop}:{dark}!important")
        for light, declarations in swapped.items():
            if declarations:
                selector = _selector("style", style, light)
                rules.append(f"{selector}{{{';'.join(declarations)}}}")
    if not rules:
        return data
    start, _, _ = svg_size(data, "give it a dark mode")
    end = data.find(b">", start)
    if end < 0:
        return data
    style = f"<style>@media (prefers-color-scheme: dark){{{''.join(rules)}}}</style>"
    return data[: end + 1] + style.encode() + data[end + 1 :]


def _selector(attribute: str, value: str, light: bool) -> str:
    quoted = value.replace("\\", "\\\\").replace('"', '\\"')
    text = ":not(text):not(text *)" if light else ""
    return f'[{attribute}="{quoted}"]:not(.{LOGO_CLASS} *){text}'


def _declarations(style: str) -> list[tuple[str, str]]:
    found = []
    for declaration in style.split(";"):
        prop, colon, value = declaration.partition(":")
        if colon:
            found.append((prop.strip().lower(), value.strip()))
    return found


def _dark(color: str) -> tuple[str, bool] | None:
    """The grey `color` becomes on a dark page and whether `color` is light,
    or `None` where it is not a grey."""
    rgb = _rgb(color)
    if rgb is None or max(rgb) - min(rgb) > SPREAD:
        return None
    light = sum(rgb) / 3 / 255
    grey = round(LIGHTEST + (DARKEST - LIGHTEST) * (1 - light))
    return f"#{grey:02x}{grey:02x}{grey:02x}", light > 0.5


def _rgb(color: str) -> tuple[int, int, int] | None:
    color = color.strip().lower()
    if color in _NAMED:
        return _NAMED[color]
    if not re.fullmatch(r"#(?:[0-9a-f]{3}|[0-9a-f]{6})", color):
        return None
    digits = color[1:]
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return red, green, blue
