"""Typst source, and that it actually compiles."""

import base64
import json
import shutil
from pathlib import Path

import pytest
from paths import FIXTURE_DIR

from eta_publish.emit.typst import TypstEmitter
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
    return TypstEmitter().emit(doc)


def test_footnote_bodies_are_inlined_at_the_reference(out: str) -> None:
    """Typst numbers and places footnotes itself,
    so there is no separate list that can fall out of sync with the references."""
    assert "#footnote[Inflation-adjusted from the 2024 capital plan.]" in out
    assert "#footnote[Measured from street level to platform.]" in out


def test_headings_map_to_typst_depth(out: str) -> None:
    assert "\n= The Elephants in the Room" in out
    assert "\n== Ground Conditions" in out


def test_the_source_line_is_not_emitted(out: str) -> None:
    # The `Source:` line names `sas-west-036.jpg` and the download wrote a
    # `.png`, so the written name is the only one either path may use.
    # `print/sas-west-036.jpg` is not that name reappearing: it is the `.png`
    # re-encoded for the PDF, which is a JPEG and has to say so.
    assert "images/sas-west-036.jpg" not in out
    assert "Source:" not in out


def test_figures_carry_caption_and_credit(out: str) -> None:
    assert 'capped_image("print/sas-west-036.jpg", alt: "SAS West alignment map")' in out
    assert '/images/sas-west-036.png")[#capped_image(' in out
    assert "The SAS West and Phase 2 alignments." in out
    assert "Credit: MTA" in out
    assert "#emph[Credit: MTA]" not in out


def test_markup_characters_in_prose_are_escaped(out: str) -> None:
    """`$` starts math mode in Typst, so an unescaped price breaks the build."""
    assert r"\$7.7 billion" in out


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
    assert "read(" not in TypstEmitter().emit(doc)


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
    source.write_text(TypstEmitter().emit(doc))
    install_template(tmp_path)

    pdf = compile_pdf(source)
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")


def test_tables_declare_their_column_count(out: str) -> None:
    assert "#table(\n  columns: 2," in out
    assert "[Grand Paris Express]," in out
    # `$` opens math mode, so a currency figure in a cell needs escaping too.
    assert r"[\$530M]," in out


def test_the_template_is_rewritten_every_build(tmp_path: Path) -> None:
    """An output directory is build output,
    so a change to the house style has to reach one that has been built before,
    which is all of them."""
    stale = tmp_path / "template.typ"
    stale.write_text("#let report(..) = none  // an old house style\n")

    install_template(tmp_path)

    assert stale.read_text() != "#let report(..) = none  // an old house style\n"
    assert "#show: doc" in stale.read_text() or "report(" in stale.read_text()
