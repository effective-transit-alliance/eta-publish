"""Tab selection, which is where a silent wrong-document bug would hide.

By default `documents.get` fills `body` from the first tab only,
so a publication drafted in a later tab would parse cleanly and be wrong.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from eta_publish.docs_json import JsonObject
from eta_publish.fetch import (
    RESPONSE_FORMAT,
    RESPONSE_KEYS,
    SCOPES,
    TabNotFound,
    parse_ref,
    select_tab,
)

URL = (
    "https://docs.google.com/document/d/1U-M71SN5azsWSLAnp_1cPaPBj8YDHfb9Z8uoopVopBg"
    "/edit?tab=t.ul3yzv5xed4w"
)

DOC_ID = "1U-M71SN5azsWSLAnp_1cPaPBj8YDHfb9Z8uoopVopBg"


def _tab(tab_id: str, title: str, text: str, children: Sequence[JsonObject] = ()) -> JsonObject:
    return {
        "tabProperties": {"tabId": tab_id, "title": title},
        "documentTab": {"body": {"content": [{"marker": text}]}},
        "childTabs": list(children),
    }


MULTI_TAB = {
    "title": "SAS West Feasibility Response",
    "tabs": [
        _tab("t.0", "Draft 2", "draft"),
        _tab("t.ul3yzv5xed4w", "Final", "final", [_tab("t.child", "Notes", "notes")]),
    ],
}


def test_parse_ref_extracts_the_tab_from_the_url():
    assert parse_ref(URL) == (DOC_ID, "t.ul3yzv5xed4w")


def test_parse_ref_accepts_a_bare_id():
    assert parse_ref(DOC_ID) == (DOC_ID, None)


def test_parse_ref_without_a_tab():
    assert parse_ref(f"https://docs.google.com/document/d/{DOC_ID}/edit") == (DOC_ID, None)


def test_the_requested_tab_wins_over_the_first_one():
    chosen = select_tab(MULTI_TAB, "t.ul3yzv5xed4w")
    assert chosen["body"]["content"][0]["marker"] == "final"
    assert chosen["tabTitle"] == "Final"


def test_child_tabs_are_selectable():
    assert select_tab(MULTI_TAB, "t.child")["tabTitle"] == "Notes"


def test_an_ambiguous_document_refuses_to_guess():
    with pytest.raises(TabNotFound) as e:
        select_tab(MULTI_TAB, None)
    assert "Draft 2" in str(e.value) and "Final" in str(e.value)


def test_an_unknown_tab_lists_what_is_available():
    with pytest.raises(TabNotFound) as e:
        select_tab(MULTI_TAB, "t.nope")
    assert "t.ul3yzv5xed4w" in str(e.value)


def test_a_single_tab_document_needs_no_choice():
    single = {"title": "x", "tabs": [_tab("t.only", "Only", "only")]}
    assert select_tab(single, None)["body"]["content"][0]["marker"] == "only"


def test_a_document_with_no_tabs_is_passed_through():
    plain = {"title": "x", "body": {"content": [{"marker": "plain"}]}}
    assert select_tab(plain, None) is plain


# ---- credentials ----------------------------------------------------


def unasked(doc_id: str) -> str | None:
    """`modified_time`, for a test that is not about when Drive saw the document.

    Asking is a call to Drive, and every one of these stubs the fetch itself.
    """
    return None


def test_service_account_credentials_are_used_when_the_environment_names_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CI has no browser to open and nobody to click,
    so the interactive flow must not be what runs there."""
    import google.auth

    from eta_publish import fetch as fetch_module

    sentinel = object()

    def fake_default(scopes: list[str]) -> tuple[object, str]:
        assert scopes == SCOPES
        return sentinel, "eta-publish"

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "key.json"))
    monkeypatch.setattr(google.auth, "default", fake_default)
    assert fetch_module._credentials() is sentinel


def test_without_the_environment_variable_nothing_is_ambient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eta_publish import fetch as fetch_module

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert fetch_module._ambient_credentials() is None


def test_a_suggestion_is_counted_once_however_much_it_touches() -> None:
    """One suggestion over a sentence marks every run in it:
    the real document carries 240 insertion marks and far fewer suggestions."""
    from eta_publish.fetch import _suggestion_ids

    document = {
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [
                            {"textRun": {"suggestedInsertionIds": ["s.1"]}},
                            {"textRun": {"suggestedInsertionIds": ["s.1"]}},
                            {"textRun": {"suggestedDeletionIds": ["s.2"]}},
                        ]
                    }
                },
                {"paragraph": {"suggestedParagraphStyleChanges": {"s.3": {"bold": True}}}},
            ]
        }
    }
    assert _suggestion_ids(document) == {"s.1", "s.2", "s.3"}


