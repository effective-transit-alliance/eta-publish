"""Docs crops, which are stored as fractions and served uncropped."""

import io

import pytest
from PIL import Image as Pillow

from eta_publish.images import crop_to
from eta_publish.nodes import Crop, Document, Image


def png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Pillow.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def size(data: bytes) -> tuple[int, int]:
    with Pillow.open(io.BytesIO(data)) as opened:
        return opened.width, opened.height


def test_an_uncropped_image_is_left_alone() -> None:
    data = png(100, 50)
    image = Image(object_id="io.1", filename="img-x")
    assert crop_to(image, data, Document()) is data


def test_each_side_is_trimmed_by_its_fraction() -> None:
    image = Image(object_id="io.1", filename="img-x", crop=Crop(left=0.1, right=0.2, top=0.25))
    assert size(crop_to(image, png(100, 40), Document())) == (70, 30)


def test_the_format_survives_the_crop() -> None:
    """The extension is chosen from the download's content type,
    so a JPEG that came back as a PNG would be a lie."""
    buffer = io.BytesIO()
    Pillow.new("RGB", (100, 100), "white").save(buffer, format="JPEG")
    image = Image(object_id="io.1", filename="img-x", crop=Crop(bottom=0.5))
    with Pillow.open(io.BytesIO(crop_to(image, buffer.getvalue(), Document()))) as opened:
        assert opened.format == "JPEG"


def test_a_crop_that_leaves_nothing_is_reported_not_applied() -> None:
    doc = Document()
    image = Image(object_id="io.1", filename="img-x", crop=Crop(left=0.6, right=0.6))
    data = png(100, 100)
    assert crop_to(image, data, doc) is data
    assert any("crops to nothing" in w for w in map(str, doc.warnings))


def test_unreadable_data_is_reported_not_raised() -> None:
    doc = Document()
    image = Image(object_id="io.1", filename="img-x", crop=Crop(top=0.1))
    assert crop_to(image, b"not an image", doc) == b"not an image"
    assert any("could not crop" in w for w in map(str, doc.warnings))


@pytest.mark.parametrize(
    ("crop", "expected"),
    [
        (Crop(), ""),
        (Crop(left=0.0, right=0.0), ""),
        (Crop(right=0.25), "|0.000000,0.250000,0.000000,0.000000"),
    ],
)
def test_only_a_real_crop_changes_the_filename(crop: Crop, expected: str) -> None:
    """Recropping in the document produces a different published image,
    so it must not keep the old name and the old cached file.
    An uncropped image keeps the name it always had."""
    assert crop.key == expected


def test_a_leftover_offset_is_no_crop() -> None:
    """What Docs stores for a side nobody trimmed, which named the file as if it were cropped."""
    crop = Crop(left=1.110223e-16, right=1.110223e-16)
    assert not crop.trims
    assert crop.key == ""
    assert Crop(left=0.01).trims
