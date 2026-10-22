"""Compile the emitted Typst source into the publication PDF.

Typst is an external binary rather than a Python dependency, so this is best-effort:
if it is missing the `.typ` is still written and the build says what to install,
rather than failing everything for the sake of one output.
"""

import shutil
import subprocess
from pathlib import Path

from .assets import read

TEMPLATE = "template.typ"


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


def compile_pdf(source: Path, dest: Path | None = None) -> Path:
    """Run `typst compile` on `source`, returning the PDF path."""
    typst = shutil.which("typst")
    if typst is None:
        # Nothing said here: what a build does about a missing `typst` is print
        # a sentence, and that sentence is written where it is printed, in
        # `build_pdf`, so the command and the URL in it are given to the log as
        # the values they are rather than spelled into a string.
        raise TypstMissing("typst")
    dest = dest or source.with_suffix(".pdf")
    result = subprocess.run(
        [typst, "compile", "--root", str(source.parent), str(source), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"typst compile failed:\n{result.stderr.strip()}")
    return dest
