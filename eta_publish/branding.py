"""The ETA logo and `etany.org` in the top right corner of every chart credited to ETA.

A chart is credited to ETA when its figure's `Credit:` line starts with `ETA`,
and it is a chart when it is an SVG: a photograph credited to ETA is a photograph.

The logo goes in the corner where the corner is empty, and above the chart where it is not:
the chart grows a strip along its top, in its own background color,
and the logo sits in that, so it never covers anything the chart draws.
Which it is gets decided by drawing the chart and looking,
since only a drawing says where a title ends or how tall a bar reaches.

The decision is one or the other rather than the least the chart could grow by,
because the drawing is made with whatever fonts this machine has,
and a chart's text set in another font is a few pixels wider or narrower:
a choice between two answers changes only when a chart is that close to the logo,
where the least growth would change with every machine that drew it.
For the same reason, anything that keeps the chart from being drawn and looked at
puts the logo above the chart: room that was not needed costs a strip of background,
and a logo over a title costs the title.
"""

import io
import re
from collections import Counter
from functools import cache
from html import escape

lazy import resvg_py
lazy from PIL import Image as Pillow

from .assets import read
from .dark import LOGO_CLASS
from .images import svg_size
from .nodes import Crop, Document, Figure, Image, plain_text

LOGO_SHARE = 0.055
"""How wide the logo is, as a share of the chart's width: 42 units across a chart 760 wide."""

MARGIN_SHARE = 1 / 3
"""The space around the logo, as a share of the logo's own width."""

SITE_SHARE = 0.22
"""How tall `etany.org` is set, as a share of the logo's width.

Stretched or squeezed to exactly the logo's width whatever font draws it,
so the two read as one mark and the corner it needs is known before it is drawn."""

GAP_SHARE = 0.1
"""The space between the logo and `etany.org`, as a share of the logo's width."""

SITE_COLOR = "#001faa"
"""The logo's own navy."""

SITE_DARK_COLOR = "#8fa6ff"
"""`etany.org` on a chart drawn dark, where the navy all but disappears.

The logo keeps its navy: its squares are their own background."""

SITE_CLASS = "eta-site"
"""What `etany.org` is marked with, for its dark color to find it.

Named for this, since the chart's own stylesheet is in the same document
and can have a class of nearly any name."""

SITE_FONTS = "system-ui, -apple-system, Segoe UI, Helvetica, Arial, DejaVu Sans, sans-serif"
"""Whatever sans serif the reader's system draws its own text in."""

TOLERANCE = 8
"""How far a pixel's channels can be from the background's and still be background:
the antialiasing at the edge of a background drawn as a rectangle."""


_ETA = re.compile(r"ETA\b")


def credited_to_eta(doc: Document, image: Image) -> bool:
    """Whether `image` is the picture of a figure whose `Credit:` line starts with `ETA`."""
    return any(
        figure.image.object_id == image.object_id and _credits_eta(figure) for figure in doc.figures
    )


def _credits_eta(figure: Figure) -> bool:
    credit = plain_text(figure.credit).strip()
    label, colon, said = credit.partition(":")
    return bool(colon) and label.strip().casefold() == "credit" and bool(_ETA.match(said.strip()))


def with_logo(data: bytes, original: bytes, crop: Crop, description: str = "") -> bytes:
    """`data` with the logo in its top right corner, the chart grown taller where it has to be.

    Nested whole inside an `svg` of its own, as a crop is,
    so nothing of the drawing is rewritten.
    `description` is the chart's own `<title>` and `<desc>`, which the nesting would hide
    from anything that reads them off the root.

    `data` is `original` with `crop` applied, and it is `original` that is drawn,
    with the crop then cut out of the drawing:
    the crop nests the chart, which `resvg` does not always draw at the size it is.
    """
    start, width, height = svg_size(data, "place the logo")
    side = width * LOGO_SHARE
    margin = side * MARGIN_SHARE
    size = side * SITE_SHARE
    gap = side * GAP_SHARE
    # The logo, the gap, and `etany.org`, which descends no further than its size.
    mark = side + gap + size
    drawn = _drawn(original, crop)
    background = _background(drawn) if drawn is not None else None
    clear = (
        drawn is not None
        and background is not None
        and _clear(drawn, background, width - side - 2 * margin, mark + 2 * margin)
    )
    grown = 0.0 if clear else mark + 2 * margin
    # `-0` where nothing grew, which is a valid number and an odd one to read.
    top = -grown or 0.0
    tall = height + grown
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {top:g} {width:g} {tall:g}"'
        f' width="{width:g}" height="{tall:g}">'
    ]
    if description:
        parts.append(f"<title>{escape(description)}</title>")
    if grown and background is not None and background[3]:
        red, green, blue, alpha = background
        opacity = "" if alpha == 255 else f' fill-opacity="{alpha / 255:.3g}"'
        parts.append(
            f'<rect y="{top:g}" width="{width:g}" height="{grown:g}"'
            f' fill="#{red:02x}{green:02x}{blue:02x}"{opacity}/>'
        )
    parts.append(f'<svg width="{width:g}" height="{height:g}">')
    chart = data[start:].rstrip()
    x = width - margin - side
    y = margin - grown
    placed = _logo().replace(
        "<svg ",
        f'<svg x="{x:g}" y="{y:g}" width="{side:g}" height="{side:g}" class="{LOGO_CLASS}" ',
        1,
    )
    # On a baseline a fifth of its size above the bottom of its room,
    # which is about where a sans serif's descenders end, and `etany.org` has one.
    site = (
        f'<text x="{x:g}" y="{y + side + gap + size * 0.8:g}" font-size="{size:g}"'
        f' textLength="{side:g}" lengthAdjust="spacingAndGlyphs"'
        f' font-family="{SITE_FONTS}"'
        f' class="{SITE_CLASS}" fill="{SITE_COLOR}">etany.org</text>'
    )
    style = (
        f"<style>@media (prefers-color-scheme: dark)"
        f"{{.{SITE_CLASS}{{fill:{SITE_DARK_COLOR}}}}}</style>"
    )
    closing = f"</svg>{placed}{site}{style}</svg>\n"
    return data[:start] + "".join(parts).encode() + chart + closing.encode()


