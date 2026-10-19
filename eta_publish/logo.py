"""The logo a chart credited to ETA carries: the logo as drawn, minified.

`assets/logo.src.svg` is the logo as Inkscape saved it, and is what gets edited.
`assets/logo.svg` is what `svgo` makes of it, as `logo.svgo.mjs` says,
and is what a chart carries: under a quarter of the size, and drawn the same.
It is committed like the site, so a diff shows what an edit to the logo did.

Every build writes it first, so an edited logo cannot go out as the old one.
`svgo` runs on Node, and starting Node is most of the fifth of a second it takes,
which every build and every test of one would pay for an answer that almost never changes.
So the answer is cached, keyed on everything that decides it.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import platformdirs

from . import PACKAGE_NAME
from .format import ROOT, pinned

ASSETS = Path(__file__).parent / "assets"
SOURCE = ASSETS / "logo.src.svg"
LOGO = ASSETS / "logo.svg"
CONFIG = Path(__file__).with_name("logo.svgo.mjs")


def cache_path() -> Path:
    return platformdirs.user_cache_path(PACKAGE_NAME) / "logo.json"


def minify(source: Path) -> str:
    """What `svgo` makes of `source`."""
    result = subprocess.run(
        [
            pinned("npm:svgo", "svgo"),
            "--quiet",
            "--config",
            CONFIG,
            "--input",
            source,
            "--output",
            "-",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"svgo failed on {source}:\n{result.stderr.strip()}")
    return result.stdout


def write_logo(source: Path = SOURCE, logo: Path = LOGO, cache: Path | None = None) -> bool:
    """Write `logo` from `source`, saying whether that changed it.

    The key is the source, the configuration, and which `svgo`,
    whose path names its version: anything else the same, the answer is too.
    A cache that cannot be read or written is only a slower build.
    """
    cache = cache or cache_path()
    svgo = pinned("npm:svgo", "svgo")
    key = hashlib.sha256(source.read_bytes() + CONFIG.read_bytes() + svgo.encode()).hexdigest()
    cached: object
    try:
        cached = json.loads(cache.read_text())
    except OSError, ValueError:
        cached = None
    if isinstance(cached, dict) and cached.get("key") == key and isinstance(cached.get("svg"), str):
        svg = cached["svg"]
    else:
        svg = minify(source)
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"key": key, "svg": svg}))
        except OSError:
            pass
    if logo.exists() and logo.read_text() == svg:
        return False
    logo.write_text(svg)
    return True


def graphic_warning(logo: str) -> str:
    """What a graphic video shows until it is played: the logo beside "WARNING: Graphic Content".

    Laid out as ETA's own card for its videos, the logo on the dark blue it sits on,
    and made from the logo here, so an edit to the logo reaches it too.
    The words are text in the report's own type, `system-ui`:
    an SVG shown as a picture cannot use the page's fonts, only the reader's.
    """
    opening, _, rest = logo.partition(">")
    view_box = opening.split('viewBox="', 1)[1].split('"', 1)[0]
    drawing = rest.rsplit("</svg>", 1)[0]
    lines = [("WARNING:", 297), ("Graphic", 437), ("Content", 572)]
    text = "".join(f'<tspan x="835" y="{y}">{line}</tspan>' for line, y in lines)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1719 787">'
        '<rect width="1719" height="787" fill="#000516"/>'
        f'<svg x="316" y="147" width="487" height="487" viewBox="{view_box}">{drawing}</svg>'
        '<text fill="#fff" font-family="system-ui, sans-serif" font-size="128">'
        f"{text}</text></svg>\n"
    )
