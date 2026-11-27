"""Typst source, and that it actually compiles."""

import base64
import json
import shutil
from pathlib import Path

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
        for page in PdfReader(compile_pdf(source)).pages
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

    pdf = compile_pdf(source)
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
