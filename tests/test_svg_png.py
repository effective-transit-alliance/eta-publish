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


def test_a_png_already_drawn_from_the_same_svg_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svg = tmp_path / "chart.svg"
    svg.write_text(CHART)
    png = write_web_copies({"io.1": svg}, tmp_path)[0]
    before = png.stat().st_ino
    _pin_codes(monkeypatch)
    monkeypatch.setattr(images, "_for_web", _never)
    write_web_copies({"io.1": svg}, tmp_path)
    assert png.stat().st_ino == before


def _never(path: Path, width: int, extension: str) -> bytes:
    raise AssertionError(f"{path.name} was encoded again as {extension}")


def _never_for_print(path: Path) -> bytes | None:
    raise AssertionError(f"{path.name} was encoded again for print")


def _photo(path: Path, color: tuple[int, int, int]) -> Path:
    Pillow.new("RGB", (32, 32), color).save(path, "PNG")
    return path


def _pin_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the code hashes the real encoders', before a test wraps them.

    The hashes read the source of `_for_print` and `_for_web`, which would be the wrapper's.
    """
    print_code = images._print_code()
    web_codes = {extension: images._web_code(extension) for extension in ("png", "avif", "webp")}

    def web_code(extension: str) -> str:
        return web_codes[extension]

    monkeypatch.setattr(images, "_print_code", lambda: print_code)
    monkeypatch.setattr(images, "_web_code", web_code)


def test_a_print_copy_made_from_the_same_picture_is_not_encoded_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    calls: list[Path] = []
    real = images._for_print

    def counting(path: Path) -> bytes | None:
        calls.append(path)
        return real(path)

    _pin_codes(monkeypatch)
    monkeypatch.setattr(images, "_for_print", counting)
    dest = tmp_path / "print"
    first = write_print_copies({"io.1": photo}, dest)
    second = write_print_copies({"io.1": photo}, dest)
    assert first == second
    assert len(calls) == 1
    assert second["io.1"].is_file()


def test_a_changed_picture_is_encoded_again_and_a_missing_copy_linked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    calls: list[Path] = []
    real = images._for_print

    def counted(path: Path) -> bytes | None:
        calls.append(path)
        return real(path)

    _pin_codes(monkeypatch)
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
    assert len(calls) == 2 and copy.is_file()


def test_writing_a_print_copy_leaves_the_file_it_is_linked_to_alone(tmp_path: Path) -> None:
    """A copy may be a hard link to another build's, which must not change."""
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    last = tmp_path / "last"
    copy = write_print_copies({"io.1": photo}, last)["io.1"]
    before = copy.read_bytes()
    this = tmp_path / "this"
    this.mkdir()
    os.link(copy, this / copy.name)
    _photo(photo, (10, 10, 200))
    write_print_copies({"io.1": photo}, this)
    assert copy.read_bytes() == before
    assert (this / copy.name).read_bytes() != before


def test_the_copy_of_a_picture_taken_out_is_removed(tmp_path: Path) -> None:
    """Whatever else is in the folder, which a build writes the posters into after."""
    kept = _photo(tmp_path / "kept.png", (200, 10, 10))
    gone = _photo(tmp_path / "gone.png", (10, 10, 200))
    dest = tmp_path / "print"
    copies = write_print_copies({"io.1": kept, "io.2": gone}, dest)
    write_print_copies({"io.1": kept}, dest)
    assert [p.name for p in dest.iterdir()] == [copies["io.1"].name]


def test_a_copy_one_build_made_is_linked_into_another_rather_than_made_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kept by the picture's bytes and what made it, not by where the build is."""
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    first = write_print_copies({"io.1": photo}, tmp_path / "first" / "print")["io.1"]
    pages = write_web_copies({"io.1": photo}, tmp_path / "first" / "images")
    _pin_codes(monkeypatch)
    monkeypatch.setattr(images, "_for_print", _never_for_print)
    monkeypatch.setattr(images, "_for_web", _never)
    second = write_print_copies({"io.1": photo}, tmp_path / "second" / "print")["io.1"]
    again = write_web_copies({"io.1": photo}, tmp_path / "second" / "images")
    assert second.stat().st_ino == first.stat().st_ino
    assert [p.name for p in again] == [p.name for p in pages]
    assert [p.stat().st_ino for p in again] == [p.stat().st_ino for p in pages]


@pytest.mark.parametrize("change", ["Pillow", "code"])
def test_a_print_copy_is_encoded_again_when_what_encodes_it_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    """It is kept by the Pillow and the code that made it, beside the picture's bytes."""
    photo = _photo(tmp_path / "photo.png", (200, 10, 10))
    calls: list[Path] = []
    real = images._for_print

    def counting(path: Path) -> bytes | None:
        calls.append(path)
        return real(path)

    _pin_codes(monkeypatch)
    monkeypatch.setattr(images, "_for_print", counting)
    dest = tmp_path / "print"
    write_print_copies({"io.1": photo}, dest)
    write_print_copies({"io.1": photo}, dest)
    assert calls == [photo]
    if change == "Pillow":
        monkeypatch.setattr(images.Pillow, "__version__", "0.0.0")
    else:
        monkeypatch.setattr(images, "_print_code", lambda: "an edited _for_print")
    write_print_copies({"io.1": photo}, dest)
    assert calls == [photo, photo]
    write_print_copies({"io.1": photo}, dest)
    assert calls == [photo, photo]


@pytest.mark.parametrize("change", ["Pillow", "code"])
@pytest.mark.parametrize("picture", ["photo.png", "chart.svg"])
def test_a_page_copy_is_encoded_again_when_what_encodes_it_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str, picture: str
) -> None:
    """It is kept by the Pillow and the code that made it, beside the picture's bytes."""
    path = tmp_path / picture
    if picture.endswith(".svg"):
        path.write_text(CHART)
    else:
        _photo(path, (200, 10, 10))
    calls: list[str] = []
    real = images._for_web

    def counting(path: Path, width: int, extension: str) -> bytes:
        calls.append(extension)
        return real(path, width, extension)

    _pin_codes(monkeypatch)
    monkeypatch.setattr(images, "_for_web", counting)
    out = tmp_path / "out"
    copies = write_web_copies({"io.1": path}, out)
    write_web_copies({"io.1": path}, out)
    made = len(calls)
    assert made == len(copies) > 0
    if change == "Pillow":
        monkeypatch.setattr(images.Pillow, "__version__", "0.0.0")
    else:

        def edited(extension: str) -> str:
            return f"an edited {extension} encoder"

        monkeypatch.setattr(images, "_web_code", edited)
    write_web_copies({"io.1": path}, out)
    assert len(calls) == 2 * made
    write_web_copies({"io.1": path}, out)
    assert len(calls) == 2 * made
