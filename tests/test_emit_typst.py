"""Typst source, and that it actually compiles."""

import base64
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from shutil import copyfile, copytree

import pytest
from paths import FIXTURE_DIR, HOST
from pypdf import PdfReader

from eta_publish.emit.typst import TypstEmitter, breakable
from eta_publish.images import write_print_copies
from eta_publish.naming import IMAGE_DIR, PRINT_DIR
from eta_publish.nodes import Document
from eta_publish.parse import parse
from eta_publish.pdf import compile_pdf, install_template

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())
# A 1x1 PNG, so the figure path is exercised without checking in an asset.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def doc() -> Document:
    parsed = parse(FIXTURE)
    parsed.image_files["io.1"] = "sas-west-036.png"
    return parsed


@pytest.fixture
def out(doc: Document) -> str:
    return TypstEmitter(site_url=HOST).emit(doc)


def test_only_the_fields_something_renders_are_passed(out: str) -> None:
    """The header carries the private contributor list and the internal dates,
    and this file is committed."""
    assert "subtitle: " in out
    for private in ("Private Contributors", "Discussion Channel", "Draft Due Date"):
        assert private not in out
        assert private.replace(" ", "_") not in out


def test_a_field_name_cannot_be_typst_code(doc: Document) -> None:
    """A field name is written in the document, and was emitted as an argument name:
    `x:read("/etc/hostname"),y` was a call, not a field, and ran at build time."""
    doc.meta['x:read("/etc/hostname"),y'] = "z"
    assert "read(" not in TypstEmitter(site_url=HOST).emit(doc)


def _no_fonts(tmp_path: Path) -> Path:
    """A font directory with nothing in it, so a test downloads no font.

    `typst` sets the text in the next font the template names, or its own,
    which changes nothing a test here looks at.
    """
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    return fonts


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst is not installed")
def test_the_pdf_links_a_contributor_on_staff(doc: Document, tmp_path: Path) -> None:
    """The link survives into the PDF, and only for the name on staff."""
    doc.meta["Public Contributors"] = "Khyber Sen, Ada Lovelace"
    doc.staff = ("Blair Lorenzo", "Khyber Sen")
    original = tmp_path / IMAGE_DIR / "sas-west-036.png"
    original.parent.mkdir()
    original.write_bytes(PNG)
    write_print_copies({"kix.1": original}, tmp_path / PRINT_DIR)
    source = tmp_path / "report.typ"
    source.write_text(TypstEmitter(site_url=HOST).emit(doc))
    install_template(tmp_path)

    uris = [
        annot["/A"]["/URI"]
        for page in PdfReader(compile_pdf(source, _no_fonts(tmp_path))).pages
        for annot in (a.get_object() for a in page.get("/Annots", []))
        if "/A" in annot and "/URI" in annot["/A"]
    ]
    assert "https://www.etany.org/about-us#:~:text=Khyber%20Sen" in uris
    assert not any("Lovelace" in str(uri) for uri in uris)


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst is not installed")
def test_the_emitted_source_compiles(doc: Document, tmp_path: Path) -> None:
    """Escaping and syntax errors only show up here."""
    # `PRINT_DIR`, not `images/`: the PDF embeds the copies made for it,
    # and links the originals, which nothing has to open to compile.
    original = tmp_path / IMAGE_DIR / "sas-west-036.png"
    original.parent.mkdir()
    original.write_bytes(PNG)
    write_print_copies({"kix.1": original}, tmp_path / PRINT_DIR)
    source = tmp_path / "report.typ"
    source.write_text(TypstEmitter(site_url=HOST).emit(doc))
    install_template(tmp_path)

    pdf = compile_pdf(source, _no_fonts(tmp_path))
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")


def test_the_template_is_rewritten_every_build(tmp_path: Path) -> None:
    """An output directory is build output,
    so a change to the house style has to reach one that has been built before,
    which is all of them."""
    stale = tmp_path / "template.typ"
    stale.write_text("#let publication(..) = none  // an old house style\n")

    install_template(tmp_path)

    assert stale.read_text() != "#let publication(..) = none  // an old house style\n"
    assert "#show: doc" in stale.read_text() or "publication(" in stale.read_text()


