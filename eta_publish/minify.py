"""The `.min` copies of what a build wrote: smaller to paste and to serve, and drawn the same.

`report.min.html` is `report.html` minified, linking `report.min.css` and `report.min.js`
where `report.html` links `report.css` and `report.js`.
It is the one to paste into a Squarespace code block: a fifth to a quarter smaller,
which is that much further under the code block's limit and that much less for the editor to save.

None of it is committed. The formatted files are what a diff reviews,
and these are made from them by tools that `mise.toml` pins, on every build,
locally and on GitHub Pages alike.

`minhtml` for the page, which drops a space between two tags only where it draws nothing.
`esbuild` for the stylesheet, and `swc` for the script, as `report.swcrc` says.
Each writes a source map carrying the file as written,
so a browser's tools show the stylesheet and the script with their comments.
Run from the directory the files are in and given their bare names,
so the maps name them that way rather than by where the build happened to run.
"""

import subprocess
from pathlib import Path

from .format import pinned

SWC_CONFIG = Path(__file__).with_name("report.swcrc")

FRAGMENT_ASSETS = ("report.css", "report.js")
"""What `report.html` links, and so what `report.min.html` links the `.min` copies of."""

PAGE_ASSETS = ("page.css", *FRAGMENT_ASSETS)
"""What a report's `index.html` links."""

MIN_ASSETS = ("report.min.css", "report.min.js")
"""What `report.min.html` links, each with its source map beside it as `<name>.map`."""


def min_name(name: str) -> str:
    """`report.min.html` for `report.html`, and the same for any file name."""
    stem, dot, suffix = name.rpartition(".")
    return f"{stem}.min{dot}{suffix}"


def is_min(name: str) -> bool:
    """Whether `name` is one of the `.min` copies, which a glob for the originals also finds."""
    return ".min." in name


def assets(directory: Path) -> list[Path]:
    """Write the `.min` copy of each of `PAGE_ASSETS` beside it,
    with its source map, returning what was written."""
    for css in ("page.css", "report.css"):
        _run(
            [
                pinned("npm:esbuild", "esbuild"),
                css,
                "--minify",
                "--sourcemap",
                "--sources-content=true",
                "--log-level=warning",
                f"--outfile={min_name(css)}",
            ],
            directory,
        )
    _run(
        [
            pinned("github:swc-project/swc", "swc"),
            "compile",
            "--config-file",
            str(SWC_CONFIG),
            "--out-file",
            "report.min.js",
            "report.js",
        ],
        directory,
    )
    names = [min_name(name) for name in PAGE_ASSETS]
    return [directory / f for name in names for f in (name, f"{name}.map")]


def page(source: Path, asset_base: str, linked: tuple[str, ...] = FRAGMENT_ASSETS) -> Path:
    """Write `source` minified beside it, linking the `.min` copies of `linked` at `asset_base`.

    A page that does not link each of them there exactly once
    is refused rather than written still linking the unminified ones,
    which would only look like it worked.
    """
    html = source.read_text()
    for name in linked:
        href = f'"{asset_base}/{name}"'
        if html.count(href) != 1:
            raise RuntimeError(
                f"{source.name} links {href} {html.count(href)} times rather than once, "
                "so it has no minified copy"
            )
        html = html.replace(href, f'"{asset_base}/{min_name(name)}"')
    dest = source.with_name(min_name(source.name))
    _run(
        [
            pinned("github:wilsonzlin/minify-html", "minhtml"),
            # Neither is the one to leave out, for a fragment that is pasted into a page
            # that has its own `<html>` and `<head>`, or anywhere else.
            "--keep-closing-tags",
            "--keep-html-and-head-opening-tags",
            "--output",
            dest.name,
        ],
        source.parent,
        stdin=html,
    )
    return dest


def _run(args: list[str], cwd: Path, stdin: str | None = None) -> None:
    result = subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{Path(args[0]).name} failed in {cwd}:\n{result.stderr.strip()}")