def test_a_document_with_nothing_suggested_counts_none() -> None:
    from eta_publish.fetch import _suggestion_ids

    assert _suggestion_ids({"body": {"content": [{"paragraph": {"elements": []}}]}}) == set()


def test_a_service_account_is_not_asked_about_the_review(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is refused the suggestions outright,
    and for the comments the export answers, renders a document with none in it
    because it cannot see any, and returns a nought no retry would catch."""
    import eta_publish.fetch as fetch

    def boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("a service account must not be asked this")

    def whole_document(doc_id: str, suggestions: str = "rejected") -> JsonObject:
        return {"tabs": []}

    def one_tab(document: JsonObject, wanted: str | None) -> JsonObject:
        return {"body": {}}

    monkeypatch.setattr(fetch, "_ambient_credentials", lambda: object())
    monkeypatch.setattr(fetch, "fetch_document", whole_document)
    monkeypatch.setattr(fetch, "select_tab", one_tab)
    # `fetch` asks Drive when the document was last edited,
    # which is a call to Drive and not what any of this is about.
    monkeypatch.setattr(fetch, "modified_time", unasked)
    monkeypatch.setattr(fetch, "open_suggestions", boom)
    monkeypatch.setattr(fetch, "open_comments_on_tab", boom)

    document = fetch.fetch("https://docs.google.com/document/d/abc/edit")
    assert "openSuggestions" not in document
    assert "openComments" not in document


def test_keeping_the_last_counts_is_said_out_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`gcloud auth application-default login` is enough to stop these being counted,
    and a build that quietly republishes the last numbers looks like one that checked."""
    import eta_publish.fetch as fetch

    def whole_document(doc_id: str, suggestions: str = "rejected") -> JsonObject:
        return {"tabs": []}

    def one_tab(document: JsonObject, wanted: str | None) -> JsonObject:
        return {"body": {}}

    monkeypatch.setattr(fetch, "_ambient_credentials", lambda: object())
    monkeypatch.setattr(fetch, "fetch_document", whole_document)
    monkeypatch.setattr(fetch, "select_tab", one_tab)
    # `fetch` asks Drive when the document was last edited,
    # which is a call to Drive and not what any of this is about.
    monkeypatch.setattr(fetch, "modified_time", unasked)

    fetch.fetch("https://docs.google.com/document/d/abc/edit")
    assert "not asking about suggestions or comments" in capsys.readouterr().err


def test_comments_can_be_left_unasked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The export is the slowest thing a build does, and the key it would set
    is one `carry_over_review` fills in from the last build that did ask."""
    import eta_publish.fetch as fetch

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("the comment export was asked for anyway")

    def whole_document(doc_id: str, suggestions: str = "rejected") -> JsonObject:
        return {"tabs": []}

    def one_tab(document: JsonObject, wanted: str | None) -> JsonObject:
        return {"body": {}}

    def three_open(doc_id: str, tab: str | None = None) -> int:
        return 3

    monkeypatch.setattr(fetch, "_ambient_credentials", lambda: None)
    monkeypatch.setattr(fetch, "fetch_document", whole_document)
    monkeypatch.setattr(fetch, "select_tab", one_tab)
    # `fetch` asks Drive when the document was last edited,
    # which is a call to Drive and not what any of this is about.
    monkeypatch.setattr(fetch, "modified_time", unasked)
    monkeypatch.setattr(fetch, "open_suggestions", three_open)
    monkeypatch.setattr(fetch, "open_comments_on_tab", boom)

    document = fetch.fetch("https://docs.google.com/document/d/abc/edit", comments=False)
    assert document["openSuggestions"] == 3
    assert "openComments" not in document


def test_a_document_drive_says_is_unmoved_is_not_fetched_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Editing a document moves `modifiedTime`, and proposing, accepting, or
    rejecting a suggestion is editing it, so neither is asked for again.
    Commenting is not, so comments are counted every time."""
    import eta_publish.fetch as fetch

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a document Drive called unmoved was fetched anyway")

    saved = tmp_path / "doc.json"
    saved.write_text(
        json.dumps(
            {
                "body": {},
                "format": RESPONSE_FORMAT,
                "modifiedTime": "2026-09-01T01:10:14.243Z",
                "suggestions": "rejected",
                "openSuggestions": 17,
            }
        )
    )
    monkeypatch.setattr(fetch, "_ambient_credentials", lambda: None)

    def unmoved(doc_id: str) -> str:
        return "2026-09-01T01:10:14.243Z"

    def four_threads(doc_id: str, tab: str | None) -> int:
        return 4

    monkeypatch.setattr(fetch, "modified_time", unmoved)
    monkeypatch.setattr(fetch, "fetch_document", boom)
    monkeypatch.setattr(fetch, "open_suggestions", boom)
    monkeypatch.setattr(fetch, "open_comments_on_tab", four_threads)

    document = fetch.fetch("https://docs.google.com/document/d/abc/edit", cached=saved)
    assert document["openSuggestions"] == 17
    assert document["openComments"] == 4


MATCHING = json.dumps({"modifiedTime": "now", "suggestions": "rejected", "format": RESPONSE_FORMAT})


@pytest.mark.parametrize(
    ("saved_text", "current"),
    [
        ('{"modifiedTime": "then", "suggestions": "rejected"}', "now"),
        ('{"body": {}, "suggestions": "rejected"}', "now"),
        ('{"modifiedTime": "now", "suggestions": "accepted"}', "now"),
        ('{"modifiedTime": "now", "suggestions": "rejected"}', "now"),
        ("{not json", "now"),
        ('{"modifiedTime": "then", "suggestions": "rejected"}', None),
    ],
    ids=[
        "edited since",
        "saved before the time was recorded",
        "read the other way",
        "saved in an older shape",
        "unreadable",
        "drive would not say",
    ],
)
def test_anything_short_of_a_match_is_a_reason_to_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, saved_text: str, current: str | None
) -> None:
    """Not knowing whether this is the document this run wants is a reason to fetch it,
    which is what this was trying to avoid and not something it may decide against."""
    import eta_publish.fetch as fetch

    saved = tmp_path / "doc.json"
    saved.write_text(saved_text)

    def says(doc_id: str) -> str | None:
        return current

    monkeypatch.setattr(fetch, "modified_time", says)
    assert fetch.unchanged("abc", saved, "rejected") is None


