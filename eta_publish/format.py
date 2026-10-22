"""Lay out and check what a build wrote: the HTML, the CSS, the JavaScript.

The emitter's job is what the page says; this is where it sits on the line.
What is emitted is committed and read as a diff, and a paragraph on one line
reports a corrected word as a changed paragraph.

One entry point, `tree`, over the finished output directory.

`biome` rather than a formatter written here: whether a line break is safe
in HTML is a question about which elements are inline, and getting it wrong
welds two words together on the page. A stylesheet and a script embedded in
the page are formatted as a stylesheet and a script, which no HTML-only
formatter does.
"""

import subprocess
from functools import cache
from pathlib import Path

# `mise` reads the pin from the nearest `mise.toml`, which is this one,
# whatever directory the build was started from.
ROOT = Path(__file__).parent.parent


class MiseMissing(RuntimeError):
    pass


def biome() -> str:
    """The `biome` that `mise.toml` pins.

    Through `mise` rather than off `PATH`, so that pin is the only answer to
    which version runs. The output is committed, and a different `biome`
    would rewrite every publication without a publication having changed, which
    `check-committed-site.sh` would report as the documents changing.
    """
    return pinned("biome", "biome")


@cache
def pinned(tool: str, binary: str) -> str:
    """Where the `binary` of `tool`, at the version `mise.toml` pins, is.

    Asked once, and for the path rather than by running `mise x` per call:
    `mise` re-reads the pin every time it is asked.

    Installed first if it is not there yet, which is what `mise x` would have
    done on its own.
    """
    try:
        path = _mise("which", binary)
    except MiseMissing:
        _mise("install", tool)
        path = _mise("which", binary)
    return path


@cache
def installed(tool: str) -> str:
    """Where `tool`, at the version `mise.toml` pins, is installed:
    for a library with no binary to ask `pinned` about, such as an npm package used from Node.
    """
    try:
        path = _mise("where", tool)
    except MiseMissing:
        _mise("install", tool)
        path = _mise("where", tool)
    return path


def _mise(*args: str) -> str:
    """What `mise` printed, or `MiseMissing` saying what it said instead."""
    try:
        result = subprocess.run(
            ["mise", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise MiseMissing(
            "`mise` is not on PATH, so the tools `mise.toml` pins could not be found. "
            "Install it from https://mise.jdx.dev, then rerun."
        ) from e
    if result.returncode != 0:
        raise MiseMissing(f"`mise {' '.join(args)}` failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


class LintFailed(RuntimeError):
    pass


def tree(root: Path) -> None:
    """Lay out and check everything under `root` that `biome` reads.

    One run over the whole build rather than one per file: `biome` spends
    about 30ms opening a workspace before it has looked at a file, and 20ms
    laying out all of the HTML here.
    It lays out the saved API responses too, which changes how
    they are punctuated and not what they say.

    Once, not until it settles. `biome` is not idempotent on HTML: run
    over its own output, 2.3.14 broke a handful of `<a href="...">` tags it had
    just fitted onto one line, and 2.5.15 breaks the line after a `<code>` or `<em>`
    that it had just joined to the next word, a few dozen places in these publications.
    That is a bug in the formatter, and chasing it costs a whole further invocation to find out
    nothing is left, on a build where a run of `biome` is mostly the fixed
    cost of starting one.

    Taking the first result is still reproducible, which is what matters here:
    every build formats freshly emitted output, and nothing ever formats what
    is already committed, so one pass over the same input writes the same
    bytes as it did last time.
    """
    result = subprocess.run(
        [
            biome(),
            "format",
            "--write",
            # HTML formatting is off by default in this version.
            "--html-formatter-enabled=true",
            # `biome` indents with tabs; the stylesheets and the script in
            # `assets/` are already written with spaces.
            "--indent-style=space",
            # Every space in the prose is one somebody typed, so none of them
            # move.
            #
            # The default breaks a long line where it judges the rendering
            # would not notice, which was wrong for a footnote reference:
            # `biome` 2.3.14 broke between a sentence and the `<sup>` welded to
            # its full stop, and that newline renders as a space between the two.
            # 2.5.15 no longer does, but the judgment is still the formatter's,
            # and under `strict` it moves nothing. The markup is uglier where a
            # line has to wrap mid-tag; the page is correct, and the page is
            # what publishes.
            "--html-formatter-whitespace-sensitivity=strict",
            root,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"biome format failed:\n{result.stderr.strip()}")
    result = subprocess.run(
        [biome(), "lint", "--error-on-warnings", root],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise LintFailed(f"biome lint failed:\n{result.stderr.strip()}")
