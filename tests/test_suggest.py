"""`eta-publish suggest`, against a document held in memory (`fake_docs`), with no network.

Each warning is made by hand at a place in the document as the build reads it,
so what is tested is what becomes of it: where it is written, and what a second run does.
"""

import json
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import override

import pytest
from fake_docs import TAB, FakeDocs
from rich.console import Console
from typer.testing import CliRunner

from eta_publish import __main__ as cli
from eta_publish import suggest as suggest_module
from eta_publish.check_names import Check
from eta_publish.docs_json import JsonObject
from eta_publish.nodes import (
    Document,
    Edit,
    Link,
    Location,
    Mark,
    Notice,
    ParagraphStyle,
    Replace,
    Underline,
    key_line,
)
from eta_publish.site import Publication
from eta_publish.suggest import (
    DocsApi,
    Outcome,
    SuggestFailed,
    Thing,
    Verb,
    suggest,
    tally,
    warnings_of,
    write,
)

URL = f"https://docs.google.com/document/d/doc/edit?tab={TAB}"

BODY = "A headline\nThe line is 137 feet long, and the ETA says so.\nA last paragraph.\n"


def warned(*marks: Mark, check: Check = Check.UNIT_NOT_ABBREVIATED) -> Notice:
    return Notice(check, (f"{check} here",), marks)


def given(*notices: Notice) -> Callable[[JsonObject, Path | None], tuple[Document, list[str]]]:
    """Warnings as the build would find them, whatever the document says."""

    def warnings(document: JsonObject, records: Path | None) -> tuple[Document, list[str]]:
        doc = Document()
        doc.warnings = list(notices)
        return doc, []

    return warnings


def run(docs: FakeDocs, *notices: Notice, apply: bool = True) -> Outcome:
    outcome = suggest(docs, Publication(url=URL), None, apply, warnings=given(*notices))
    assert not outcome.error, outcome.error
    return outcome


def verbs(outcome: Outcome) -> list[tuple[Verb, Thing, str]]:
    return [(step.verb, step.thing, step.key) for step in outcome.steps]


def again_changes_nothing(docs: FakeDocs, *notices: Notice) -> None:
    """The second run of the same warnings, which has to leave the document as it is."""
    sent = len(docs.batches)
    outcome = run(docs, *notices)
    assert {step.verb for step in outcome.steps} <= {Verb.KEEP}
    assert len(docs.batches) == sent


def fixed(docs: FakeDocs, *edits: Edit, subject: str = "137 feet") -> Mark:
    return Mark(edits[0].location, fix=edits, subject=subject)


# ---- comments ------------------------------------------------------------


def test_a_comment_says_the_warning_and_its_key_where_it_is_about() -> None:
    docs = FakeDocs(BODY)
    notice = warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE)
    outcome = run(docs, notice)
    assert verbs(outcome) == [(Verb.CREATE, Thing.COMMENT, "eta-with-article: the ETA")]
    (comment,) = docs.comments
    assert comment["headPost"]["content"] == (f"{notice}\n{key_line('eta-with-article: the ETA')}")
    assert docs.commented(comment["commentId"]) == "the ETA"
    again_changes_nothing(docs, notice)


def test_a_comment_in_a_footnote_is_anchored_in_it() -> None:
    docs = FakeDocs(BODY, {"kix.note": " A footnote with the ETA in it.\n"})
    notice = warned(Mark(docs.at("the ETA", "kix.note"), subject="x"), check=Check.ETA_WITH_ARTICLE)
    run(docs, notice)
    ((requests, _),) = docs.batches
    assert requests[0]["insertComment"]["range"]["segmentId"] == "kix.note"
    assert docs.commented(docs.comments[0]["commentId"]) == "the ETA"
    again_changes_nothing(docs, notice)


