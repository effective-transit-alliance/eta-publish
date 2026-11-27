"""Markdown emitted for the committed archive."""

import json

import pytest
from paths import FIXTURE_DIR, named_images

from eta_publish.docs_json import JsonObject
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.nodes import Document, Inline, Paragraph, Text
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


@pytest.mark.parametrize("gap", [" ", "  "])
def test_editing_one_sentence_changes_one_line(gap: str) -> None:
    """The whole reason this file exists:
    a one-word fix must be a one-line diff,
    not a whole paragraph reported as changed.
    Two spaces after a sentence still split it."""
    before = MarkdownEmitter().emit(with_paragraph(f"Alpha one.{gap}Beta two.{gap}Gamma three."))
    after = MarkdownEmitter().emit(with_paragraph(f"Alpha one.{gap}Beta TWO.{gap}Gamma three."))
    changed = [
        (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b
    ]
    assert changed == [("Beta two.", "Beta TWO.")]


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


def test_markdown_syntax_in_prose_is_escaped(doc: Document) -> None:
    href = "https://en.wikipedia.org/wiki/Second_Avenue_Subway_(Phase_2)"
    runs: list[Inline] = [
        Text(text="A [bracket] and an *asterisk*, costing a | b, see "),
        Text(text="here", href=href),
    ]
    doc.blocks.append(Paragraph(runs))
    # A bare `)` in an address would end the link early and drop the rest into the prose,
    # and these publications cite Wikipedia and agency PDFs, which have plenty.
    # Likewise a figure whose file name has parentheses or a space.
    doc.image_files["io.1"] = "Bus (disambiguation).png"
    out = MarkdownEmitter().emit(doc)
    assert r"\[bracket\]" in out
    assert r"\*asterisk\*" in out
    assert r"a \| b" in out, "unescaped, it would split a table row"
    assert f"[here](<{href}>)" in out
    assert "(<images/Bus (disambiguation).png>)" in out


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
    from eta_publish.nodes import Document, Shown

    doc = Document()
    doc.warn("using {} and ignoring {}", Shown("a ` b"), Shown("c"))
    rendered = MarkdownEmitter().warnings(doc)
    assert "using ``a ` b`` and ignoring `c`" in rendered


@pytest.mark.parametrize(
    ("runs", "written"),
    [
        # A `**` after a space cannot close, so this would print its asterisks.
        ([Text(text="on August 21, 2026: ", bold=True)], "**on August 21, 2026:** "),
        ([Text(text=" stressed", italic=True)], " _stressed_"),
        ([Text(text=" both ", bold=True, italic=True)], " _**both**_ "),
        ([Text(text="saving ", href="https://a.example/")], "[saving](<https://a.example/>) "),
        ([Text(text=" ", bold=True)], " "),
        ([Text(text=" plain ")], " plain "),
        # `_` is what `biome` writes, but it neither opens nor closes inside a word.
        (
            [Text(text="un"), Text(text="frigging", italic=True), Text(text="believable")],
            "un*frigging*believable",
        ),
        ([Text(text="a_b", italic=True)], "*a\\_b*"),
        (
            [Text(text="see "), Text(text="this", italic=True), Text(text=".")],
            "see _this_.",
        ),
    ],
)
def test_edge_whitespace_goes_outside_the_markers(runs: list[Inline], written: str) -> None:
    assert MarkdownEmitter().inlines(runs) == written