def test_a_long_query_string_can_break_without_a_slash() -> None:
    """A source's address wraps at its query string's separators, not only at `/`,
    and adds no character to the text a reader copies out of the PDF."""
    assert breakable("oecd.org/vis?a=1&b=A%2BB") == (
        "#box[oecd.org/vis?]#box[a=]#box[1&]#box[b=]#box[A]#box[%2BB]"
    )
    assert breakable("oecd.org/vis") == "oecd.org/vis"


needs_typst = pytest.mark.skipif(shutil.which("typst") is None, reason="typst is not installed")


def counted_compiles(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every `typst compile` from here on, still run, so a test can count them."""
    import subprocess

    from eta_publish import pdf

    compiles: list[list[str]] = []
    run = subprocess.run

    def counting(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        if "compile" in command:
            compiles.append(command)
        return run(command, capture_output=capture_output, text=text, check=check)

    monkeypatch.setattr(pdf.subprocess, "run", counting)
    return compiles


def small_publication(directory: Path) -> Path:
    """A source that sets text and embeds a print copy, as a publication does."""
    (directory / PRINT_DIR).mkdir(parents=True)
    (directory / PRINT_DIR / "figure.png").write_bytes(PNG)
    source = directory / "report.typ"
    source.write_text('#import "template.typ": video_warning\nHello.\n#image("print/figure.png")\n')
    install_template(directory)
    return source


@needs_typst
def test_a_second_compile_of_unchanged_sources_does_not_run_typst(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The PDF the last compile made is kept, and is what is returned."""
    compiles = counted_compiles(monkeypatch)
    source = small_publication(tmp_path)
    fonts = _no_fonts(tmp_path)

    first = compile_pdf(source, fonts).read_bytes()
    assert compile_pdf(source, fonts).read_bytes() == first
    assert len(compiles) == 1


def change_the_source(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source.write_text(source.read_text() + "More.\n")


def change_the_template(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    template = source.parent / "template.typ"
    template.write_text(template.read_text() + "\n// edited\n")


def change_a_print_copy(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import Image as Pillow

    Pillow.new("RGB", (2, 2), "red").save(source.parent / PRINT_DIR / "figure.png")


def change_a_font(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fonts = source.parent.parent / "fonts"
    copyfile(fonts / "DejaVuSans.ttf", fonts / "DejaVuSans-Bold.ttf")


def change_typst(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eta_publish import pdf

    def another_release(typst: str) -> str:
        return "typst 99.0.0 (00000000)"

    monkeypatch.setattr(pdf, "_typst_version", another_release)


def set_a_typst_variable(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")


def replace_the_pdf(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source.with_suffix(".pdf").write_bytes(b"%PDF not the one compiled")


@needs_typst
@pytest.mark.parametrize(
    "change",
    [
        change_the_source,
        change_the_template,
        change_a_print_copy,
        change_a_font,
        change_typst,
        set_a_typst_variable,
        replace_the_pdf,
    ],
)
def test_a_change_to_anything_typst_reads_compiles_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[Path, pytest.MonkeyPatch], None],
) -> None:
    from eta_publish.fonts import fonts as cached_fonts

    # A copy of the fonts a build gets, which `change_a_font` can change.
    fonts = tmp_path / "fonts"
    copytree(cached_fonts(offline=True), fonts)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    compiles = counted_compiles(monkeypatch)
    source = small_publication(tmp_path / "publication")
    compile_pdf(source, fonts)

    change(source, monkeypatch)
    compiled = compile_pdf(source, fonts)

    assert len(compiles) == 2
    assert compiled.read_bytes().startswith(b"%PDF-")
    compile_pdf(source, fonts)
    assert len(compiles) == 2


@needs_typst
def test_a_compile_replaces_the_pdf_and_leaves_a_linked_copy_alone(tmp_path: Path) -> None:
    """The PDF may be a link to the last build's, which must keep what it was."""
    source = small_publication(tmp_path)
    fonts = _no_fonts(tmp_path)
    pdf = compile_pdf(source, fonts)
    last = tmp_path / "last build's.pdf"
    last.hardlink_to(pdf)
    before = last.read_bytes()

    source.write_text(source.read_text() + "More.\n")
    compile_pdf(source, fonts)

    assert last.read_bytes() == before
    assert pdf.stat().st_ino != last.stat().st_ino
