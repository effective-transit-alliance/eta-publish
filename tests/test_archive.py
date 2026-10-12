"""What the report cites, and the record of where each of those is archived."""

import json
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import cast, override

import pytest
import requests
from pypdf import PdfWriter

from eta_publish import archive
from eta_publish.archive import (
    ARCHIVES_JSON,
    missing,
    read_archive_index,
    write_archive_index,
)
from eta_publish.nodes import (
    Archived,
    Document,
    Figure,
    Image,
    Paragraph,
    Text,
    unwrap_snapshot,
)


def cites(*hrefs: str) -> Document:
    """A document whose body is one paragraph of links."""
    return Document(blocks=[Paragraph(content=[Text(text=href, href=href) for href in hrefs])])


# ---- what counts as a source ----------------------------------------


def test_sources_are_external_links_in_document_order() -> None:
    doc = cites("https://b.example/2", "https://a.example/1")
    assert doc.sources == ["https://b.example/2", "https://a.example/1"]


def test_a_source_cited_twice_is_one_source_and_keeps_its_first_place() -> None:
    doc = cites("https://a.example/1", "https://b.example/2", "https://a.example/1")
    assert doc.sources == ["https://a.example/1", "https://b.example/2"]
    assert doc.source_uses == {"https://a.example/1": 2, "https://b.example/2": 1}


def test_anchors_and_email_addresses_are_not_sources() -> None:
    doc = cites(
        "#fn3",
        "mailto:someone@example.org",
        "https://www.etany.org/reports/something",
        "https://a.example/1",
    )
    assert doc.sources == [
        "https://www.etany.org/reports/something",
        "https://a.example/1",
    ]


def test_a_figures_source_line_is_not_a_source() -> None:
    """It names the file in Drive, and no published output points at it."""
    figure = Figure(
        image=Image(object_id="kix.1", filename="img-1"),
        source=[Text(text="drive", href="https://drive.google.com/file/d/1/view")],
        caption=[Text(text="cited", href="https://a.example/1")],
    )
    assert Document(blocks=[figure]).sources == ["https://a.example/1"]


# ---- a link the document already wrote as a snapshot ------------------


def test_a_wayback_link_is_the_page_it_is_of() -> None:
    original, archived = unwrap_snapshot(
        "https://web.archive.org/web/20240503123456/https://nypost.com/a"
    )
    assert original == "https://nypost.com/a"
    assert archived == Archived(
        snapshot="https://web.archive.org/web/20240503123456/https://nypost.com/a",
        timestamp="20240503123456",
    )


def test_a_modifier_on_the_timestamp_is_not_a_different_capture() -> None:
    plain, _ = unwrap_snapshot("https://web.archive.org/web/20240503123456/https://nypost.com/a")
    with_modifier, archived = unwrap_snapshot(
        "https://web.archive.org/web/20240503123456id_/https://nypost.com/a"
    )
    assert with_modifier == plain
    assert archived is not None
    assert archived.snapshot.endswith("/web/20240503123456/https://nypost.com/a")


def test_an_ordinary_link_is_left_alone() -> None:
    assert unwrap_snapshot("https://nypost.com/a") == ("https://nypost.com/a", None)


# ---- the record -------------------------------------------------------


def test_the_record_round_trips(tmp_path: Path) -> None:
    doc = cites("https://a.example/1")
    doc.archives["https://a.example/1"] = Archived(
        snapshot="https://web.archive.org/web/20240503123456/https://a.example/1",
        timestamp="20240503123456",
    )
    write_archive_index(tmp_path, doc)

    read = cites("https://a.example/1")
    read_archive_index(tmp_path, read)
    assert read.archives == doc.archives


def test_the_record_is_sorted_so_two_builds_write_the_same_bytes(tmp_path: Path) -> None:
    """The file is committed and compared against a fresh build."""
    doc = cites("https://b.example/2", "https://a.example/1")
    for url in doc.sources:
        doc.archives[url] = Archived(snapshot=f"snap {url}", timestamp="20240503123456")
    write_archive_index(tmp_path, doc)
    written = json.loads((tmp_path / ARCHIVES_JSON).read_text())
    assert list(written) == sorted(written)


def test_only_what_the_report_still_cites_is_written(tmp_path: Path) -> None:
    """A URL a draft dropped is not something the report stands on any more."""
    doc = cites("https://a.example/1")
    doc.archives["https://dropped.example/"] = Archived(snapshot="snap", timestamp="20240503")
    doc.archives["https://a.example/1"] = Archived(snapshot="snap", timestamp="20240503")
    write_archive_index(tmp_path, doc)
    assert list(json.loads((tmp_path / ARCHIVES_JSON).read_text())) == ["https://a.example/1"]


def test_what_the_document_itself_says_wins_over_the_record(tmp_path: Path) -> None:
    doc = cites("https://a.example/1")
    doc.archives["https://a.example/1"] = Archived(snapshot="recorded", timestamp="20200101")
    write_archive_index(tmp_path, doc)

    fresh = cites("https://a.example/1")
    fresh.archives["https://a.example/1"] = Archived(snapshot="from the doc", timestamp="20260101")
    read_archive_index(tmp_path, fresh)
    assert fresh.archives["https://a.example/1"].snapshot == "from the doc"


def test_a_failed_capture_is_not_tried_again() -> None:
    doc = cites("https://a.example/1", "https://b.example/2")
    doc.archives["https://a.example/1"] = Archived(timestamp="20260101", error="cannot be captured")
    assert missing(doc) == ["https://b.example/2"]


def test_a_failure_recorded_about_the_moment_is_tried_again() -> None:
    """Recorded before `error:no-request` was known to be about the moment,
    the Harsimus Cove photo would otherwise never have been asked about again."""
    doc = cites("https://a.example/1")
    doc.archives["https://a.example/1"] = Archived(
        timestamp="20261012", error="error:no-request", job="job-1"
    )
    assert missing(doc) == ["https://a.example/1"]


def test_each_step_of_a_capture_is_said_while_it_is_waited_on(no_waiting: None) -> None:
    said: list[str] = []
    archive._SAYING.say = said.append
    try:
        session = Saving(
            [
                {"job_id": "job-5"},
                {"status": "pending"},
                {"status": "success", "timestamp": "20261012000000"},
            ]
        )
        archive._submit(session, {"Authorization": "LOW a:b"}, "https://a.example/5")
    finally:
        archive._SAYING.say = None
    assert said == [
        "queued to capture",
        "asking to capture",
        "capture asked",
        "capture pending",
        "capture success",
    ]


def test_a_job_save_page_now_cannot_find_is_not_the_pages_answer(no_waiting: None) -> None:
    session = Saving([{"job_id": "job-4"}, {"status": "error", "status_ext": "error:no-request"}])
    with pytest.raises(archive.Busy):
        archive._submit(session, {"Authorization": "LOW a:b"}, "https://a.example/4")


