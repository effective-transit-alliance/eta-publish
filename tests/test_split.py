"""Cutting an oversized report into pastable pieces."""

import json
import re

from paths import FIXTURE_DIR, named_images

from eta_publish.emit.html import CODE_BLOCK_LIMIT, HtmlEmitter
from eta_publish.parse import parse

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


def fragment() -> str:
    return HtmlEmitter().emit(named_images(parse(FIXTURE)))


def pieces() -> list[str]:
    emitter = HtmlEmitter()
    doc = named_images(parse(FIXTURE))
    return [emitter.join(emitter.wrapped(group)) for group in emitter.groups(doc)]


def test_each_piece_is_a_standalone_report_div() -> None:
    for piece in pieces():
        assert piece.count('<div class="eta-report') == 1
        assert piece.rstrip().endswith("</div>")
        assert piece.startswith("<style>")


def test_pieces_break_at_h2_and_nowhere_else() -> None:
    parts = pieces()
    # The h3 stays with its section rather than starting a new piece.
    with_h2 = [p for p in parts if "<h2 id=" in p]
    assert all(p.count("<h2 id=") == 1 for p in with_h2)
    assert any("<h3 id=" in p for p in with_h2)


def test_nothing_is_lost_in_the_split() -> None:
    """Every paragraph in the whole fragment survives into some piece."""
    whole = fragment()
    joined = "".join(pieces())
    for paragraph in re.findall(r"<p>.*?</p>", whole, re.S):
        assert paragraph in joined


def test_the_limit_matches_squarespace() -> None:
    assert CODE_BLOCK_LIMIT == 400_000


def test_a_piece_keeps_the_notes_behind_its_references() -> None:
    """A reference carries a copy of its note, read off the document rather than
    passed down the tree, so a walk that never set the document kept every
    reference and lost every preview: a difference nothing about a piece shows."""
    parts = pieces()
    with_refs = [p for p in parts if 'class="footnote-ref"' in p]
    assert with_refs
    assert all('class="footnote-tip"' in p for p in with_refs)


def test_the_pieces_are_the_whole_report() -> None:
    """Cut from the blocks rather than out of the markup, so this is the check
    that the two ways of walking one document agree."""
    emitter = HtmlEmitter()
    doc = named_images(parse(FIXTURE))
    whole = emitter.emit(doc)
    body = emitter.join([part for group in emitter.groups(doc) for part in group])
    assert body in whole
