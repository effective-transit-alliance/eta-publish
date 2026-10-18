"""Write an SVG with every transform applied to the coordinates it moves.

For `scripts/build-logo.sh`. Inkscape drew the logo's icons thousands of units across
and scaled them down through nested groups, so every coordinate carried digits
that the scaling then threw away. Applied, they are numbers in the logo's own
40-unit box, which `svgo` can round to two decimals without moving anything.

Each shape becomes a path with its fill, its stroke, and the stroke's width as drawn,
and shapes drawn one after another in the same style become one path:
the order is kept, so what was drawn over something still is.

    python flatten-svg.py SOURCE OUTPUT
"""

import sys

from svgelements import SVG, Color, Path, Shape


def colour(paint: Color | None) -> str | None:
    """`paint` as a hex color, or `None` for none or fully transparent."""
    if paint is None or paint.value is None or Color(paint).alpha == 0:
        return None
    return Color(paint).hex


def flatten(source: str) -> str:
    svg = SVG.parse(source, reify=True)
    # The source is sized in millimeters, which `svgelements` reads as pixels,
    # so this scales back to the `viewBox` the source draws in.
    x, y, width, height = svg.viewbox.x, svg.viewbox.y, svg.viewbox.width, svg.viewbox.height
    scale = width / svg.width
    runs: list[tuple[str, list[str]]] = []
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        fill = colour(element.fill)
        stroke = colour(element.stroke)
        if fill is None and stroke is None:
            continue
        path = Path(element) * f"scale({scale})"
        path.reify()
        style = f'fill="{fill or "none"}"'
        if stroke is not None:
            style += f' stroke="{stroke}" stroke-width="{element.implicit_stroke_width * scale}"'
        # Absolute, since two paths' data joined into one would otherwise
        # start the second where the first ended.
        data = path.d(relative=False)
        if runs and runs[-1][0] == style:
            runs[-1][1].append(data)
        else:
            runs.append((style, [data]))
    paths = "".join(f'<path {style} d="{" ".join(data)}"/>' for style, data in runs)
    box = f"{x} {y} {width} {height}"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}">{paths}</svg>\n'


if __name__ == "__main__":
    source, output = sys.argv[1:]
    with open(output, "w") as out:
        out.write(flatten(source))