# ---- what the service says --------------------------------------------


@pytest.fixture(autouse=True)
def impatient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ask once and take the answer.

    A real build waits and asks again, because being told to slow down is not
    an answer. A test that did would spend 85 seconds finding that out.
    """
    monkeypatch.setattr(archive, "PATIENCE", ())


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keys in the environment, so these test the capture rather than their absence."""
    monkeypatch.setenv(archive.ACCESS_KEY, "access")
    monkeypatch.setenv(archive.SECRET_KEY, "secret")


class Answering(requests.Session):
    """A session that answers every request with one canned status and body."""

    def __init__(self, status: int, body: object = None) -> None:
        super().__init__()
        self.status = status
        self.body = body

    @override
    # The signature is narrowed on purpose: nothing here reads the arguments.
    def request(self, *args: object, **kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = self.status
        response.url = "https://archive.org/asked"
        response._content = json.dumps(self.body or {}).encode()
        return response


def pending(doc: Document) -> dict[str, str]:
    """The sources published as not archived for now, by the reason shown."""
    return {url: a.error for url, a in doc.archives.items() if a.pending}


def test_being_told_to_slow_down_is_not_an_answer_about_the_page(keyed: None) -> None:
    """A rate limit publishes the source as not archived for now,
    and the next build asks again."""
    doc = cites("https://a.example/1")
    archive.capture(doc, session=Answering(429))
    assert pending(doc) == {"https://a.example/1": archive.NO_ANSWER}
    assert missing(doc) == ["https://a.example/1"]
    archive.check_pending(doc)
    assert any("could not archive" in str(w) for w in doc.warnings)


def test_a_capture_somebody_else_already_made_is_used(keyed: None) -> None:
    doc = cites("https://a.example/1")
    session = Answering(200, [["timestamp"], ["20240503123456"]])
    assert archive.capture(doc, session=session) == (1, 0)
    assert doc.archives["https://a.example/1"].timestamp == "20240503123456"


def test_a_server_error_is_not_recorded_as_a_fact_about_the_source(keyed: None) -> None:
    doc = cites("https://a.example/1")
    archive.capture(doc, session=Answering(503))
    assert pending(doc) == {"https://a.example/1": archive.NO_ANSWER}


def test_without_keys_what_is_already_archived_is_still_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Looking one up needs no account; only asking for a new one does."""
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)
    doc = cites("https://a.example/1")
    found, submitted = archive.capture(
        doc, session=Answering(200, [["timestamp"], ["20240503123456"]])
    )
    assert (found, submitted) == (1, 0)
    assert doc.archives["https://a.example/1"].timestamp == "20240503123456"


def test_without_keys_a_source_with_no_capture_is_left_for_a_build_that_can_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)
    doc = cites("https://a.example/1")
    assert archive.capture(doc, session=Answering(200, [["timestamp"]])) == (0, 0)
    assert doc.archives == {}
    assert missing(doc) == ["https://a.example/1"]


def ia_ini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "ia.ini"
    path.write_text(text)
    monkeypatch.setenv(archive.IA_CONFIG, str(path))


def test_without_keys_in_the_environment_the_ia_config_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)
    ia_ini(tmp_path, monkeypatch, "[s3]\naccess = from-ia\nsecret = shh\n")
    assert archive._keys() == {
        "Accept": "application/json",
        "Authorization": "LOW from-ia:shh",
    }


def test_keys_in_the_environment_come_before_the_ia_config(
    keyed: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ia_ini(tmp_path, monkeypatch, "[s3]\naccess = from-ia\nsecret = shh\n")
    keys = archive._keys()
    assert keys is not None
    assert keys["Authorization"] == "LOW access:secret"


def test_an_ia_config_without_keys_is_no_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)
    ia_ini(tmp_path, monkeypatch, "not an ini file\n")
    assert archive._keys() is None


class Refusing(Answering):
    """An `Answering` that refuses the connection the first `refusals` times."""

    def __init__(self, refusals: int, status: int, body: object = None) -> None:
        super().__init__(status, body)
        self.refusals = refusals

    @override
    def request(self, *args: object, **kwargs: object) -> requests.Response:
        if self.refusals:
            self.refusals -= 1
            raise requests.ConnectionError("refused")
        return super().request(*args, **kwargs)


def test_a_refused_connection_is_asked_again(keyed: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Being refused is how `web.archive.org` says to slow down when it says nothing."""
    monkeypatch.setattr(archive, "PATIENCE", (timedelta(0),))
    doc = cites("https://a.example/1")
    session = Refusing(1, 200, [["timestamp"], ["20240503123456"]])
    assert archive.capture(doc, session=session) == (1, 0)


def test_a_source_the_archive_could_not_be_asked_about_does_not_stop_the_build(
    keyed: None,
) -> None:
    """A capture can still be running a day later, and a report held back
    that long over one source is a report nobody can publish."""
    doc = cites("https://a.example/1", "https://b.example/2")
    archive.capture(doc, session=Refusing(1_000, 200))
    assert pending(doc) == {
        "https://a.example/1": archive.NO_ANSWER,
        "https://b.example/2": archive.NO_ANSWER,
    }


def test_a_source_the_archive_could_not_be_asked_about_says_why(keyed: None) -> None:
    doc = cites("https://a.example/1")
    archive.capture(doc, session=Refusing(1_000, 200))
    archive.check_pending(doc)
    assert any("https://a.example/1" in str(w) and "(refused)" in str(w) for w in doc.warnings)

    # The same from the record alone, which is all an offline build has.
    offline = cites("https://a.example/1")
    offline.archives = dict(doc.archives)
    archive.check_pending(offline)
    assert list(map(str, offline.warnings)) == list(map(str, doc.warnings))


def test_a_source_still_waiting_keeps_the_date_it_first_waited(keyed: None) -> None:
    """Otherwise the page would change on every build over the same answer."""
    doc = cites("https://a.example/1")
    doc.archives["https://a.example/1"] = Archived(
        timestamp="20261001", error=archive.NO_ANSWER, pending=True
    )
    archive.capture(doc, session=Answering(503))
    assert doc.archives["https://a.example/1"].timestamp == "20261001"


def test_a_pending_source_is_written_down_as_pending(keyed: None, tmp_path: Path) -> None:
    """So an offline build publishes it the same, and an online one asks again."""
    doc = cites("https://a.example/1")
    archive.capture(doc, session=Answering(503))
    archive.write_archive_index(tmp_path, doc)
    again = cites("https://a.example/1")
    archive.read_archive_index(tmp_path, again)
    assert again.archives == doc.archives
    assert missing(again) == ["https://a.example/1"]


@pytest.mark.parametrize("when", ["submitted", "polled"])
def test_a_refusal_about_the_moment_says_all_the_service_said(no_waiting: None, when: str) -> None:
    refused = {
        "status": "error",
        "status_ext": "error:too-many-daily-captures",
        "message": "This URL has been already captured 1 times today.",
    }
    answers = [refused] if when == "submitted" else [{"job_id": "job-1"}, refused]
    with pytest.raises(archive.Busy) as busy:
        archive._submit(Saving(answers), {"Authorization": "LOW a:b"}, "https://a.example/1")
    expected = "error:too-many-daily-captures: This URL has been already captured 1 times today."
    if when == "polled":
        expected += " (job job-1)"
    assert str(busy.value) == expected


# ---- a source that is already an Internet Archive item ---------------


class Item(requests.Session):
    """The metadata API, answering with `body` for any identifier."""

    def __init__(self, body: object) -> None:
        super().__init__()
        self.body = body
        self.wayback_asked = 0

    @override
    def request(self, method: object, url: object, *args: object, **kwargs: object):
        response = requests.Response()
        response.url = str(url)
        if not str(url).startswith(archive.METADATA):
            # `archive.org` excludes its own pages from the Wayback Machine,
            # so anything asked there about one of these answers `403`.
            self.wayback_asked += 1
            response.status_code = 403
            return response
        response.status_code = 200
        response._content = json.dumps(self.body).encode()
        return response


def test_an_item_is_archived_at_itself_the_day_it_was_added() -> None:
    """It cannot be captured and does not need to be: it is the preserved copy."""
    doc = cites("https://archive.org/details/slurrywallsasstr0000xant/page/34/mode/2up")
    session = Item({"metadata": {"addeddate": "2023-05-04 00:51:39"}})
    assert archive.capture(doc, session=session) == (1, 0)
    archived = doc.archives["https://archive.org/details/slurrywallsasstr0000xant/page/34/mode/2up"]
    assert archived.timestamp == "20230504005139"
    assert archived.date == "May 4, 2023"
    assert session.wayback_asked == 0


def test_a_capture_date_writes_its_month_in_three_letters() -> None:
    """So a list of them is one width, rather than as wide as `September`."""
    assert Archived(timestamp="20260902181426").date == "Sep 2, 2026"


def test_a_failed_capture_is_shown_without_its_error_prefix() -> None:
    assert Archived(error="error:blocked-url").reason == "blocked-url"


def test_the_archived_copy_is_the_page_that_was_cited() -> None:
    """`/page/34/mode/2up` is the page the claim is about, not the front matter."""
    url = "https://archive.org/details/slurrywallsasstr0000xant/page/34/mode/2up"
    doc = cites(url)
    archive.capture(doc, session=Item({"metadata": {"addeddate": "2023-05-04 00:51:39"}}))
    assert doc.archives[url].snapshot == url


def test_public_date_stands_in_where_an_item_has_no_added_date() -> None:
    """The day it became readable, which is the nearest thing left."""
    url = "https://archive.org/details/something"
    doc = cites(url)
    archive.capture(doc, session=Item({"metadata": {"publicdate": "2023-03-29 19:29:10"}}))
    assert doc.archives[url].timestamp == "20230329192910"


def test_an_item_that_says_no_date_is_left_to_the_next_build() -> None:
    """Learning nothing is not the same as there being no archive."""
    doc = cites("https://archive.org/details/something")
    archive.capture(doc, session=Item({"metadata": {"addeddate": "0000-00-00"}}))
    assert doc.archives == {}


def test_an_identifier_nothing_holds_is_not_recorded() -> None:
    """The API answers `{}` rather than saying so."""
    doc = cites("https://archive.org/details/nothing-is-here")
    archive.capture(doc, session=Item({}))
    assert doc.archives == {}


def test_an_archive_org_url_that_is_not_an_item_is_an_ordinary_source() -> None:
    """`archive.org/about` is a page like any other, and can be captured."""
    doc = cites("https://archive.org/about")
    session = Replaying([("20240503123456", 200)])
    archive.capture(doc, session=session)
    assert doc.archives["https://archive.org/about"].timestamp == "20240503123456"


# ---- asking the replay before the index ------------------------------


class Replaying(requests.Session):
    """A replay that has `captures`, newest last, each with the status it serves.

    The index answers separately, from `rows`, so a test can say what each of
    the two would say and check which one was believed.
    """

    def __init__(self, captures: list[tuple[str, int]], rows: object = None) -> None:
        super().__init__()
        self.captures = captures
        self.rows = rows
        self.index_asked = 0
        self.index_params: dict[str, object] = {}
        self.content_type = "text/html"

    @override
    def request(self, method: object, url: object, *args: object, **kwargs: object):
        response = requests.Response()
        response.url = str(url)
        asked = str(url)
        if asked.startswith(archive.INDEX):
            self.index_asked += 1
            self.index_params = cast("dict[str, object]", kwargs.get("params"))
            response.status_code = 200
            response._content = json.dumps(self.rows or [["timestamp"]]).encode()
            return response
        if not self.captures:
            response.status_code = 404
            return response
        stamp, status = self.captures[-1]
        if f"/web/{archive.NEWEST}/" in asked:
            response.status_code = 302
            response.headers["location"] = f"{archive.REPLAY}/{stamp}/whatever"
            return response
        response.status_code = status
        response.headers["content-type"] = self.content_type
        return response


def test_a_capture_the_replay_serves_is_taken_without_asking_the_index(keyed: None) -> None:
    """Two `HEAD`s at 200 ms beat one query that took 0.5s to 31s."""
    doc = cites("https://a.example/1")
    session = Replaying([("20240503123456", 200)])
    assert archive.capture(doc, session=session) == (1, 0)
    assert doc.archives["https://a.example/1"].timestamp == "20240503123456"
    assert session.index_asked == 0


def test_the_snapshot_is_the_url_this_publishes(keyed: None) -> None:
    """Built from the timestamp, not taken from the redirect.

    The two differ over percent-encoding, and the record is committed and
    compared against a fresh build byte for byte.
    """
    doc = cites("https://a.example/1")
    archive.capture(doc, session=Replaying([("20240503123456", 200)]))
    assert doc.archives["https://a.example/1"].snapshot == (
        "https://web.archive.org/web/20240503123456/https://a.example/1"
    )


def test_a_capture_that_is_not_the_page_falls_back_to_the_index(keyed: None) -> None:
    """The NYT's newest capture replays `403`, and the newest that was the page
    is a different question only the index can answer."""
    doc = cites("https://a.example/1")
    session = Replaying([("20260913083748", 403)], rows=[["timestamp"], ["20260101035028"]])
    assert archive.capture(doc, session=session) == (1, 0)
    assert doc.archives["https://a.example/1"].timestamp == "20260101035028"
    assert session.index_asked == 1


def test_no_capture_at_all_is_confirmed_with_the_index(
    keyed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `404` from the replay is not taken as the answer.

    Nothing is written down without the index saying so, because `not archived`
    is what a report publishes.
    """
    refused = Archived(timestamp="20260913", error="no")

    def refuse(*args: object) -> Archived:
        return refused

    monkeypatch.setattr(archive, "_submit", refuse)
    doc = cites("https://a.example/1")
    session = Replaying([])
    archive.capture(doc, session=session)
    assert session.index_asked == 1


class Overlapping(Replaying):
    """A `Replaying` that notes the most replay lookups it had in flight at once."""

    def __init__(self, captures: list[tuple[str, int]]) -> None:
        super().__init__(captures)
        self.lock = threading.Lock()
        self.in_flight = 0
        self.most = 0

    @override
    def request(self, method: object, url: object, *args: object, **kwargs: object):
        with self.lock:
            self.in_flight += 1
            self.most = max(self.most, self.in_flight)
        try:
            # Long enough for every thread that could get in to have got in.
            time.sleep(0.01)
            return super().request(method, url, *args, **kwargs)
        finally:
            with self.lock:
                self.in_flight -= 1


def test_reports_built_at_once_share_the_replay_limit(
    keyed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each report has its own pool, so the limit has to be wider than any one of them."""
    monkeypatch.setattr(archive, "_REPLAYING", threading.Semaphore(2))
    session = Overlapping([("20240503123456", 200)])
    docs = [cites(*(f"https://{report}.example/{n}" for n in range(6))) for report in "abc"]
    with ThreadPoolExecutor(max_workers=len(docs)) as pool:
        for answer in [pool.submit(archive.capture, doc, session=session) for doc in docs]:
            assert answer.result() == (6, 0)
    assert session.most == 2


# ---- not asking again about the same nothing -------------------------


class Counting(Answering):
    """An `Answering` that says how many requests it was sent."""

    def __init__(self, status: int, body: object = None) -> None:
        super().__init__(status, body)
        self.asked = 0

    @override
    def request(self, *args: object, **kwargs: object) -> requests.Response:
        self.asked += 1
        return super().request(*args, **kwargs)


@pytest.fixture
def unkeyed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No keys, which is the case the cache is for."""
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)


def test_the_index_is_not_asked_again_the_same_week(unkeyed: None) -> None:
    """The slow half of a build, spent to write down the same nothing twice."""
    doc = cites("https://a.example/1")
    session = Replaying([])
    archive.capture(doc, session=session)
    assert session.index_asked == 1
    archive.capture(cites("https://a.example/1"), session=session)
    assert session.index_asked == 1, "the index was asked again inside the week"


def test_the_replay_is_held_back_for_an_hour(unkeyed: None) -> None:
    """Running `eta-publish all` twice in a row should not ask the same question
    twice, and the second run within the hour asks the archive nothing."""
    archive.capture(cites("https://a.example/1"), session=Replaying([]))
    session = Replaying([("20240503123456", 200)])
    doc = cites("https://a.example/1")
    assert archive.capture(doc, session=session) == (0, 0)
    assert doc.archives == {}
    assert session.index_asked == 0


def test_the_replay_is_asked_again_once_the_hour_is_up(unkeyed: None) -> None:
    """An hour rather than the index's week, because the replay is the half that
    finds a new capture: held back for a week, a source would publish as
    unarchived long after it was not, which is what `masstransitmag.com` did."""
    archive.capture(cites("https://a.example/1"), session=Replaying([]))
    path = archive.archive_cache_path()
    cached = json.loads(path.read_text())
    stale = datetime.now(UTC) - archive.REPLAY_LIFETIME - timedelta(seconds=1)
    cached["replay"]["https://a.example/1"] = stale.isoformat(timespec="seconds")
    path.write_text(json.dumps(cached))
    session = Replaying([("20240503123456", 200)])
    doc = cites("https://a.example/1")
    assert archive.capture(doc, session=session) == (1, 0)
    assert doc.archives["https://a.example/1"].timestamp == "20240503123456"
    assert session.index_asked == 0


def test_an_hour_of_holding_back_does_not_renew_itself(unkeyed: None) -> None:
    """The time is when the replay was asked, not when it was skipped.

    Refreshed on a build that never asked, the entry would never reach an hour old.
    """
    archive.capture(cites("https://a.example/1"), session=Replaying([]))
    cached = json.loads(archive.archive_cache_path().read_text())["replay"]
    archive.capture(cites("https://a.example/1"), session=Replaying([]))
    assert json.loads(archive.archive_cache_path().read_text())["replay"] == cached


def test_a_week_of_holding_back_does_not_renew_itself(unkeyed: None) -> None:
    """The date is the day the index said so, not the day it was skipped.

    Refreshed on a build that never asked, the entry would be a week old
    forever and the index would never be asked again.
    """
    archive.capture(cites("https://a.example/1"), session=Replaying([]))
    cached = json.loads(archive.archive_cache_path().read_text())["index"]
    archive.capture(cites("https://a.example/1"), session=Replaying([]))
    assert json.loads(archive.archive_cache_path().read_text())["index"] == cached


def test_it_is_looked_up_again_once_the_week_is_up(
    unkeyed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = cites("https://a.example/1")
    session = Counting(200, [["timestamp"]])
    archive.capture(doc, session=session)
    asked = session.asked
    monkeypatch.setitem(archive.LIFETIMES, "index", timedelta())
    archive.capture(cites("https://a.example/1"), session=session)
    assert session.asked > asked


def test_what_the_cache_holds_back_is_still_counted_as_unarchived(unkeyed: None) -> None:
    """The count a person reads is how many sources have no capture.

    Not how many were asked about today: a build that said `0 sources` because
    it skipped them all would be reporting on its own cache.
    """
    doc = cites("https://a.example/1")
    archive.capture(doc, session=Answering(200, [["timestamp"]]))
    again = cites("https://a.example/1")
    archive.capture(again, session=Answering(200, [["timestamp"]]))
    assert missing(again) == ["https://a.example/1"]


def test_being_told_to_slow_down_is_not_cached(unkeyed: None) -> None:
    """Nothing was learned, so there is nothing to remember for a week."""
    doc = cites("https://a.example/1")
    session = Counting(429)
    archive.capture(doc, session=session)
    asked = session.asked
    archive.capture(cites("https://a.example/1"), session=session)
    assert session.asked > asked


def test_with_keys_nothing_is_held_back(keyed: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """A source with no capture is submitted, so it leaves `missing` either way.

    So a build that has keys asks the index however recently one without them
    looked, and the capture gets made rather than waiting out the week.
    """
    refused = Archived(timestamp="20260913", error="no")

    def refuse(*args: object) -> Archived:
        return refused

    monkeypatch.setattr(archive, "_submit", refuse)
    archive._remember({"index": ["https://a.example/1"]})
    session = Replaying([])
    archive.capture(cites("https://a.example/1"), session=session)
    assert session.index_asked == 1


def test_a_cache_that_cannot_be_read_is_an_empty_one(
    unkeyed: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A truncated write is a slower build, not a failed one."""
    broken = tmp_path / "archive.json"
    broken.write_text("{not json")
    monkeypatch.setenv(archive.ARCHIVE_CACHE, str(broken))
    session = Counting(200, [["timestamp"]])
    archive.capture(cites("https://a.example/1"), session=session)
    assert session.asked


# ---- a link to a page of a PDF ---------------------------------------


def test_pages_of_one_pdf_are_one_document_to_capture() -> None:
    """A fragment never reaches a server, so there is one file to ask for."""
    doc = cites(
        "https://a.example/report.pdf#page=28",
        "https://a.example/report.pdf#page=5",
        "https://a.example/report.pdf",
    )
    assert len(doc.sources) == 3
    assert missing(doc) == ["https://a.example/report.pdf"]


def test_every_page_of_a_pdf_shares_the_one_capture(keyed: None) -> None:
    doc = cites("https://a.example/report.pdf#page=28", "https://a.example/report.pdf#page=5")
    session = Answering(200, [["timestamp"], ["20240503123456"]])
    assert archive.capture(doc, session=session) == (1, 0)


def test_the_archived_copy_opens_on_the_page_that_was_cited() -> None:
    doc = cites("https://a.example/report.pdf#page=28")
    doc.archives["https://a.example/report.pdf"] = Archived(
        snapshot="https://web.archive.org/web/20240503123456/https://a.example/report.pdf",
        timestamp="20240503123456",
    )
    archived = doc.archived("https://a.example/report.pdf#page=28")
    assert archived is not None
    assert archived.snapshot.endswith("/https://a.example/report.pdf#page=28")


def test_a_hand_written_snapshot_of_a_page_is_recorded_as_the_document() -> None:
    original, archived = unwrap_snapshot(
        "https://web.archive.org/web/20240503123456/https://a.example/report.pdf#page=50"
    )
    assert original == "https://a.example/report.pdf#page=50"
    assert archived is not None
    assert archived.snapshot == (
        "https://web.archive.org/web/20240503123456/https://a.example/report.pdf"
    )


def test_a_page_of_a_pdf_is_asked_for_raw() -> None:
    """The ordinary Wayback URL for a PDF is an HTML page carrying the toolbar,
    so `#page=50` lands on a wrapper that has no page 50."""
    doc = cites("https://a.example/report.pdf#page=50")
    doc.archives["https://a.example/report.pdf"] = Archived(
        snapshot="https://web.archive.org/web/20240503123456/https://a.example/report.pdf",
        timestamp="20240503123456",
    )
    archived = doc.archived("https://a.example/report.pdf#page=50")
    assert archived is not None
    assert archived.snapshot == (
        "https://web.archive.org/web/20240503123456id_/https://a.example/report.pdf#page=50"
    )


def test_an_anchor_in_a_page_is_left_on_the_ordinary_capture() -> None:
    """An HTML capture is the document itself, toolbar and rewritten assets included."""
    doc = cites("https://a.example/article#grades")
    doc.archives["https://a.example/article"] = Archived(
        snapshot="https://web.archive.org/web/20240503123456/https://a.example/article",
        timestamp="20240503123456",
    )
    archived = doc.archived("https://a.example/article#grades")
    assert archived is not None
    assert archived.snapshot == (
        "https://web.archive.org/web/20240503123456/https://a.example/article#grades"
    )


def test_a_request_that_never_arrived_says_nothing_about_the_source(keyed: None) -> None:
    """A read timeout is about reaching `web.archive.org`, not about the page.

    Recorded as a failed capture it would leave that source with no archive
    for good, which is what happened to a Wikipedia article that has been
    captured hundreds of times.
    """

    class Timing(requests.Session):
        @override
        def request(self, *args: object, **kwargs: object) -> requests.Response:
            raise requests.Timeout("read timed out")

    doc = cites("https://a.example/1")
    archive.capture(doc, session=Timing())
    assert pending(doc) == {"https://a.example/1": archive.NO_ANSWER}
    assert missing(doc) == ["https://a.example/1"]


def test_being_told_to_slow_down_is_asked_again(
    keyed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two `429`s and then an answer, which is the shape a real build meets."""
    monkeypatch.setattr(archive, "PATIENCE", (timedelta(),) * 3)
    answers = [429, 429, 200]

    class Relenting(requests.Session):
        @override
        def request(self, *args: object, **kwargs: object) -> requests.Response:
            response = requests.Response()
            response.status_code = answers.pop(0) if answers else 200
            response.url = "https://web.archive.org/asked"
            response._content = json.dumps([["timestamp"], ["20240503123456"]]).encode()
            return response

    doc = cites("https://a.example/1")
    assert archive.capture(doc, session=Relenting()) == (1, 0)
    assert doc.archives["https://a.example/1"].timestamp == "20240503123456"


def test_being_stopped_says_what_it_was_waiting_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Ctrl+C` in the middle of the archiving is answered with how far it got
    and which sources it is still asking about, rather than with a traceback
    through the machinery that was waiting."""
    doc = cites("https://example.com/one", "https://example.com/two")

    def looked_up(*_args: object, **_kwargs: object) -> archive.Lookup:
        return archive.Lookup()

    monkeypatch.setattr(archive, "_archive", looked_up)

    def interrupt() -> None:
        raise KeyboardInterrupt

    with pytest.raises(archive.Stopped) as stopped:
        archive.capture(doc, along=interrupt)
    assert "of 2 sources" in str(stopped.value)
    assert isinstance(stopped.value, KeyboardInterrupt)


class Saving(requests.Session):
    """Save Page Now answering each request in turn from `answers`.

    An `int` in place of an answer is a status with no body, for the service
    failing that one request. Counts the submissions, which is what a test of
    capturing a page only once is about.
    """

    def __init__(self, answers: Sequence[dict[str, str] | int]) -> None:
        super().__init__()
        self.answers = list(answers)
        self.submitted = 0

    @override
    def request(self, method: object, url: object, *args: object, **kwargs: object):
        if method == "POST":
            self.submitted += 1
        response = requests.Response()
        response.url = str(url)
        nothing: dict[str, str] = {}
        answer = self.answers.pop(0) if self.answers else nothing
        response.status_code = answer if isinstance(answer, int) else 200
        response._content = b"" if isinstance(answer, int) else json.dumps(answer).encode()
        return response


@pytest.fixture
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    def instantly(_seconds: float) -> None:
        return None

    monkeypatch.setattr(archive, "PATIENCE", (timedelta(),) * 3)
    monkeypatch.setattr(archive.time, "sleep", instantly)


@pytest.mark.parametrize("refusal", archive.RETRY_LATER)
@pytest.mark.parametrize("when", ["submitted", "polled"])
def test_a_refusal_about_the_moment_is_not_written_down(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch, refusal: str, when: str
) -> None:
    """`too-many-daily-captures` was recorded against four sources for good, after
    a day of builds that could not yet see their own captures used it up.

    Nor submitted again: each submission is a capture, and the daily limit
    is one capture of a PDF, so asking again only ever hears the refusal."""

    def nothing(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(archive, "_existing", nothing)
    refused = {"status": "error", "status_ext": refusal}
    job = {"job_id": "job-1"}
    session = Saving(([refused] if when == "submitted" else [job, refused]) * 4)
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.unanswered
    assert lookup.archived is None
    assert session.submitted == 1


def test_a_status_poll_that_fails_does_not_submit_the_page_again(no_waiting: None) -> None:
    """The capture is still going: a second submission is a second capture."""
    session = Saving(
        [{"job_id": "job-1"}, 503, 503, {"status": "success", "timestamp": "20261009120000"}]
    )
    captured = archive._submit(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert captured.timestamp == "20261009120000"
    assert session.submitted == 1


def test_a_capture_keeps_its_job(no_waiting: None) -> None:
    """In the cache the moment it is given, and on the record once it answers."""
    session = Saving([{"job_id": "job-1"}, {"status": "success", "timestamp": "20261009120000"}])
    captured = archive._submit(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert captured.job == "job-1"
    jobs = json.loads(archive.archive_cache_path().read_text())["jobs"]
    assert list(jobs["https://a.example/1"]) == ["job-1"]


def test_a_failed_capture_keeps_its_job(no_waiting: None) -> None:
    refused = {"status": "error", "status_ext": "error:not-found"}
    session = Saving([{"job_id": "job-2"}, refused])
    captured = archive._submit(session, {"Authorization": "LOW a:b"}, "https://a.example/2")
    assert (captured.error, captured.job) == ("error:not-found", "job-2")


def test_a_refused_capture_keeps_its_job_in_the_cache(no_waiting: None) -> None:
    """The build stops over this one, so the cache is the only place the job is kept."""
    refused = {"status": "error", "status_ext": "error:too-many-daily-captures"}
    session = Saving([{"job_id": "job-3"}, refused])
    with pytest.raises(archive.Busy):
        archive._submit(session, {"Authorization": "LOW a:b"}, "https://a.example/3")
    jobs = json.loads(archive.archive_cache_path().read_text())["jobs"]
    assert "job-3" in jobs["https://a.example/3"]


def test_remembering_lookups_keeps_the_jobs(no_waiting: None) -> None:
    archive._remember_job("https://a.example/4", "job-4")
    archive._remember({"index": ["https://a.example/5"], "replay": []})
    cached = json.loads(archive.archive_cache_path().read_text())
    assert "job-4" in cached["jobs"]["https://a.example/4"]
    assert "https://a.example/5" in cached["index"]


def _found_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def nothing(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(archive, "_existing", nothing)


def test_a_recorded_job_that_worked_is_the_capture(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked about rather than submitted again: the capture it made may be
    filed under where the source redirected, where no lookup finds it."""
    _found_nothing(monkeypatch)
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving([{"status": "success", "timestamp": "20261010114910"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.archived is not None
    assert (lookup.archived.timestamp, lookup.archived.job) == ("20261010114910", "job-1")
    assert session.submitted == 0


def test_a_recorded_job_still_running_is_not_submitted_again(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _found_nothing(monkeypatch)
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving([{"status": "pending"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.unanswered
    assert "job-1" in lookup.why
    assert session.submitted == 0


def test_a_recorded_job_refused_about_the_page_is_the_answer(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _found_nothing(monkeypatch)
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving([{"status": "error", "status_ext": "error:not-found"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.archived is not None
    assert (lookup.archived.error, lookup.archived.job) == ("error:not-found", "job-1")
    assert session.submitted == 0


def test_a_recorded_job_refused_about_the_moment_is_asked_for_again(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _found_nothing(monkeypatch)
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving(
        [
            {"status": "error", "status_ext": "error:user-session-limit"},
            {"job_id": "job-2"},
            {"status": "success", "timestamp": "20261011000000"},
        ]
    )
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.archived is not None
    assert lookup.archived.job == "job-2"
    assert session.submitted == 1


def test_a_capture_is_asked_for_at_most_once_a_day(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counted when it is asked for, refused or not: the refusal is the daily limit."""
    _found_nothing(monkeypatch)
    refused = {"status": "error", "status_ext": "error:too-many-daily-captures"}
    session = Saving([refused, refused])
    headers = {"Authorization": "LOW a:b"}
    first = archive._archive(session, headers, "https://a.example/1")
    second = archive._archive(session, headers, "https://a.example/1")
    assert session.submitted == 1
    assert first.unanswered
    assert (second.unanswered, second.short) == (True, archive.ASKED_LATELY)


def test_a_job_save_page_now_lost_is_not_captured_again_within_the_day(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Harsimus Cove photo: its job answered `error:no-request`, which is about
    the moment, so it is asked for again, but not before the day is out."""
    _found_nothing(monkeypatch)
    archive._remember_request("https://a.example/1")
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving([{"status": "error", "status_ext": "error:no-request"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert session.submitted == 0
    assert (lookup.unanswered, lookup.short) == (True, archive.ASKED_LATELY)


def test_a_capture_is_asked_for_again_the_next_day(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _found_nothing(monkeypatch)
    archive._remember_request("https://a.example/1")
    monkeypatch.setattr(archive, "REQUEST_EVERY", timedelta())
    session = Saving([{"job_id": "job-1"}, {"status": "success", "timestamp": "20261011000000"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.archived is not None
    assert session.submitted == 1


def test_a_recorded_job_is_still_asked_about_within_the_day(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking about a job is not asking for a capture."""
    _found_nothing(monkeypatch)
    archive._remember_request("https://a.example/1")
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving([{"status": "success", "timestamp": "20261010114910"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert lookup.archived is not None
    assert lookup.archived.timestamp == "20261010114910"
    assert session.submitted == 0


def test_a_capture_still_running_is_not_asked_of_the_index(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index is the slow one; the job says in one request that it is still going."""
    asked: list[bool] = []

    def existing(*_args: object, index: bool = True, **_kwargs: object) -> None:
        asked.append(index)

    monkeypatch.setattr(archive, "_existing", existing)
    archive._remember_job("https://a.example/1", "job-1")
    session = Saving([{"status": "pending"}])
    lookup = archive._archive(session, {"Authorization": "LOW a:b"}, "https://a.example/1")
    assert (lookup.unanswered, lookup.short) == (True, archive.STILL_RUNNING)
    assert asked == [False]


def test_a_source_waiting_for_tomorrow_keeps_what_it_last_heard(keyed: None) -> None:
    """Not replaced by "asked for today", which would say less and change the page."""
    doc = cites("https://a.example/1")
    before = Archived(
        timestamp="20261010", error="error:too-many-daily-captures", pending=True, said="x"
    )
    doc.archives["https://a.example/1"] = before
    archive._remember_request("https://a.example/1")
    archive.capture(doc, session=Answering(200, [["timestamp"]]))
    assert doc.archives["https://a.example/1"] == before


def test_an_anonymous_capture_is_asked_for_at_most_once_a_day(anonymous: None) -> None:
    session = SavingAnonymously(429)
    archive.capture(cites("https://a.example/1"), session=session)
    archive.capture(cites("https://a.example/1"), session=session)
    assert len(session.saved) == 1


def test_a_job_older_than_its_lifetime_is_taken_as_lost(
    no_waiting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save Page Now answers `pending` for a job it never heard of."""
    archive._remember_job("https://a.example/1", "job-1")
    monkeypatch.setattr(archive, "JOB_LIFETIME", timedelta())
    assert archive._recorded_job("https://a.example/1") is None


def test_a_build_with_keys_captures_only_what_has_no_capture(keyed: None) -> None:
    """A capture is somebody else's page fetch, and asking for one of a page the
    archive already holds spends it on nothing: the lookup comes first."""
    posted: list[str] = []

    class Watching(Replaying):
        @override
        def request(self, method: object, url: object, *args: object, **kwargs: object):
            if str(url).startswith(archive.SAVE):
                posted.append(str(url))
            return super().request(method, url, *args, **kwargs)

    doc = cites("https://a.example/1")
    assert archive.capture(doc, session=Watching([("20240503123456", 200)])) == (1, 0)
    assert posted == []


def _pdf(pages: int) -> bytes:
    """A PDF of `pages` blank pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


class Serving(requests.Session):
    """A session that answers each URL with its own body, and 404 for any other."""

    def __init__(self, bodies: dict[str, bytes]) -> None:
        super().__init__()
        self.bodies = bodies
        self.asked: list[str] = []

    @override
    def request(
        self, method: object, url: object, *args: object, **kwargs: object
    ) -> requests.Response:
        self.asked.append(str(url))
        response = requests.Response()
        response.url = str(url)
        body = self.bodies.get(str(url))
        response.status_code = 404 if body is None else 200
        response._content = body or b""
        return response


CAPTURED = Archived(
    snapshot="https://web.archive.org/web/20240503123456/https://a.example/a.pdf",
    timestamp="20240503123456",
)


def test_a_pdf_cited_by_page_is_counted_from_its_raw_capture() -> None:
    doc = cites("https://a.example/a.pdf#page=2", "https://a.example/a.pdf#page=3")
    doc.archives["https://a.example/a.pdf"] = CAPTURED
    raw = "https://web.archive.org/web/20240503123456id_/https://a.example/a.pdf"
    session = Serving({raw: _pdf(6)})
    assert archive.count_pages(doc, session=session) == 1
    assert doc.archives["https://a.example/a.pdf"].pages == 6
    # One document, counted once, however many of its pages are cited.
    assert session.asked == [raw]


def test_a_recorded_capture_that_is_not_the_pdf_is_dropped() -> None:
    """The capture of `TCP_Final_Report.pdf` is a bot check, not the report.

    Dropped, the next lookup finds a capture that is the PDF.
    """
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = CAPTURED
    raw = "https://web.archive.org/web/20240503123456id_/https://a.example/a.pdf"
    assert archive.count_pages(doc, session=Serving({raw: b"<!DOCTYPE html>"})) == 0
    assert "https://a.example/a.pdf" not in doc.archives


def test_a_capture_that_cannot_be_downloaded_is_counted_live_once(no_waiting: None) -> None:
    """A Substack attachment's capture answered `503` after twenty seconds, and
    waiting that out patiently was three minutes a PDF on every build."""
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = CAPTURED
    raw = "https://web.archive.org/web/20240503123456id_/https://a.example/a.pdf"
    session = Serving({"https://a.example/a.pdf": _pdf(4)})
    assert archive.count_pages(doc, session=session) == 1
    assert session.asked == [raw, "https://a.example/a.pdf"]
    assert doc.archives["https://a.example/a.pdf"].snapshot == CAPTURED.snapshot
    assert doc.archives["https://a.example/a.pdf"].pages == 4


def test_a_substack_attachment_is_counted_live_first() -> None:
    """Its URL names one upload for good, and the live copy is the fast one."""
    url = "https://bqrail.substack.com/api/v1/file/e01c0e72-8526-4748-879c-5ac271ca3c06.pdf"
    doc = cites(f"{url}#page=2")
    doc.archives[url] = Archived(
        snapshot=f"https://web.archive.org/web/20261010195152/{url}", timestamp="20261010195152"
    )
    session = Serving({url: _pdf(3)})
    assert archive.count_pages(doc, session=session) == 1
    assert session.asked == [url]
    assert doc.archives[url].pages == 3


def test_only_what_is_named_is_counted() -> None:
    """The count after the archive check is for what it newly archived."""
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = CAPTURED
    session = Serving({})
    assert archive.count_pages(doc, session=session, only=set()) == 0
    assert session.asked == []


def test_a_pdf_whose_capture_failed_is_counted_live() -> None:
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = Archived(timestamp="20240503", error="refused")
    archive.count_pages(doc, session=Serving({"https://a.example/a.pdf": _pdf(4)}))
    assert doc.archives["https://a.example/a.pdf"].pages == 4


def test_a_pdf_whose_newest_capture_is_not_one_is_looked_up_in_the_index(keyed: None) -> None:
    """For a PDF, a `200` that is a bot check is not a capture of it."""
    doc = cites("https://a.example/document/1#page=2")
    session = Replaying([("20260909150154", 200)], rows=[["timestamp"], ["20260905012630"]])
    assert archive.capture(doc, session=session) == (1, 0)
    assert doc.archives["https://a.example/document/1"].timestamp == "20260905012630"
    assert "mimetype:application/pdf" in cast("list[str]", session.index_params["filter"])


def test_a_pdf_capture_the_replay_serves_as_one_is_taken(keyed: None) -> None:
    doc = cites("https://a.example/a.pdf")
    session = Replaying([("20260930025658", 200)])
    session.content_type = "application/pdf"
    assert archive.capture(doc, session=session) == (1, 0)
    assert session.index_asked == 0


class Redirecting(Replaying):
    """A replay whose capture redirects through `hops` before it is served.

    The Substack shape: the cited URL was captured as a `302` to a signed S3
    URL, which was captured too.
    """

    def __init__(self, hops: list[str], content_type: str) -> None:
        super().__init__([("20240921120558", 200)], rows=[["timestamp"], ["20240101000000"]])
        self.hops = hops
        self.content_type = content_type

    @override
    def request(self, method: object, url: object, *args: object, **kwargs: object):
        asked = str(url)
        if asked.startswith(f"{archive.REPLAY}/20240921120558/") and asked != self.hops[-1]:
            response = requests.Response()
            response.url = asked
            response.status_code = 302
            hop = self.hops.index(asked) + 1 if asked in self.hops else 0
            response.headers["location"] = self.hops[hop]
            return response
        return super().request(method, url, *args, **kwargs)


SIGNED = [
    f"{archive.REPLAY}/20240921120558/https://s3.example/a.pdf?signed=1",
    f"{archive.REPLAY}/20240921120558/https://s3.example/a.pdf",
]


def test_a_pdf_capture_that_redirects_to_the_pdf_is_taken(keyed: None) -> None:
    doc = cites("https://a.example/a.pdf")
    session = Redirecting(SIGNED, "application/pdf")
    assert archive.capture(doc, session=session) == (1, 0)
    assert doc.archives["https://a.example/a.pdf"].snapshot == (
        "https://web.archive.org/web/20240921120558/https://a.example/a.pdf"
    )
    assert session.index_asked == 0


def test_a_page_capture_that_redirects_is_not_taken(keyed: None) -> None:
    """A dead page sent to a site's front page also ends in `200`."""
    session = Redirecting(SIGNED, "text/html")
    archive.capture(cites("https://a.example/1"), session=session)
    assert session.index_asked == 1


def test_a_redirect_out_of_the_archive_is_not_followed(keyed: None) -> None:
    session = Redirecting(["https://s3.example/a.pdf"], "application/pdf")
    archive.capture(cites("https://a.example/a.pdf"), session=session)
    assert session.index_asked == 1


def test_what_cannot_be_counted_is_not_recorded() -> None:
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = CAPTURED
    assert archive.count_pages(doc, session=Serving({})) == 0
    assert doc.archives["https://a.example/a.pdf"].pages == 0


def test_a_counted_pdf_is_not_downloaded_again() -> None:
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = replace(CAPTURED, pages=6)
    session = Serving({})
    assert archive.count_pages(doc, session=session) == 0
    assert session.asked == []


def test_the_page_count_survives_the_record(tmp_path: Path) -> None:
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = replace(CAPTURED, pages=6)
    write_archive_index(tmp_path, doc)
    again = cites("https://a.example/a.pdf#page=2")
    read_archive_index(tmp_path, again)
    assert again.archives["https://a.example/a.pdf"].pages == 6


def test_a_capture_the_document_names_keeps_its_recorded_page_count(tmp_path: Path) -> None:
    """The R211 spec is cited as its Wayback URL, which seeds its entry before the record."""
    doc = cites("https://a.example/a.pdf#page=2")
    doc.archives["https://a.example/a.pdf"] = replace(CAPTURED, pages=6)
    write_archive_index(tmp_path, doc)
    again = cites("https://a.example/a.pdf#page=2")
    # What parsing the Wayback URL seeds, which is there before the record is read.
    again.archives["https://a.example/a.pdf"] = CAPTURED
    read_archive_index(tmp_path, again)
    assert again.archives["https://a.example/a.pdf"].pages == 6


# ---- capturing without an account ------------------------------------


class SavingAnonymously(Replaying):
    """No capture anywhere, and anonymous Save Page Now answering `status` and `body`."""

    def __init__(self, status: int, body: str = "", location: str = "") -> None:
        super().__init__([])
        self.status = status
        self.body = body
        self.location = location
        self.saved: list[str] = []

    @override
    def request(self, method: object, url: object, *args: object, **kwargs: object):
        asked = str(url)
        if not asked.startswith(f"{archive.SAVE}/"):
            return super().request(method, url, *args, **kwargs)
        self.saved.append(asked)
        response = requests.Response()
        response.url = asked
        response.status_code = self.status
        response._content = self.body.encode()
        if self.location:
            response.headers["location"] = self.location
        return response


@pytest.fixture
def anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    """No keys, outside CI, and no waiting between captures."""
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)
    monkeypatch.delenv(archive.CI, raising=False)
    monkeypatch.setattr(archive, "ANONYMOUS_EVERY", timedelta())
    monkeypatch.setattr(archive, "PATIENCE", (timedelta(),) * 3)


def test_without_keys_a_source_with_no_capture_is_captured_anonymously(anonymous: None) -> None:
    doc = cites("https://a.example/1")
    session = SavingAnonymously(
        302, location=f"{archive.REPLAY}/20261009154154/https://a.example/1"
    )
    assert archive.capture(doc, session=session) == (0, 1)
    assert session.saved == [f"{archive.SAVE}/https://a.example/1"]
    assert doc.archives["https://a.example/1"] == Archived(
        snapshot="https://web.archive.org/web/20261009154154/https://a.example/1",
        timestamp="20261009154154",
    )


def test_a_page_anonymous_capture_says_failed_is_recorded_with_why(anonymous: None) -> None:
    doc = cites("https://a.example/gone")
    page = (
        "<html><body><h2>Sorry</h2><p>The target server cannot find "
        "https://a.example/gone. (HTTP status=404)</p>"
        "<a>Return to Save Page Now</a></body></html>"
    )
    archive.capture(doc, session=SavingAnonymously(523, page))
    assert doc.archives["https://a.example/gone"].error == (
        "The target server cannot find https://a.example/gone. (HTTP status=404)"
    )


def test_a_failure_status_without_a_reason_is_not_recorded(anonymous: None) -> None:
    """A refusal is recorded for good, so only one the service explained."""
    doc = cites("https://a.example/1")
    archive.capture(doc, session=SavingAnonymously(520, "<html>whatever</html>"))
    assert pending(doc) == {"https://a.example/1": archive.NO_ANSWER}


def test_being_rate_limited_anonymously_is_not_an_answer(anonymous: None) -> None:
    doc = cites("https://a.example/1")
    session = SavingAnonymously(429)
    archive.capture(doc, session=session)
    assert len(session.saved) == 1
    assert pending(doc) == {"https://a.example/1": archive.NO_ANSWER}


def test_in_ci_nothing_is_captured_anonymously(
    anonymous: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(archive.CI, "true")
    session = SavingAnonymously(302)
    assert archive.capture(cites("https://a.example/1"), session=session) == (0, 0)
    assert session.saved == []
