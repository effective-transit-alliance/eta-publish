"""The PNG an SVG is offered as too, for whoever cannot use an SVG."""

from pathlib import Path
from typing import cast

from PIL import Image as Pillow

from eta_publish.images import write_web_copies
from eta_publish.naming import PNG_SIDE

CHART = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
    '<rect x="100" y="50" width="200" height="100" fill="#2a76d6"/></svg>'
)


def pixel(png: Pillow.Image, x: int, y: int) -> tuple[int, int, int, int]:
    return cast("tuple[int, int, int, int]", png.getpixel((x, y)))


def test_an_svg_is_drawn_as_a_png_as_large_as_a_slide_wants(tmp_path: Path) -> None:
    """Its longer side `PNG_SIDE` across, and transparent where the SVG draws nothing."""
    svg = tmp_path / "chart.svg"
    svg.write_text(CHART)
    written = write_web_copies({"io.1": svg}, tmp_path)
    assert [p.name for p in written] == ["chart.png"]
    with Pillow.open(written[0]) as png:
        assert png.size == (PNG_SIDE, PNG_SIDE // 2)
        assert pixel(png, 0, 0)[3] == 0
        assert pixel(png, PNG_SIDE // 2, PNG_SIDE // 4)[:3] == (0x2A, 0x76, 0xD6)


def test_a_png_already_drawn_from_the_same_svg_is_kept(tmp_path: Path) -> None:
    svg = tmp_path / "chart.svg"
    svg.write_text(CHART)
    png = write_web_copies({"io.1": svg}, tmp_path)[0]
    png.write_bytes(b"kept")
    write_web_copies({"io.1": svg}, tmp_path)
    assert png.read_bytes() == b"kept"
