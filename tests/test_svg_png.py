"""The PNG an SVG is offered as too, for whoever cannot use an SVG."""

import os
from pathlib import Path
from typing import cast

import pytest
from PIL import Image as Pillow

from eta_publish import images
from eta_publish.images import write_print_copies, write_web_copies
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


def _photo(path: Path, color: tuple[int, int, int]) -> Path:
    Pillow.new("RGB", (32, 32), color).save(path, "PNG")
    return path


def test_a_print_copy_made_from_the_same_picture_is_not_encoded_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    calls: list[Path] = []
    real = images._for_print

    def counting(path: Path) -> bytes | None:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(images, "_for_print", counting)
    dest = tmp_path / "print"
    first = write_print_copies({"io.1": photo}, dest)
    second = write_print_copies({"io.1": photo}, dest)
    assert first == second
    assert len(calls) == 1
    assert second["io.1"].is_file()


def test_a_changed_picture_or_a_missing_copy_is_encoded_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    calls: list[Path] = []
    real = images._for_print

    def counted(path: Path) -> bytes | None:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(images, "_for_print", counted)
    dest = tmp_path / "print"
    copy = write_print_copies({"io.1": photo}, dest)["io.1"]
    write_print_copies({"io.1": photo}, dest)
    assert len(calls) == 1
    _photo(photo, (10, 10, 200))
    write_print_copies({"io.1": photo}, dest)
    assert len(calls) == 2
    with Pillow.open(copy) as shown:
        assert cast("tuple[int, int, int]", shown.convert("RGB").getpixel((0, 0)))[2] > 150
    copy.unlink()
    write_print_copies({"io.1": photo}, dest)
    assert len(calls) == 3 and copy.is_file()


def test_writing_a_print_copy_leaves_the_file_it_is_linked_to_alone(tmp_path: Path) -> None:
    """A carried copy is a hard link to the last build's, which must not change."""
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    last = tmp_path / "last"
    copy = write_print_copies({"io.1": photo}, last)["io.1"]
    before = copy.read_bytes()
    this = tmp_path / "this"
    this.mkdir()
    for name in (copy.name, images.PRINT_SOURCES):
        os.link(last / name, this / name)
    _photo(photo, (10, 10, 200))
    write_print_copies({"io.1": photo}, this)
    assert copy.read_bytes() == before
    assert (this / copy.name).read_bytes() != before


def test_a_build_stopped_while_encoding_does_not_leave_a_copy_recorded_as_another_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record forgets a copy before it is rewritten, not after the last one is."""
    first = _photo(tmp_path / "first.png", (200, 10, 10))
    second = _photo(tmp_path / "second.png", (10, 200, 10))
    written = {"io.1": first, "io.2": second}
    dest = tmp_path / "print"
    copy = write_print_copies(written, dest)["io.1"]
    _photo(first, (10, 10, 200))
    _photo(second, (10, 10, 10))
    real = images._for_print

    def stopping(path: Path) -> bytes | None:
        if path == second:
            raise KeyboardInterrupt
        return real(path)

    monkeypatch.setattr(images, "_for_print", stopping)
    with pytest.raises(KeyboardInterrupt):
        write_print_copies(written, dest)
    calls: list[Path] = []

    def counting(path: Path) -> bytes | None:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(images, "_for_print", counting)
    _photo(first, (200, 10, 10))
    write_print_copies(written, dest)
    with Pillow.open(copy) as shown:
        assert cast("tuple[int, int, int]", shown.convert("RGB").getpixel((0, 0)))[0] > 150
    write_print_copies(written, dest)
    assert calls == [first, second]
