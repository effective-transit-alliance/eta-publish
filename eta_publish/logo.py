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
