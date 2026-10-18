"""Byte-for-byte comparison against committed output.

`emit(doc) == emit(doc)` in one process proves nothing:
hash randomization is per-interpreter,
so anything order- or hash-dependent still matches itself.
A committed file compares across runs,
and doubles as the diff that shows what a parser change actually did to the output.

The snapshots sit in `tests/fixture/reports/<slug>/`,
beside the `doc.json` they are emitted from,
which is the same shape as `site/unpublished/`:
a report directory holding a document and what it produces.

Regenerate with `pytest --regenerate-snapshots` after checking the diff.
"""

import json

import pytest
from paths import FIXTURE_DIR

from eta_publish.emit.html import HtmlEmitter, report_page
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.emit.typst import TypstEmitter
from eta_publish.naming import IMAGE_DIR
from eta_publish.nodes import Document
from eta_publish.parse import parse

ASSET_BASE = "../../assets"
"""What a build links from a report at `reports/<slug>/`."""

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


@pytest.fixture
def doc() -> Document:
    parsed = parse(FIXTURE)
    parsed.image_files["io.1"] = "sas-west-036.png"
    return parsed


def check(name: str, actual: str, regenerate: bool) -> None:
    path = FIXTURE_DIR / name
    if regenerate or not path.exists():
        path.write_text(actual)
        if not regenerate:
            pytest.fail(f"{path} did not exist; wrote it, review and commit")
        return
    assert actual == path.read_text(), (
        f"{path} differs; review the change and rerun with --regenerate-snapshots"
    )


def test_html_matches_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    # The emitter's defaults,
    # so the snapshot is what a build of this document writes
    # rather than a shape only this test produces.
    # Pointing the images somewhere else is covered in `test_emit_html.py`.
    check("report.html", HtmlEmitter(image_base=IMAGE_DIR).emit(doc), regenerate_snapshots)


def test_markdown_matches_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    check("report.md", MarkdownEmitter().emit(doc), regenerate_snapshots)


def test_typst_matches_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    check("report.typ", TypstEmitter().emit(doc), regenerate_snapshots)


def test_page_matches_snapshot(doc: Document, regenerate_snapshots: bool) -> None:
    """Snapshotted for the same reason as the rest:
    it is one of the files a build writes,
    and leaving it out would make this directory something a build cannot reproduce."""
    check("index.html", report_page(doc, asset_base=ASSET_BASE), regenerate_snapshots)
