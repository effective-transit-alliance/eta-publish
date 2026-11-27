"""The fonts are downloaded once, checked, and kept in the cache, and made into `woff2`s."""

from collections.abc import Mapping
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import override

import pytest
import requests
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from requests.adapters import BaseAdapter

from eta_publish import fonts
from eta_publish.assets import read
from eta_publish.fonts import (
    PAGE_FONTS,
    FontDownloadFailed,
    FontFile,
    FontMismatch,
    FontNotCached,
    woff2s,
)

URL = "https://fonts.test/Test.ttf"


def _font() -> bytes:
    """A `ttf` with a square for `a` and nothing for a space."""
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0))
    pen.lineTo((100, 500))
    pen.lineTo((400, 500))
    pen.lineTo((400, 0))
    pen.closePath()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "space", "a"])
    builder.setupCharacterMap({ord(" "): "space", ord("a"): "a"})
    builder.setupGlyf(
        {".notdef": TTGlyphPen(None).glyph(), "space": TTGlyphPen(None).glyph(), "a": pen.glyph()}
    )
    builder.setupHorizontalMetrics({".notdef": (500, 0), "space": (250, 0), "a": (500, 100)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    out = BytesIO()
    builder.save(out)
    return out.getvalue()


FONT = _font()


class _Served(BaseAdapter):
    """Answers every request with `body`, and counts them."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__()
        self.body = body
        self.status = status
        self.asked = 0

    @override
    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | tuple[float, None] | None = None,
        verify: bool | str = True,
        cert: bytes | str | tuple[bytes | str, bytes | str] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.Response:
        self.asked += 1
        response = requests.Response()
        response.status_code = self.status
        response._content = self.body
        response.url = request.url or ""
        response.request = request
        return response

    @override
    def close(self) -> None:
        pass


def _http(adapter: _Served) -> requests.Session:
    http = requests.Session()
    http.mount("https://", adapter)
    return http


@pytest.fixture(autouse=True)
def _one_font(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pinned = FontFile(name="Test", url=URL, sha256=sha256(FONT).hexdigest())
    monkeypatch.setattr(fonts, "FONTS", (pinned,))
    monkeypatch.setattr(fonts, "PAGE_FONTS", (pinned,))
    monkeypatch.setattr(fonts, "font_dir", lambda: tmp_path / "fonts")


def test_a_font_is_downloaded_once(tmp_path: Path) -> None:
    served = _Served(FONT)
    assert fonts.fonts(http=_http(served)) == tmp_path / "fonts"
    assert (tmp_path / "fonts" / "Test.ttf").read_bytes() == FONT
    fonts.fonts(http=_http(served))
    assert served.asked == 1


def test_offline_a_cached_font_is_used() -> None:
    fonts.fonts(http=_http(_Served(FONT)))
    fonts.fonts(offline=True)


def test_offline_a_font_not_cached_costs_the_pdf() -> None:
    with pytest.raises(FontNotCached):
        fonts.fonts(offline=True)


def test_a_download_of_other_bytes_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FontMismatch):
        fonts.fonts(http=_http(_Served(b"some other bytes")))
    assert not (tmp_path / "fonts" / "Test.ttf").exists()


def test_a_failed_download_costs_the_pdf() -> None:
    with pytest.raises(FontDownloadFailed):
        fonts.fonts(http=_http(_Served(b"", status=503)))


def test_a_cached_font_that_changed_is_downloaded_again(tmp_path: Path) -> None:
    cached = tmp_path / "fonts" / "Test.ttf"
    cached.parent.mkdir()
    cached.write_bytes(FONT[:5])
    with pytest.raises(FontNotCached):
        fonts.fonts(offline=True)
    fonts.fonts(http=_http(_Served(FONT)))
    assert cached.read_bytes() == FONT


def test_the_pages_get_a_woff2_of_each_font_with_every_glyph() -> None:
    converted = woff2s(fonts.fonts(http=_http(_Served(FONT))))
    assert list(converted) == ["Test.woff2"]
    woff2 = TTFont(BytesIO(converted["Test.woff2"]))
    assert woff2.flavor == "woff2"
    ttf = TTFont(BytesIO(FONT))
    assert woff2.getBestCmap() == ttf.getBestCmap()
    assert woff2.getGlyphOrder() == ttf.getGlyphOrder()


def test_a_font_always_makes_the_same_woff2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every build of the site serves the same bytes, whenever it converted them."""
    source = fonts.fonts(http=_http(_Served(FONT)))
    # What `fontTools` stamps a font it saves with, unless told to keep the font's own.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    first = woff2s(source)
    monkeypatch.setattr(fonts, "_woff2", {})
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "2000000000")
    assert woff2s(source) == first


def test_the_pages_load_each_font_from_the_site() -> None:
    css = read("page.css")
    for font in PAGE_FONTS:
        assert f'url("fonts/{font.woff2}") format("woff2")' in css
