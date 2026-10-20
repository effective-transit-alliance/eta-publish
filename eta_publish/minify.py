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

MIN_ASSETS = ("report.min.css", "report.min.js")
"""What `assets` writes, each with its source map beside it as `<name>.map`."""


def min_name(name: str) -> str:
    """`report.min.html` for `report.html`, and the same for any file name."""
    stem, dot, suffix = name.rpartition(".")
    return f"{stem}.min{dot}{suffix}"


def assets(directory: Path) -> list[Path]:
    """Write `report.min.css` and `report.min.js` beside `report.css` and `report.js`,
    with their source maps, returning what was written."""
    _run(
        [
            pinned("npm:esbuild", "esbuild"),
            "report.css",
            "--minify",
            "--sourcemap",
            "--sources-content=true",
            "--log-level=warning",
            "--outfile=report.min.css",
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
    return [directory / f for name in MIN_ASSETS for f in (name, f"{name}.map")]


def page(source: Path, asset_base: str) -> Path:
    """Write `source` minified beside it, linking the `.min` assets at `asset_base`.

    A page that does not link each of `report.css` and `report.js` there exactly once
    is refused rather than written still linking the unminified ones,
    which would only look like it worked.
    """
    html = source.read_text()
    for name in ("report.css", "report.js"):
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
