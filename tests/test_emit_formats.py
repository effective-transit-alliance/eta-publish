"""What the three outputs say alike: the page, the archive, and the PDF source."""

import json

import pytest
from paths import FIXTURE_DIR, HOST, named_images

from eta_publish.emit.base import Emitter
from eta_publish.emit.html import HtmlEmitter
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.emit.typst import TypstEmitter
from eta_publish.nodes import Document, Inline, Paragraph, Text
from eta_publish.parse import parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())

ABOUT = "https://www.etany.org/about-us#:~:text=Khyber%20Sen"

STAFF_LINKED = [
    pytest.param(
        HtmlEmitter(inline_css=False, site_url=HOST),
        f'<li>Ada Lovelace</li>\n<li><a href="{ABOUT}">Khyber Sen</a></li>',
        id="html",
    ),
    pytest.param(MarkdownEmitter(), f"- Ada Lovelace\n- [Khyber Sen](<{ABOUT}>)", id="markdown"),
    pytest.param(
        TypstEmitter(site_url=HOST),
        f'  contributors: ("Ada Lovelace", [#link("{ABOUT}")[Khyber Sen]], )',
        id="typst",
    ),
]
STRUCK_AND_COLORED = [
    pytest.param(
        HtmlEmitter(inline_css=False, site_url=HOST),
        "<s>cut this</s>",
        '<span style="color: #ff9900">note</span>',
        id="html",
    ),
    pytest.param(
        MarkdownEmitter(), "~~cut this~~", '<span style="color: #ff9900">note</span>', id="markdown"
    ),
    pytest.param(
        TypstEmitter(site_url=HOST),
        "#strike[cut this]",
        '#text(fill: rgb("#ff9900"))[note]',
        id="typst",
    ),
]


@pytest.mark.parametrize(("emitter", "linked"), STAFF_LINKED)
def test_a_contributor_on_staff_is_linked_in_every_format(emitter: Emitter, linked: str) -> None:
    """Linked to their entry on the about page, as `etany.org` links them;
    anyone else is credited as plain text, since there is nowhere to link them to."""
    doc = named_images(parse(FIXTURE))
    doc.meta["Public Contributors"] = "Khyber Sen, Ada Lovelace"
    doc.staff = ("Blair Lorenzo", "Khyber Sen")
    assert linked in emitter.emit(doc)


@pytest.mark.parametrize(("emitter", "struck", "colored"), STRUCK_AND_COLORED)
def test_struck_and_colored_text_in_every_format(
    emitter: Emitter, struck: str, colored: str
) -> None:
    """As Docs draws them, so every output shows what the document does."""
    runs: list[Inline] = [
        Text(text="cut this", strike=True),
        Text(text=" and "),
        Text(text="note", color="#ff9900"),
    ]
    out = emitter.emit(Document(blocks=[Paragraph(runs)]))
    assert struck in out
    assert colored in out
    assert " and " in out