def test_a_match_on_both_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The one case that does not fetch, beside the six that do."""
    import eta_publish.fetch as fetch

    saved = tmp_path / "doc.json"
    saved.write_text(MATCHING)

    def now(doc_id: str) -> str:
        return "now"

    monkeypatch.setattr(fetch, "modified_time", now)
    assert fetch.unchanged("abc", saved, "rejected") is not None


def test_a_missing_saved_response_is_a_reason_to_fetch(tmp_path: Path) -> None:
    import eta_publish.fetch as fetch

    assert fetch.unchanged("abc", tmp_path / "absent.json", "rejected") is None


def test_a_selected_tab_says_where_it_came_from() -> None:
    """A saved response is read by whoever wants the document behind it,
    and a link is what they want, not two ids to assemble one from."""
    tab: JsonObject = {
        "tabProperties": {"tabId": "t.1", "title": "Live version"},
        "documentTab": {},
    }
    document: JsonObject = {"documentId": "abc", "title": "IBX Automation", "tabs": [tab]}
    chosen = select_tab(document, "t.1")
    assert chosen["url"] == "https://docs.google.com/document/d/abc/edit?tab=t.1"
    assert parse_ref(chosen["url"]) == ("abc", "t.1")


def test_a_document_url_is_spelled_one_way() -> None:
    """However the reference that reached the build was spelled,
    including as a bare id or a path, which are not URLs at all."""
    from eta_publish.fetch import document_url

    assert document_url("abc") == "https://docs.google.com/document/d/abc/edit"
    assert document_url("abc", "t.1") == "https://docs.google.com/document/d/abc/edit?tab=t.1"


def test_a_saved_response_says_what_shape_it_is() -> None:
    """The list `RESPONSE_FORMAT` is computed from has to be the list
    `select_tab` actually writes, or the marker marks the wrong thing.

    This failing means a key was added or dropped: update `RESPONSE_KEYS`,
    which changes the marker, which is what makes every response saved
    in the old shape be fetched again instead of reused.
    """
    tab: JsonObject = {
        "tabProperties": {"tabId": "t.1", "title": "Live version"},
        "documentTab": {},
    }
    document: JsonObject = {"documentId": "abc", "title": "IBX Automation", "tabs": [tab]}
    written = select_tab(document, "t.1")
    assert set(written) == {*RESPONSE_KEYS, "format"}
    assert written["format"] == RESPONSE_FORMAT