def test_a_comment_whose_warning_says_something_else_now_is_reworded() -> None:
    docs = FakeDocs(BODY)
    mark = Mark(docs.at("the ETA"), subject="the ETA")
    run(docs, warned(mark, check=Check.ETA_WITH_ARTICLE))
    reworded = Notice(Check.ETA_WITH_ARTICLE, ("say ETA, not the ETA",), (mark,))
    outcome = run(docs, reworded)
    assert verbs(outcome) == [(Verb.UPDATE, Thing.COMMENT, "eta-with-article: the ETA")]
    assert docs.comments[0]["headPost"]["content"].startswith("say ETA, not the ETA\n")
    again_changes_nothing(docs, reworded)


def test_a_comment_a_person_resolved_is_reopened_while_its_warning_is_there() -> None:
    docs = FakeDocs(BODY)
    notice = warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE)
    run(docs, notice)
    docs.person_resolves(docs.comments[0]["commentId"])
    outcome = run(docs, notice)
    assert verbs(outcome) == [(Verb.REOPEN, Thing.COMMENT, "eta-with-article: the ETA")]
    assert docs.comments[0]["status"] == "OPEN"
    again_changes_nothing(docs, notice)


def test_a_comment_whose_warning_is_gone_is_resolved_and_then_left() -> None:
    docs = FakeDocs(BODY)
    run(docs, warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE))
    outcome = run(docs)
    assert verbs(outcome) == [(Verb.RESOLVE, Thing.COMMENT, "eta-with-article: the ETA")]
    assert docs.comments[0]["status"] == "RESOLVED"
    again_changes_nothing(docs)


def test_a_comment_whose_text_is_gone_is_made_again_where_the_warning_now_is() -> None:
    docs = FakeDocs(BODY)
    run(docs, warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE))
    docs.person_edits("and the ETA says so", "and so says the ETA")
    notice = warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE)
    outcome = run(docs, notice)
    assert [step.verb for step in outcome.steps] == [Verb.DELETE, Verb.CREATE]
    (comment,) = docs.comments
    assert docs.commented(comment["commentId"]) == "the ETA"
    again_changes_nothing(docs, notice)


def anchored_at(docs: FakeDocs, comment: JsonObject) -> int:
    segment, first, _ = docs.anchors[comment["anchorId"]]
    return docs.segments[segment].index(first) + docs.offset(segment)


def test_comments_with_one_key_stay_on_their_places_and_a_new_place_gets_its_own() -> None:
    docs = FakeDocs("The ETA and the ETA.\nAnd the ETA.\n")
    first, second, third = (Mark(docs.at("ETA", nth=n), subject="ETA") for n in range(3))
    run(docs, warned(second, third, check=Check.ETA_WITH_ARTICLE))
    notice = warned(first, second, third, check=Check.ETA_WITH_ARTICLE)
    outcome = run(docs, notice)
    assert sorted(step.verb for step in outcome.steps) == [Verb.CREATE, Verb.KEEP, Verb.KEEP]
    assert sorted(anchored_at(docs, c) for c in docs.comments) == [
        mark.location.start for mark in (first, second, third)
    ]
    again_changes_nothing(docs, notice)


def test_fixing_one_of_two_places_resolves_the_comment_on_that_one() -> None:
    docs = FakeDocs("Say the ETA and the ETA.\n")
    first, second = (Mark(docs.at("ETA", nth=n), subject="ETA") for n in range(2))
    run(docs, warned(first, second, check=Check.ETA_WITH_ARTICLE))
    on_first, on_second = sorted(docs.comments, key=lambda c: anchored_at(docs, c))
    # A person fixes the first place, leaving its "ETA", which the comment is on.
    docs.person_edits("Say the ", "Say ")
    notice = warned(Mark(docs.at("ETA", nth=1), subject="ETA"), check=Check.ETA_WITH_ARTICLE)
    run(docs, notice)
    status = {c["commentId"]: c["status"] for c in docs.comments}
    assert status == {on_first["commentId"]: "RESOLVED", on_second["commentId"]: "OPEN"}
    again_changes_nothing(docs, notice)


