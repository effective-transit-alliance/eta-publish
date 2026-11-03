"""Markdown emitted for the committed archive."""

import json

import pytest
from paths import FIXTURE_DIR, named_images

from eta_publish.docs_json import JsonObject
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.nodes import Document, Text
from eta_publish.parse import parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


@pytest.fixture
def doc() -> Document:
    return named_images(parse(FIXTURE))


@pytest.fixture
def out(doc: Document) -> str:
    return MarkdownEmitter().emit(doc)


def with_paragraph(text: str) -> Document:
    doc_json: JsonObject = json.loads(json.dumps(FIXTURE))
    doc_json["body"]["content"].append(
        {
            "paragraph": {
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "elements": [{"textRun": {"content": text + "\n", "textStyle": {}}}],
            }
        }
    )
    return named_images(parse(doc_json))


def test_it_opens_the_way_the_page_does(out: str) -> None:
    """The same publication as the page and the PDF, not a different view of it."""
    assert out.startswith("# Digging Out of a Very Deep Hole: Saving Billions on 125th Street\n")


def test_the_header_block_is_not_in_the_archive(out: str) -> None:
    """It is production scaffolding,
    and `doc.json` beside this file keeps every field of it verbatim."""
    assert not out.startswith("---")
    assert "draft due date" not in out.lower()
    assert "url: /reports/" not in out
    assert "seo description" not in out.lower()


def test_a_paragraph_is_one_line_per_sentence() -> None:
    """The whole reason this file exists:
    a one-word fix must be a one-line diff,
    not a whole paragraph reported as changed."""
    text = "First sentence here. Second sentence here. Third sentence here."
    out = MarkdownEmitter().emit(with_paragraph(text))
    assert "First sentence here.\nSecond sentence here.\nThird sentence here." in out


def test_editing_one_sentence_changes_one_line() -> None:
    before = MarkdownEmitter().emit(with_paragraph("Alpha one. Beta two. Gamma three."))
    after = MarkdownEmitter().emit(with_paragraph("Alpha one. Beta TWO. Gamma three."))
    changed = [
        (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b
    ]
    assert changed == [("Beta two.", "Beta TWO.")]


def test_headings_carry_no_explicit_anchor(out: str) -> None:
    """Pandoc's `{#anchor}` syntax renders as literal text inside the heading on GitHub,
    which is where this file is read,
    and the anchor is a property of the HTML rather than of the archive."""
    assert "## The Elephants in the Room\n" in out
    assert "{#" not in out


def test_superscript_uses_html_that_both_renderers_accept(out: str) -> None:
    """GitHub renders Pandoc's `^x^` literally and `~x~` as strikethrough,
    which is wrong rather than merely ugly.
    Both accept the HTML."""
    from eta_publish.emit.markdown import MarkdownEmitter
    from eta_publish.nodes import Document, Paragraph, Text

    doc = Document(blocks=[Paragraph([Text("2", sup=True), Text("2", sub=True)])])
    emitted = MarkdownEmitter().emit(doc)
    assert "<sup>2</sup>" in emitted
    assert "<sub>2</sub>" in emitted


def test_footnotes_use_pandoc_syntax(out: str) -> None:
    assert "[^1]" in out
    assert "[^1]: Inflation-adjusted from the 2024 capital plan." in out


def test_the_archive_keeps_the_source_line_as_a_comment(out: str) -> None:
    """Unlike the published outputs:
    it records which file in Drive an image came from,
    which is provenance worth keeping in a durable record."""
    assert "<!-- Source: sas-west-036.jpg -->" in out


def test_figures_carry_caption_and_credit(out: str) -> None:
    assert "![SAS West alignment map](<images/sas-west-036.png>)" in out
    assert "The SAS West and Phase 2 alignments." in out
    assert "Credit: MTA" in out
    # Not italicized: the live publication does not italicize either.
    assert "*Credit: MTA*" not in out


def test_nested_lists_indent(out: str) -> None:
    assert "- First point\n  - Nested point\n- Second point" in out


def test_markdown_syntax_in_prose_is_escaped() -> None:
    out = MarkdownEmitter().emit(with_paragraph("A [bracket] and an *asterisk*."))
    assert r"\[bracket\]" in out
    assert r"\*asterisk\*" in out


def test_a_url_containing_parentheses_survives() -> None:
    """A bare `)` would end the link early and drop the rest into the prose.
    These publications cite Wikipedia and agency PDFs, which have plenty."""
    doc_json: JsonObject = json.loads(json.dumps(FIXTURE))
    href = "https://en.wikipedia.org/wiki/Second_Avenue_Subway_(Phase_2)"
    doc_json["body"]["content"].append(
        {
            "paragraph": {
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "elements": [
                    {"textRun": {"content": "see here\n", "textStyle": {"link": {"url": href}}}}
                ],
            }
        }
    )
    out = MarkdownEmitter().emit(named_images(parse(doc_json)))
    assert f"[see here](<{href}>)" in out


def test_a_pipe_in_prose_is_escaped() -> None:
    """Unescaped, it would split a table row."""
    out = MarkdownEmitter().emit(with_paragraph("Costs a | b compared."))
    assert r"\|" in out


def test_tables_render_with_a_header_row(out: str) -> None:
    """Markdown requires one,
    so the first row serves whether or not the doc meant it as a header."""
    assert "| **Project** | **Cost per mile** |" in out
    assert "| --- | --- |" in out
    assert "| Grand Paris Express | $530M |" in out


def test_a_caption_is_a_line_of_its_own() -> None:
    """A bare newline is a soft break, which renders as a space:
    the picture, its caption and its credit came out as one running line."""
    doc = named_images(parse(FIXTURE))
    doc.image_files["io.1"] = "sas-west-036.png"
    out = MarkdownEmitter().emit(doc)
    picture = next(line for line in out.splitlines() if line.startswith("!["))
    assert picture.endswith("\\")


def test_a_value_holding_a_backtick_is_still_one_span() -> None:
    """The failure the pieces exist to prevent: marked-up text put through a
    parser re-paired its spans around a value it did not control."""
    from eta_publish.emit.markdown import fence
    from eta_publish.nodes import Document, Shown

    doc = Document()
    doc.warn("using {} and ignoring {}", Shown("a ` b"), Shown("c"))
    rendered = MarkdownEmitter().warnings(doc)
    assert "using ``a ` b`` and ignoring `c`" in rendered
    assert fence("`leading") == "`` `leading ``"
    assert fence("plain") == "`plain`"


@pytest.mark.parametrize(
    ("run", "written"),
    [
        # A `**` after a space cannot close, so this would print its asterisks.
        (Text(text="on August 21, 2026: ", bold=True), "**on August 21, 2026:** "),
        (Text(text=" stressed", italic=True), " *stressed*"),
        (Text(text=" both ", bold=True, italic=True), " ***both*** "),
        (Text(text="saving ", href="https://a.example/"), "[saving](<https://a.example/>) "),
        (Text(text=" ", bold=True), " "),
        (Text(text=" plain "), " plain "),
    ],
)
def test_edge_whitespace_goes_outside_the_markers(run: Text, written: str) -> None:
    assert MarkdownEmitter().text(run) == written
