"""Compile the emitted Typst source into the publication PDF.

Typst is an external binary rather than a Python dependency, so this is best-effort:
if it is missing the `.typ` is still written and the build says what to install,
rather than failing everything for the sake of one output.
"""

import json
import os
import shutil
import subprocess
from functools import cache
from hashlib import file_digest
from os.path import relpath
from pathlib import Path
from tempfile import TemporaryDirectory, mkstemp
from typing import TypedDict

from .assets import read
from .build_cache import CacheKind, cache_bytes, cache_file, cached_path, link_cached, read_cached

TEMPLATE = "template.typ"

PDF_KIND: CacheKind = "pdfs"
"""The folder in `build_cache_dir` the PDFs are kept in,
with what each `typst` compile read.

Two files for each: one named by a `PdfKey`, which says what `typst` was given,
holding the names of the files it read, which the compile's `--deps` lists;
and the PDF, named by that key and a hash of each of those files.
So a compile given the same, whose files are still what they were, finds the PDF it would make,
and one whose files changed, or that has never been given the same, finds none.
That is safe because which files a compile reads follows from what it is given and what it read:
given the same source and finding the same bytes in each file it read,
`typst` reads the same files again.
"""


class PdfKey(TypedDict):
    """What `typst` is given to make a PDF from, before what it reads.

    Not the time it was made, which it writes into it:
    a PDF found under the key keeps the date of the build that made it.
    The fonts it sets the PDF in are the ones it is given and its own, never the machine's,
    so its version and the font files it is given stand for all of them.
    """

    typst: str
    """What `typst --version` says, the release and the commit it was built from."""
    args: list[str]
    """The arguments it was given, with the build's directory and the fonts' left out."""
    env: dict[str, str]
    """Each `$TYPST_*` variable, which can stand for an argument, and `$SOURCE_DATE_EPOCH`."""
    fonts: dict[str, str]
    """A hash of each file in the fonts directory it is given, by its path in there."""
    source: str
    """A hash of the source it compiles, which says what else it reads."""


class TypstMissing(RuntimeError):
    """`typst` is not installed, which costs the PDF and nothing else.

    Carries no sentence: see `compile_pdf`.
    """


def install_template(outdir: Path) -> Path:
    """Write the house style next to the emitted source, every build.

    A package asset rather than something the emitter writes,
    so editing how publications look means editing Typst rather than a Python string.

    Overwritten rather than kept, because an output directory is build output.
    Keeping an existing copy meant a change to the house style
    never reached a directory that had been built once,
    and the PDF compiled against a template several versions old without saying so.
    """
    dest = outdir / TEMPLATE
    dest.write_text(read(TEMPLATE), encoding="utf-8")
    return dest


def compile_pdf(source: Path, fonts: Path, dest: Path | None = None) -> Path:
    """Run `typst compile` on `source`, returning the PDF path.

    Unless some build already compiled what it would be compiled from now:
    then `typst` isn't run at all, and the PDF it made is linked from `build_cache_dir`,
    keeping the date that build gave it (see `PDF_KIND`).
    `fonts` is the directory of fonts it is set in besides `typst`'s own,
    which a build gets from `fonts.fonts`.
    """
    typst = shutil.which("typst")
    if typst is None:
        # Nothing said here: what a build does about a missing `typst` is print
        # a sentence, and that sentence is written where it is printed, in
        # `build_pdf`, so the command and the URL in it are given to the log as
        # the values they are rather than spelled into a string.
        raise TypstMissing("typst")
    dest = dest or source.with_suffix(".pdf")
    root = source.parent.resolve()
    relative = relpath(dest.resolve(), root)
    key = PdfKey(
        typst=_typst_version(typst),
        args=_arguments("<root>", "<fonts>", "<deps>", source.name, relative),
        env={
            name: value
            for name, value in sorted(os.environ.items())
            if name.startswith("TYPST_") or name == "SOURCE_DATE_EPOCH"
        },
        fonts={
            path.relative_to(fonts).as_posix(): _hash(path)
            for path in sorted(fonts.rglob("*"))
            if path.is_file()
        },
        source=_hash(source),
    )
    given = json.dumps(key, sort_keys=True)
    listed = cached_path(PDF_KIND, given, ".json")
    names = _names(read_cached(listed))
    if names is not None:
        try:
            inputs = {name: _hash(root / name) for name in names}
        except OSError:
            inputs = None
        if inputs is not None and link_cached(_compiled(given, inputs), dest):
            return dest
    # A PDF compiled from other sources is not this build's,
    # and a compile that fails should leave none, as it does in a fresh directory.
    dest.unlink(missing_ok=True)
    with TemporaryDirectory() as scratch:
        deps = Path(scratch) / "deps.json"
        # Written beside `dest` and put in its place once whole,
        # so a compile stopped partway leaves no PDF to be kept or linked.
        handle, written = mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".pdf")
        os.close(handle)
        try:
            # Set only in the fonts in `fonts` and those built into `typst`,
            # never the machine's, so every machine sets the same PDF.
            result = subprocess.run(
                [
                    typst,
                    *_arguments(str(root), str(fonts), str(deps), str(source.resolve()), written),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"typst compile failed:\n{result.stderr.strip()}")
            os.replace(written, dest)
        finally:
            Path(written).unlink(missing_ok=True)
        try:
            listed_deps: object = json.loads(deps.read_text())
        except OSError, ValueError:
            listed_deps = None
    read_paths = _strings(listed_deps.get("inputs")) if isinstance(listed_deps, dict) else None
    if read_paths is None:
        # Not kept, so the next build compiles it again rather than trust a guess.
        return dest
    inputs = {
        _input_name(Path(path).resolve(), root): _hash(Path(path)) for path in sorted(read_paths)
    }
    cache_bytes(listed, (json.dumps(sorted(inputs), indent=2) + "\n").encode())
    cache_file(_compiled(given, inputs), dest)
    return dest


def _compiled(given: str, inputs: dict[str, str]) -> Path:
    """Where the PDF compiled from what `given` says, reading `inputs`, is kept."""
    return cached_path(PDF_KIND, json.dumps([given, inputs], sort_keys=True), ".pdf")


def _names(data: bytes | None) -> list[str] | None:
    """The names of the files a compile read, as `compile_pdf` keeps them; `None` if unreadable."""
    if data is None:
        return None
    try:
        return _strings(json.loads(data))
    except ValueError:
        return None


def _arguments(root: str, fonts: str, deps: str, source: str, output: str) -> list[str]:
    """The arguments to `typst`, built the same way for the key as for the compile."""
    return [
        "compile",
        "--root",
        root,
        "--font-path",
        fonts,
        "--ignore-system-fonts",
        "--deps",
        deps,
        source,
        output,
    ]


@cache
def _typst_version(typst: str) -> str:
    """What `typst --version` says, asked once a run."""
    result = subprocess.run([typst, "--version"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _hash(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def _input_name(path: Path, root: Path) -> str:
    """`path` as a key names it: relative to `root`, so a build elsewhere matches it."""
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _strings(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    strings = [item for item in value if isinstance(item, str)]
    return strings if len(strings) == len(value) else None
