"""The fonts the PDF is set in are downloaded once, checked, and kept in the cache."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import override

import pytest
import requests
from requests.adapters import BaseAdapter

from eta_publish import fonts
from eta_publish.fonts import FontDownloadFailed, FontFile, FontMismatch, FontNotCached

URL = "https://fonts.test/Test.ttf"
FONT = b"the font's bytes"


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