@cache
def _logo() -> str:
    return read("logo.svg").strip()


def _drawn(data: bytes, crop: Crop) -> Pillow.Image | None:
    """`crop` of the chart drawn one pixel to a unit, or `None` where it cannot be drawn faithfully.

    With its own `width` and `height` said again in pixels, rather than nested in something
    that says so: `resvg` draws a nested `svg` sized in inches at its `viewBox`'s size,
    a corner of empty canvas beside a chart three quarters the size it is,
    and refuses an inch-sized root outright.
    """
    if not _fonts_draw():
        return None
    start, width, height = svg_size(data, "place the logo")
    end = data.find(b">", start)
    if end < 0:
        return None
    root = data[start:end].decode(errors="replace")
    for name, value in (("width", width), ("height", height)):
        sized, found = _SIZE[name].subn(rf'\g<1>{name}="{value:g}"', root, count=1)
        root = sized if found else f'{root} {name}="{value:g}"'
    try:
        drawn = _draw(data[:start].decode() + root + data[end:].decode())
    except ValueError, UnicodeDecodeError:
        return None
    # Drawn at another size, or not at all, is not this chart.
    if drawn.size != (round(width), round(height)) or drawn.getchannel("A").getbbox() is None:
        return None
    if not crop.trims:
        return drawn
    return drawn.crop(
        (
            round(crop.left * width),
            round(crop.top * height),
            round((1 - crop.right) * width),
            round((1 - crop.bottom) * height),
        )
    )


_SIZE = {name: re.compile(rf'(\s){name}\s*=\s*"[^"]*"') for name in ("width", "height")}


def _draw(svg: str) -> Pillow.Image:
    """`svg` drawn, with every family of font falling back to one that is here.

    Every family, not only `sans-serif`: text in a font that resolves to nothing is not drawn,
    and a corner whose title was not drawn looks empty.
    DejaVu Sans is wider than Helvetica, Arial, or anything a reader's system draws a chart in,
    so a title measured in it ends further right than it will on the page, which errs toward room.
    """
    png = resvg_py.svg_to_bytes(
        svg_string=svg,
        font_family="DejaVu Sans",
        sans_serif_family="DejaVu Sans",
        serif_family="DejaVu Serif",
        monospace_family="DejaVu Sans Mono",
    )
    return Pillow.open(io.BytesIO(bytes(png))).convert("RGBA")


@cache
def _fonts_draw() -> bool:
    """Whether text draws at all here, which it does not where none of `FONTS` is installed."""
    probe = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
        '<text x="2" y="16" font-size="16" font-family="sans-serif">ETA</text></svg>'
    )
    try:
        return _draw(probe).getchannel("A").getbbox() is not None
    except ValueError:
        return False


def _background(drawn: Pillow.Image) -> tuple[int, int, int, int] | None:
    """The chart's background: the color most of its top row is.

    Not the corner pixel, which a background with rounded corners leaves transparent.
    `None` where no color is most of the row, which is a chart with no background to speak of
    drawn right up to its top edge.
    """
    row = _pixels(drawn.crop((0, 0, drawn.width, 1)))
    color, count = Counter(row).most_common(1)[0]
    if count * 2 < len(row):
        return None
    red, green, blue, alpha = color
    return red, green, blue, alpha


def _clear(
    drawn: Pillow.Image, background: tuple[int, int, int, int], left: float, bottom: float
) -> bool:
    """Whether everything right of `left` and above `bottom` looks like `background`.

    Looks like: drawn over the background, as the page draws it over its own,
    so what the chart leaves transparent is background too.
    A background with rounded corners leaves its corners part transparent,
    and one that stops short of the edge leaves the rest clear.
    """
    box = (max(0, int(left)), 0, drawn.width, min(drawn.height, int(bottom) + 1))
    corner = Pillow.new("RGBA", (box[2] - box[0], box[3] - box[1]), background)
    corner.alpha_composite(drawn.crop(box))
    for pixel in _pixels(corner):
        if any(abs(a - b) > TOLERANCE for a, b in zip(pixel, background, strict=True)):
            return False
    return True


def _pixels(drawn: Pillow.Image) -> list[tuple[int, ...]]:
    """Every pixel of an RGBA drawing, as its four channels."""
    raw = drawn.tobytes()
    return [tuple(raw[i : i + 4]) for i in range(0, len(raw), 4)]
