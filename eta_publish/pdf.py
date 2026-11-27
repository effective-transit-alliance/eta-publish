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
from .naming import PRINT_DIR, replace_bytes

TEMPLATE = "template.typ"

PDF_RECORD = f"{PRINT_DIR}/pdfs.json"
"""What each PDF in a directory was compiled from, kept in `PRINT_DIR` beside what they print.

Not committed, like the PDFs and that folder,
and in the folder rather than beside the PDFs because it is already ignored,
by `eta-drafts` as well, whose commits take every other file a build writes.
Maps each PDF's file name to a `PdfEntry`,
so a rebuild that changed nothing `typst` reads does not compile it again,
and `carry_over` links it into a build's own directory with the PDFs it names.
"""


class PdfKey(TypedDict):
    """Everything `typst` makes a PDF from, but the time it was made, which it writes into it.

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
    inputs: dict[str, str]
    """A hash of each file `typst` read, by its path in the build's directory.

    The files `--deps` listed: the source, the template, and the pictures,
    any of which may name others, so the list is the last compile's rather than one worked out here.
    If none of them changed, a compile reads the same files again and makes the same PDF.
    """


class PdfEntry(TypedDict):
    """What one PDF was compiled from, and a hash of the PDF, so a PDF replaced since is noticed."""

    key: PdfKey
    pdf: str


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

    Unless the PDF there was compiled from what it would be compiled from now:
    `PDF_RECORD` says what that was, and then `typst` isn't run at all,
    so the PDF keeps the date the last build gave it.
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
    record = dest.parent / PDF_RECORD
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
        inputs={},
    )
    last = read_pdf_record(record).get(dest.name)
    if last is not None and _still_made_from(last, key, root, dest):
        return dest
    # Forgotten before the PDF is touched, so a build stopped from here on
    # leaves no record naming a PDF it doesn't describe.
    _forget(record, dest.name)
    # And the PDF goes too: one compiled from other sources is not this build's,
    # and a compile that fails should leave none, as it does in a fresh directory.
    dest.unlink(missing_ok=True)
    with TemporaryDirectory() as scratch:
        deps = Path(scratch) / "deps.json"
        # Written beside `dest` and put in its place, never written over it,
        # since `dest` may be a link to the last build's PDF.
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
            listed: object = json.loads(deps.read_text())
        except OSError, ValueError:
            listed = None
    read_paths = _strings(listed.get("inputs")) if isinstance(listed, dict) else None
    if read_paths is None:
        # Not recorded, so the next build compiles it again rather than trust a guess.
        return dest
    key["inputs"] = {
        _input_name(Path(path).resolve(), root): _hash(Path(path)) for path in sorted(read_paths)
    }
    _remember(record, dest.name, PdfEntry(key=key, pdf=_hash(dest)))
    return dest


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
    """`path` as the record names it: relative to `root`, so a build elsewhere matches it."""
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _still_made_from(entry: PdfEntry, key: PdfKey, root: Path, dest: Path) -> bool:
    """Whether `dest` is still what `entry` says, and would be made again the same way."""
    last = entry["key"]
    if [last["typst"], last["args"], last["env"], last["fonts"]] != [
        key["typst"],
        key["args"],
        key["env"],
        key["fonts"],
    ]:
        return False
    try:
        if any(_hash(root / name) != digest for name, digest in last["inputs"].items()):
            return False
        return _hash(dest) == entry["pdf"]
    except OSError:
        return False


def read_pdf_record(path: Path) -> dict[str, PdfEntry]:
    """The record `_remember` writes, without any entry not of its shape; empty if unreadable."""
    try:
        recorded: object = json.loads(path.read_text())
    except OSError, ValueError:
        return {}
    if not isinstance(recorded, dict):
        return {}
    record: dict[str, PdfEntry] = {}
    for name, value in recorded.items():
        entry = _entry(value)
        if isinstance(name, str) and entry is not None:
            record[name] = entry
    return record


def _entry(value: object) -> PdfEntry | None:
    if not isinstance(value, dict):
        return None
    key = value.get("key")
    pdf = value.get("pdf")
    if not isinstance(key, dict) or not isinstance(pdf, str):
        return None
    typst = key.get("typst")
    args = _strings(key.get("args"))
    env = _string_map(key.get("env"))
    fonts = _string_map(key.get("fonts"))
    inputs = _string_map(key.get("inputs"))
    if not isinstance(typst, str) or args is None or env is None or fonts is None:
        return None
    if inputs is None:
        return None
    return PdfEntry(
        key=PdfKey(typst=typst, args=args, env=env, fonts=fonts, inputs=inputs), pdf=pdf
    )


def _strings(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    strings = [item for item in value if isinstance(item, str)]
    return strings if len(strings) == len(value) else None


def _string_map(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    pairs = {
        name: item
        for name, item in value.items()
        if isinstance(name, str) and isinstance(item, str)
    }
    return pairs if len(pairs) == len(value) else None


def _forget(record: Path, name: str) -> None:
    entries = read_pdf_record(record)
    if entries.pop(name, None) is not None:
        _write_record(record, entries)


def _remember(record: Path, name: str, entry: PdfEntry) -> None:
    _write_record(record, {**read_pdf_record(record), name: entry})


def _write_record(record: Path, entries: dict[str, PdfEntry]) -> None:
    """Replace the record, never rewrite it: it may be a link to the last build's."""
    data = json.dumps(dict(sorted(entries.items())), indent=2) + "\n"
    replace_bytes(record, data.encode())