def test_a_comment_on_the_end_of_a_paragraph_is_on_its_last_character() -> None:
    docs = FakeDocs(BODY)
    notice = warned(Mark(docs.point("A headline"), subject="x"), check=Check.ETA_WITH_ARTICLE)
    run(docs, notice)
    assert docs.commented(docs.comments[0]["commentId"]) == "e"
    again_changes_nothing(docs, notice)


def test_someone_elses_comment_is_left_alone() -> None:
    docs = FakeDocs(BODY)
    theirs = docs.person_comments(f"mine\n{key_line('eta-with-article: the ETA')}", on="the ETA")
    outcome = run(docs)
    assert outcome.steps == []
    assert [c["commentId"] for c in docs.comments] == [theirs]


# ---- suggestions -----------------------------------------------------------


def test_a_fix_is_suggested_as_a_replacement_and_kept_the_second_time() -> None:
    docs = FakeDocs(BODY)
    notice = warned(fixed(docs, Replace(docs.at("feet"), "ft")))
    outcome = run(docs, notice)
    assert verbs(outcome) == [(Verb.CREATE, Thing.SUGGESTION, "unit-not-abbreviated: 137 feet")]
    (sid,) = docs.open_suggestions()
    assert docs.suggested_by(sid) == ("ft", "feet")
    assert docs.inline_text() == BODY.replace("feet", "ftfeet")
    again_changes_nothing(docs, notice)


def test_a_fix_of_several_edits_is_suggested_whole_and_kept_whole() -> None:
    docs = FakeDocs(BODY)
    notice = warned(
        fixed(
            docs,
            Replace(docs.at(" feet"), " ft"),
            Replace(docs.point("The line"), " A"),
            Replace(docs.at(", and"), ""),
        )
    )
    run(docs, notice)
    assert sorted(docs.suggested_by(sid) for sid in docs.open_suggestions()) == [
        ("", ", and"),
        (" A", ""),
        (" ft", " feet"),
    ]
    again_changes_nothing(docs, notice)


def test_a_style_fix_is_suggested_and_kept() -> None:
    docs = FakeDocs(BODY)
    notices = (
        warned(fixed(docs, Underline(docs.at("137"), underline=True))),
        warned(
            fixed(docs, Link(docs.at("last"), "https://example.org/")), check=Check.URL_NOT_LINKED
        ),
        warned(
            Mark(
                docs.at("A headline\n"),
                fix=(ParagraphStyle(docs.at("A headline\n"), "NORMAL_TEXT"),),
            ),
            check=Check.IMAGE_STYLED_AS_HEADING,
        ),
    )
    outcome = run(docs, *notices)
    assert [step.verb for step in outcome.steps] == [Verb.CREATE] * 3
    assert len(docs.open_suggestions()) == 3
    again_changes_nothing(docs, *notices)


def test_a_suggestion_whose_fix_changed_is_deleted_and_made_again() -> None:
    docs = FakeDocs(BODY)
    run(docs, warned(fixed(docs, Replace(docs.at("feet"), "ft"))))
    notice = warned(fixed(docs, Replace(docs.at("feet"), " ft")))
    outcome = run(docs, notice)
    assert sorted(step.verb for step in outcome.steps) == [Verb.CREATE, Verb.DELETE]
    (sid,) = docs.open_suggestions()
    assert docs.suggested_by(sid) == (" ft", "feet")
    again_changes_nothing(docs, notice)


def test_a_suggestion_no_warning_asks_for_is_deleted() -> None:
    docs = FakeDocs(BODY)
    run(docs, warned(fixed(docs, Replace(docs.at("feet"), "ft"))))
    outcome = run(docs)
    assert [step.verb for step in outcome.steps] == [Verb.DELETE]
    assert docs.open_suggestions() == []
    assert docs.inline_text() == BODY
    again_changes_nothing(docs)


