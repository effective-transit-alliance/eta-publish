"""The fonts the publications are set in, downloaded into the cache rather than committed.

Each is one pinned `ttf`, by its URL and its SHA-256,
so every machine sets a publication in the same bytes,
and a download that is not those bytes is an error rather than a different publication.
`typst` reads the directory they are kept in,
and the pages load a `woff2` the build makes from each of theirs.
"""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Lock

import requests
from fontTools.ttLib import TTFont
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

    @property
    def woff2(self) -> str:
        """What the pages load it as, in `assets/fonts/`."""
        return f"{self.name}.woff2"


# A font is one pinned `ttf`, which `typst` reads, and a page font gets a `woff2` built from it.
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

# DejaVu Sans 2.37, regular and bold, for the PDF alone:
# `typst` sets in it the text of the charts, whose SVGs name `DejaVu Sans`,
# and any character neither Yaldevi nor `typst`'s own fonts have, like the "⚠" of `template.typ`.
# The upstream release's own files, through jsDelivr's copy of the `dejavu-fonts-ttf` npm package,
# which ships them one file each, where the release itself is a tarball.
DEJAVU_SANS = FontFile(
    name="DejaVuSans",
    url="https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf",
    sha256="7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954",
)
DEJAVU_SANS_BOLD = FontFile(
    name="DejaVuSans-Bold",
    url="https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans-Bold.ttf",
    sha256="e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724",
)

PAGE_FONTS = (YALDEVI,)
"""The fonts the pages load, each as a `woff2`."""

FONTS = (*PAGE_FONTS, DEJAVU_SANS, DEJAVU_SANS_BOLD)
"""Every font, which is every file in `font_dir()`:
every one `typst` sets a PDF in but its own."""

_lock = Lock()
"""Held while the fonts are checked and fetched,
so publications built at once download and convert each only once."""

_woff2: dict[str, bytes] = {}
"""Each font converted, by its SHA-256, so a build converts it once."""


class FontNotCached(RuntimeError):
    """An offline build found a font not yet downloaded, which fails the publication.

    No page or PDF is set in another font in its place.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name} has not been downloaded, and an offline build downloads nothing; "
            "`eta-publish fonts`, or a build without `--offline`, downloads it once"
        )


class FontDownloadFailed(RuntimeError):
    """A font could not be downloaded, which fails the publication."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url} could not be downloaded: {reason}")


class FontMismatch(Exception):
    """A download is not the bytes it is pinned to.

    Not a `RuntimeError`, which fails only the publication:
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


def woff2s(fonts_dir: Path) -> dict[str, bytes]:
    """Each page font, from `fonts_dir` as `fonts` returns it, as the `woff2` the pages load.

    By the name it is served as.
    Converted by `fontTools`, which keeps every glyph and every table but `DSIG`,
    the signature of the `ttf`'s own bytes.
    The `ttf`'s own timestamp is kept, so the same `ttf` always makes the same bytes,
    and every build of the site serves the same file.
    """
    converted = {}
    with _lock:
        for font in PAGE_FONTS:
            if font.sha256 not in _woff2:
                ttf = TTFont(fonts_dir / font.ttf, recalcTimestamp=False)
                ttf.flavor = "woff2"
                out = BytesIO()
                ttf.save(out)
                _woff2[font.sha256] = out.getvalue()
            converted[font.woff2] = _woff2[font.sha256]
    return converted
