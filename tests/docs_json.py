"""Hand-built Docs JSON that tests share: paragraphs, fields, pictures, and whole builds."""

import json
from pathlib import Path

from paths import HOSTS

from eta_publish.archive import ARCHIVES_JSON
from eta_publish.build import IMAGES_JSON
from eta_publish.docs_json import JsonObject
from eta_publish.naming import UNPUBLISHED_DIR
from eta_publish.nodes import Document, Inline, Text
from eta_publish.publish import Suggestions, publish
from eta_publish.site import Publication, Site


def para(text: str, style: str = "NORMAL_TEXT") -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": style},
            "elements": [{"textRun": {"content": text + "\n", "textStyle": {}}}],
        }
    }


def field(text: str, style: str = "NORMAL_TEXT") -> JsonObject:
    """A paragraph whose labels are underlined, which is how the document writes one.

    The name up to the first colon of each line: a label is a label because it
    is underlined, so a test meaning one has to write it the way the doc does.
    """
    runs: list[JsonObject] = []
    for n, line in enumerate(text.split("\v")):
        if n:
            runs.append({"textRun": {"content": "\v", "textStyle": {}}})
        mark = min((line.find(c) for c in ":]" if c in line), default=-1)
        if mark >= 0:
            runs.append({"textRun": {"content": line[:mark], "textStyle": {"underline": True}}})
        runs.append({"textRun": {"content": line[mark:] if mark >= 0 else line, "textStyle": {}}})
    runs[-1]["textRun"]["content"] += "\n"
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style}, "elements": runs}}


def image(object_id: str = "io.1") -> JsonObject:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"inlineObjectElement": {"inlineObjectId": object_id}}],
        }
    }


def text_of(content: list[Inline]) -> str:
    return "".join(i.text for i in content if isinstance(i, Text))


HEADER: dict[str, str] = {
    "Project Manager": "Khyber Sen",
    "SME/Liaison": "Blair Lorenzo",
    "Phase": "Drafting",
    "Discussion Channel": "#a-draft",
    "Publish Due Date": "2026-12-01",
    "Goals": "Make the case.",
    "Audience": "Planners.",
    "Public Contributors": "Alon Levy, Khyber Sen",
    "Private Contributors": "Blair Lorenzo",
    "URL": "/reports/a-draft",
    "Short": "A short line.",
    "SEO Description": "Cheaper, shallower, faster.",
    "Social Title Card": "A Draft",
}
"""A complete `Header` section, which warns about nothing.

A test changes it with `header(...)`: a value replaces one, and `None` leaves one out.
"""

HEADLINE = "A Draft About Tunnels"


def header(changes: dict[str, str | None] | None = None) -> list[JsonObject]:
    """The `Header` section and the headline that ends it, with `changes` made to `HEADER`."""
    fields = {**HEADER, **(changes or {})}
    return [
        para("Header", "HEADING_1"),
        *(
            part
            for name, value in fields.items()
            if value is not None
            for part in (
                [field(f"{name}: {value}"), image("io.card")]
                if name == "Social Title Card"
                else [field(f"{name}: {value}")]
            )
        ),
        para(HEADLINE, "TITLE"),
    ]


def drafted(
    content: list[JsonObject],
    *,
    changes: dict[str, str | None] | None = None,
    footnotes: dict[str, JsonObject] | None = None,
    objects: dict[str, str] | None = None,
    **review: int,
) -> JsonObject:
    """A Docs response for a publication whose body is `content`, under its header.

    `objects` maps the id of each inline object to its alt text.
    `review` is the counts the fetch records, `openSuggestions` and `openComments`.
    """
    return {
        "title": HEADLINE,
        "body": {"content": [*header(changes), *content]},
        "footnotes": footnotes or {},
        "lists": {},
        "inlineObjects": {
            object_id: {
                "inlineObjectProperties": {
                    "embeddedObject": {"description": alt, "imageProperties": {}}
                }
            }
            for object_id, alt in {"io.card": "The social card", **(objects or {})}.items()
        },
        **review,
    }


def rich(*pieces: str | tuple[str, JsonObject] | JsonObject) -> JsonObject:
    """A paragraph of runs: text, text with a style, or an element such as a footnote reference.

    A style is what Docs puts on a run, e.g. `{"bold": True}` or `{"link": {"url": ...}}`.
    """
    elements: list[JsonObject] = []
    for piece in pieces:
        if isinstance(piece, str):
            elements.append({"textRun": {"content": piece, "textStyle": {}}})
        elif isinstance(piece, tuple):
            elements.append({"textRun": {"content": piece[0], "textStyle": piece[1]}})
        else:
            elements.append(piece)
    last = elements[-1]["textRun"]
    last["content"] += "\n"
    return {
        "paragraph": {"paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}, "elements": elements}
    }


def footnote(*pieces: str | tuple[str, JsonObject]) -> JsonObject:
    """A footnote's definition, to go in `drafted(footnotes=...)`."""
    return {"content": [rich(*pieces)]}


def cites(footnote_id: str) -> JsonObject:
    """The reference to a footnote, for `rich`."""
    return {"footnoteReference": {"footnoteId": footnote_id}}


def link(url: str) -> JsonObject:
    """The style of a run that links `url`."""
    return {"link": {"url": url}}


PUBLICATION_URL = "https://docs.google.com/document/d/abc/edit?tab=t.1"
"""The tab `build` builds, which the response it saves says it is."""


def build(
    tmp_path: Path,
    document: JsonObject,
    *,
    images: dict[str, dict[str, object]] | None = None,
    archives: dict[str, dict[str, object]] | None = None,
    suggestions: Suggestions = Suggestions.REJECTED,
) -> tuple[Site, Path]:
    """Build `document` the way a build does, offline, and say where it went.

    The response is saved where the last build left one, with the `images.json`
    and the archive index beside it, so the build reads it and fetches nothing.
    `images` is what `images.json` records of each picture, and `archives`
    what the archive index records of each source, for what a test wants known.
    """
    root = tmp_path / "site"
    dest = root / UNPUBLISHED_DIR / "reports" / "a-draft"
    dest.mkdir(parents=True)
    saved = {**document, "documentId": "abc", "tabId": "t.1", "suggestions": suggestions.value}
    (dest / "doc.json").write_text(json.dumps(saved))
    (dest / IMAGES_JSON).write_text(json.dumps({"io.card": {"file": "card.png"}, **(images or {})}))
    if archives is not None:
        (dest / ARCHIVES_JSON).write_text(json.dumps(archives))
    site = publish(
        [Publication(url=PUBLICATION_URL)],
        root,
        suggestions,
        False,
        False,
        False,
        offline=True,
        archive=False,
        hosts=HOSTS,
    )
    return site, root / UNPUBLISHED_DIR / "reports" / "a-draft"


def warned(site: Site) -> list[str]:
    """What the build told the writer, in the order it said it."""
    doc: Document = site.built[0].doc
    return [str(w) for w in doc.warnings]