def test_a_suggestion_a_person_rejected_is_suggested_again() -> None:
    docs = FakeDocs(BODY)
    notice = warned(fixed(docs, Replace(docs.at("feet"), "ft")))
    run(docs, notice)
    (rejected,) = docs.open_suggestions()
    docs.person_rejects(rejected)
    outcome = run(docs, notice)
    assert verbs(outcome) == [(Verb.CREATE, Thing.SUGGESTION, "unit-not-abbreviated: 137 feet")]
    (sid,) = docs.open_suggestions()
    assert sid != rejected
    assert docs.suggested_by(sid) == ("ft", "feet")
    again_changes_nothing(docs, notice)


def test_someone_elses_suggestion_is_left_alone() -> None:
    docs = FakeDocs(BODY)
    theirs = docs.person_inserts("very ", after="The line is ")
    run(docs)
    assert docs.open_suggestions() == [theirs]


def test_overlapping_fixes_are_not_both_written_in_one_run() -> None:
    docs = FakeDocs(BODY)
    outcome = run(
        docs,
        warned(fixed(docs, Replace(docs.at("feet"), "ft"))),
        warned(fixed(docs, Replace(docs.at("137 feet"), "137 ft"), subject="x")),
    )
    assert sorted((step.verb, step.why) for step in outcome.steps) == [
        (Verb.CREATE, ""),
        (Verb.SKIP, "it overlaps another fix made in this run"),
    ]
    (sid,) = docs.open_suggestions()
    assert docs.suggested_by(sid) == ("137 ft", "137 feet")


def test_a_deletion_and_an_insertion_at_its_start_from_two_marks_are_kept() -> None:
    docs = FakeDocs(BODY)
    notices = (
        warned(fixed(docs, Replace(docs.at("137 "), ""))),
        warned(fixed(docs, Replace(docs.point("is "), "about "), subject="y")),
    )
    run(docs, *notices)
    # Sent together, the two are one replacement, as Docs makes them.
    (sid,) = docs.open_suggestions()
    assert docs.suggested_by(sid) == ("about ", "137 ")
    again_changes_nothing(docs, *notices)


@pytest.mark.parametrize("underline", [False, True], ids=["replacement", "underline"])
def test_our_suggestion_with_someone_elses_insertion_inside_it_is_kept(underline: bool) -> None:
    docs = FakeDocs(BODY)
    where = docs.at("137 feet")
    edit = Underline(where, underline=True) if underline else Replace(where, "137 ft")
    notice = warned(fixed(docs, edit))
    run(docs, notice)
    docs.person_inserts("X", after="137 f")
    again_changes_nothing(docs, notice)


# ---- where, with other people's suggestions in the text -----------------------


def test_what_someone_suggested_before_a_warning_moves_where_it_is_written() -> None:
    docs = FakeDocs(BODY)
    docs.person_inserts("XYZ ", after="A head")
    docs.person_deletes("A last")
    notices = (
        warned(fixed(docs, Replace(docs.at("feet"), "ft"))),
        warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE),
    )
    run(docs, *notices)
    ours = [sid for sid in docs.open_suggestions() if "ours" in sid]
    assert [docs.suggested_by(sid) for sid in ours] == [("ft", "feet")]
    assert docs.commented(docs.comments[0]["commentId"]) == "the ETA"
    again_changes_nothing(docs, *notices)


def test_a_fix_overlapping_someone_elses_suggestion_is_skipped_and_said_why() -> None:
    docs = FakeDocs(BODY)
    docs.person_deletes("137 feet")
    outcome = run(docs, warned(fixed(docs, Replace(docs.at("feet"), "ft"))))
    ((verb, why),) = [(step.verb, step.why) for step in outcome.steps]
    assert verb is Verb.SKIP
    assert "overlaps a suggestion" in why
    assert docs.batches == []


