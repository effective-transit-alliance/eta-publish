"""The fonts the PDF is set in, downloaded into the cache rather than committed.

Each is one pinned `ttf`, by its URL and its SHA-256,
so every machine sets the PDF in the same bytes,
and a download that is not those bytes is an error rather than a different PDF.
`typst` reads the directory they are kept in.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock

import requests
from platformdirs import user_cache_path
from requests import RequestException

from . import PACKAGE_NAME
from .naming import replace_bytes


@dataclass(frozen=True)
class FontFile:
    """A font, and the one download it can be."""

    name: str
    url: str
    sha256: str

    @property
    def ttf(self) -> str:
        """What it is kept as in `font_dir()`."""
        return f"{self.name}.ttf"


# Yaldevi, the typeface etany.org sets its text in,
# as one variable font holding every weight, which `typst` sets at whatever weight it is asked for.
# Google Fonts' repository at the commit that added this version, through jsDelivr's copy of it,
# rather than a font host's copy, which is split by script into several files:
# `typst` sets a family from only one of them,
# and would set every character outside it in another font.
YALDEVI = FontFile(
    name="Yaldevi",
    url=(
        "https://cdn.jsdelivr.net/gh/google/fonts@5236812944acca710a7b6db2dbc583a02671ea2f"
        "/ofl/yaldevi/Yaldevi%5Bwght%5D.ttf"
    ),
    sha256="21d5516cd9a8831964b57503f5b7a119aafa9603bdddd0183e91a0ac8c8dc2e4",
)

FONTS = (YALDEVI,)
"""Every font, which is every file in `font_dir()`."""

_lock = Lock()
"""Held while the fonts are checked and fetched,
so publications built at once download each only once."""


class FontNotCached(RuntimeError):
    """An offline build found a font not yet downloaded, which costs the PDF.

    Carries the font's name. Said by `build_pdf`, as `TypstMissing` is.
    """


class FontDownloadFailed(RuntimeError):
    """A font could not be downloaded, which costs the PDF.

    Carries the font's URL and what went wrong. Said by `build_pdf`.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(url, reason)
        self.url = url
        self.reason = reason


class FontMismatch(Exception):
    """A download is not the bytes it is pinned to.

    Not a `RuntimeError`, which `build_pdf` reports and moves on from:
    a pinned file that changed is this code to fix, so the build stops.
    """


def font_dir() -> Path:
    """Where the fonts are kept: the cache, as nothing in it is anything but a download."""
    return user_cache_path(PACKAGE_NAME) / "fonts"


def _matches(path: Path, font: FontFile) -> bool:
    return path.is_file() and sha256(path.read_bytes()).hexdigest() == font.sha256


def fonts(offline: bool = False, http: requests.Session | None = None) -> Path:
    """The directory holding every font in `FONTS`, downloading any it lacks.

    A cached file is checked against its checksum each time,
    so one cut short or changed on disk is downloaded again rather than used.
    Offline, nothing is downloaded: a font not there raises `FontNotCached`.
    Online, one that cannot be downloaded raises `FontDownloadFailed`,
    and one that downloads as other bytes than it is pinned to, `FontMismatch`.
    """
    dest = font_dir()
    with _lock:
        for font in FONTS:
            path = dest / font.ttf
            if _matches(path, font):
                continue
            if offline:
                raise FontNotCached(font.name)
            try:
                response = (http or requests.Session()).get(font.url, timeout=60)
                response.raise_for_status()
            except RequestException as e:
                raise FontDownloadFailed(font.url, str(e)) from e
            digest = sha256(response.content).hexdigest()
            if digest != font.sha256:
                raise FontMismatch(
                    f"{font.url} has SHA-256 {digest}, not the {font.sha256} it is pinned to"
                )
            replace_bytes(path, response.content)
    return dest
