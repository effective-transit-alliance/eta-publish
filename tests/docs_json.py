"""Hand-built Docs JSON that tests share: paragraphs, fields, and pictures."""

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Inline, Text


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