def test_an_insertion_against_someone_elses_insertion_is_skipped() -> None:
    docs = FakeDocs(BODY)
    docs.person_inserts("very ", after="The line is ")
    outcome = run(docs, warned(fixed(docs, Replace(docs.point("The line is "), "now "))))
    assert [step.verb for step in outcome.steps] == [Verb.SKIP]


def test_text_that_changed_before_the_write_is_skipped() -> None:
    docs = FakeDocs(BODY)
    run(docs, warned(Mark(docs.at("A last"), subject="x"), check=Check.ETA_WITH_ARTICLE))
    # The first batch resolves that comment; someone edits the text before the next is sent.
    docs.before_batch = lambda d: d.person_edits("137", "140")
    outcome = run(docs, warned(fixed(docs, Replace(docs.at("feet"), "ft"))))
    skipped = [step for step in outcome.steps if step.verb is Verb.SKIP]
    assert [step.why for step in skipped] == [
        "the text there has changed since the warnings were read"
    ]
    assert docs.open_suggestions() == []


def test_a_write_the_document_moved_on_from_is_placed_again() -> None:
    docs = FakeDocs(BODY)
    notice = warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE)
    # Something else is suggested between the read the comment is placed in and its write.
    docs.before_batch = lambda d: d.person_inserts("XYZ ", after="A head")
    run(docs, notice)
    assert docs.commented(docs.comments[0]["commentId"]) == "the ETA"


# ---- the run -------------------------------------------------------------------


def test_without_apply_nothing_is_written_and_everything_is_said() -> None:
    docs = FakeDocs(BODY)
    notice = warned(fixed(docs, Replace(docs.at("feet"), "ft")))
    outcome = run(docs, notice, apply=False)
    assert verbs(outcome) == [(Verb.CREATE, Thing.SUGGESTION, "unit-not-abbreviated: 137 feet")]
    assert docs.batches == []
    assert docs.suggestions == {}


def test_the_command_writes_nothing_without_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = FakeDocs(BODY)
    notice = warned(fixed(docs, Replace(docs.at("feet"), "ft")))
    monkeypatch.setattr(cli, "DocsApi", lambda: docs)

    def warnings(document: JsonObject, records: Path | None) -> tuple[Document, list[str]]:
        doc = Document()
        doc.warnings = [notice]
        return doc, []

    monkeypatch.setattr(suggest_module, "warnings_of", warnings)
    result = CliRunner().invoke(cli.app, ["suggest", URL])
    assert result.exit_code == 0, result.output
    assert "would create" in result.output
    assert "`--apply` writes it" in result.output
    assert docs.batches == []
    result = CliRunner().invoke(cli.app, ["suggest", URL, "--apply"])
    assert result.exit_code == 0, result.output
    assert "created" in result.output
    assert len(docs.open_suggestions()) == 1


class FailingSuggestions(FakeDocs):
    @override
    def batch(
        self, doc_id: str, requests: list[JsonObject], suggest: bool, revision: str | None
    ) -> JsonObject:
        if suggest:
            raise SuggestFailed("the API returned 400: invalid range")
        return super().batch(doc_id, requests, suggest, revision)


def test_what_a_failed_batch_was_to_make_is_said_to_be_not_done() -> None:
    docs = FailingSuggestions(BODY)
    run(docs, warned(Mark(docs.at("the ETA"), subject="the ETA"), check=Check.ETA_WITH_ARTICLE))
    notices = (
        warned(Mark(docs.at("A last"), subject="last"), check=Check.ETA_WITH_ARTICLE),
        warned(fixed(docs, Replace(docs.at("feet"), "ft"))),
    )
    outcome = suggest(docs, Publication(url=URL), None, True, warnings=given(*notices))
    assert outcome.error == "the API returned 400: invalid range"
    log = StringIO()
    write(outcome, True, Console(file=log, width=200))
    lines = log.getvalue().splitlines()
    # The comments went out before the failure; the suggestion did not.
    assert sorted(" ".join(line.split()[:3]) for line in lines[1:4]) == [
        "created comment eta-with-article:",
        "not created suggestion",
        "resolved comment eta-with-article:",
    ]
    assert str(tally([outcome], True)) == "1 created · 1 resolved · 1 not done · 1 failed"


def test_comments_the_api_says_it_did_not_save_fail_the_batch() -> None:
    class Request:
        def execute(self) -> JsonObject:
            return {"commentUpdateState": "ALL_FAILED_UNKNOWN_REASON"}

    class Documents:
        def batchUpdate(self, documentId: str, body: JsonObject) -> Request:
            return Request()

    api = DocsApi.__new__(DocsApi)
    api.documents = Documents()
    with pytest.raises(SuggestFailed, match="ALL_FAILED_UNKNOWN_REASON"):
        api.batch("doc", [{"insertComment": {}}], suggest=False, revision=None)


def test_a_fix_skipped_in_one_read_is_placed_again_after_the_document_moves_on() -> None:
    docs = FakeDocs(BODY)
    # A comment for the first batch to resolve, so something happens before the suggestions.
    run(docs, warned(Mark(docs.at("A last"), subject="last"), check=Check.ETA_WITH_ARTICLE))
    notices = (
        warned(fixed(docs, Replace(docs.point("The line is "), "now "))),
        warned(fixed(docs, Replace(docs.at("feet"), "ft")), check=Check.ETA_WITH_ARTICLE),
    )

    def suggested_beside(d: FakeDocs) -> None:
        # Someone suggests text right where the insertion goes, so it is skipped in that read,
        # and withdraws it as the other fix is sent, which moves the document on.
        theirs = d.person_inserts("very ", after="The line is ")
        d.before_batch = lambda again: again.person_rejects(theirs)

    docs.before_batch = suggested_beside
    outcome = run(docs, *notices)
    assert [(step.verb, step.done) for step in outcome.steps if step.thing is Thing.SUGGESTION] == [
        (Verb.CREATE, True),
        (Verb.CREATE, True),
    ]
    assert sorted(docs.suggested_by(sid) for sid in docs.open_suggestions()) == [
        ("ft", "feet"),
        ("now ", ""),
    ]


def _list(path: Path, *names: str) -> Path:
    path.write_text(
        "".join(
            f'[[report]]\nname = "{name}"\ntab = "Tab"\n'
            f'url = "https://docs.google.com/document/d/{name}/edit?tab=t.0"\npublished = "draft"\n'
            for name in names
        )
    )
    return path


def test_one_document_is_chosen_by_its_name_in_either_list_or_by_its_url(tmp_path: Path) -> None:
    public = _list(tmp_path / "publications.toml", "One", "Two")
    drafts = _list(tmp_path / "drafts.toml", "Three")
    lists = [public, drafts]
    assert [p.name for p in cli.suggested_publications(None, lists)] == ["One", "Two", "Three"]
    assert [p.name for p in cli.suggested_publications("three", lists)] == ["Three"]
    assert cli.suggested_publications(URL, lists) == [Publication(url=URL)]


def test_a_listed_document_that_is_not_the_one_named_is_not_written_to() -> None:
    docs = FakeDocs(BODY)
    publication = Publication(url=URL, name="Another", tab="Tab")
    outcome = suggest(
        docs,
        publication,
        None,
        apply=True,
        warnings=lambda d, r: (Document(file_title="Doc", tab_title="Tab"), []),
    )
    assert "calls this `Another`" in outcome.error
    assert docs.batches == []


def test_the_build_s_own_checks_give_the_marks(tmp_path: Path) -> None:
    saved = Path(__file__).parent.parent / "site/unpublished/reports/monthly-passes"
    doc, said = warnings_of(json.loads((saved / "doc.json").read_text()), saved)
    assert said == []
    assert any(notice.marks for notice in doc.warnings)
    assert all(
        isinstance(mark.location, Location) for notice in doc.warnings for mark in notice.marks
    )
