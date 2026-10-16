"""Building more than one report into one site.

The single-document path is covered everywhere else.
What matters here is what only appears with several:
where each report lands,
that one failure does not take the others with it,
and that the index says so.
"""

import json
from pathlib import Path

import pytest
from paths import FIXTURE_DIR
from test_conventions import build, field, image, para
from typer import Exit

from eta_publish import console
from eta_publish.build import (
    IMAGES_JSON,
    BuildOptions,
    has_its_figures,
    read_image_index,
    require_image_index,
    write_image_index,
)
from eta_publish.nodes import Document, Image
from eta_publish.parse import parse
from eta_publish.site import (
    Built,
    Failed,
    Report,
    Site,
    add_report,
    build_site,
    canonical,
    index_page,
    listed_report,
    load_reports,
    report_path,
    reusable,
    saved_responses,
    social_image,
)

FIXTURE = json.loads((FIXTURE_DIR / "doc.json").read_text())


SLUG = "reports/digging-out-deep-hole-sas-west"


def seed_image_index(out: Path) -> None:
    """Give a build that skips the download the record it now requires.

    A real run has one because a real run downloaded once and left it there.
    A test that builds into an empty directory has to say so itself.
    """
    dest = out / SLUG
    dest.mkdir(parents=True, exist_ok=True)
    (dest / IMAGES_JSON).write_text((FIXTURE_DIR / IMAGES_JSON).read_text())


@pytest.fixture
def doc() -> Document:
    return parse(FIXTURE)


def test_a_report_is_published_at_the_path_its_header_names(doc: Document) -> None:
    doc.meta["URL"] = "/reports/digging-out-deep-hole-sas-west"
    assert report_path(doc) == "reports/digging-out-deep-hole-sas-west"


def test_a_report_with_no_url_is_refused(doc: Document) -> None:
    """A slug of the headline is a plausible path and not the published one,
    so guessing one publishes the report at the wrong URL, quietly."""
    doc.meta.pop("URL", None)
    doc.title = "Digging Out of a Very Deep Hole"
    with pytest.raises(ValueError, match="no `URL:` line"):
        report_path(doc)


def test_a_document_with_no_header_is_told_that_and_not_about_its_url(doc: Document) -> None:
    """A `Header` line styled as body text is not a `Header` section,
    so every line under it, the `URL:` one included, is read as prose.
    Reporting the missing URL sends whoever reads it looking for a line
    that is sitting right there in the document."""
    doc.meta.clear()
    doc.has_header = False
    with pytest.raises(ValueError, match="no `Header` section"):
        report_path(doc)


def test_an_absolute_url_cannot_escape_the_site_root(doc: Document) -> None:
    """`/reports/x` is a published path, not a filesystem one;
    joined unstripped it would write to the root of the disk."""
    doc.meta["URL"] = "/reports/x"
    assert not Path(report_path(doc)).is_absolute()


def test_reports_are_read_from_the_list(tmp_path: Path) -> None:
    path = tmp_path / "reports.toml"
    path.write_text(
        '[[report]]\nname = "SAS West"\ntab = "Draft 2"\nurl = "https://example.invalid/a"\n'
        '\n[[report]]\nname = "IBX"\ntab = "Live version"\nurl = "https://example.invalid/b"\n'
    )
    assert load_reports(path) == [
        Report(url="https://example.invalid/a", name="SAS West", tab="Draft 2"),
        Report(url="https://example.invalid/b", name="IBX", tab="Live version"),
    ]


@pytest.mark.parametrize("blank", ["name", "tab"])
def test_an_entry_that_names_nothing_disagrees_like_any_other(tmp_path: Path, blank: str) -> None:
    """A blank field needs no rule of its own: no document is named nothing,
    so the comparison that catches a wrong name catches a missing one."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    fields = {"name": "Digging Out of a Very Deep Hole", "tab": "Draft 2"}
    fields[blank] = ""
    site = build_site(
        [Report(url=str(saved), **fields)],
        tmp_path / "site",
        BuildOptions(images=False, archive=False),
    )
    assert not site.built
    # An empty marked span, which is what a name that is not there looks like.
    assert "``" in site.failed[0].error


def test_one_finds_a_report_by_its_name_in_any_case(tmp_path: Path) -> None:
    path = tmp_path / "reports.toml"
    path.write_text(
        '[[report]]\nname = "IBX Automation"\ntab = "Live"\nurl = "https://example.invalid/b"\n'
    )
    assert listed_report("ibx automation", path) == Report(
        url="https://example.invalid/b", name="IBX Automation", tab="Live"
    )


def test_one_takes_anything_unlisted_as_the_document_itself(tmp_path: Path) -> None:
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "IBX"\ntab = "Live"\nurl = "https://example.invalid/b"\n')
    assert listed_report("https://example.invalid/c", path) == Report(
        url="https://example.invalid/c"
    )
    assert listed_report("x", tmp_path / "missing.toml") == Report(url="x")


def test_one_refuses_a_name_two_entries_share(tmp_path: Path) -> None:
    path = tmp_path / "reports.toml"
    path.write_text(
        '[[report]]\nname = "IBX"\ntab = "A"\nurl = "https://example.invalid/a"\n'
        '\n[[report]]\nname = "IBX"\ntab = "B"\nurl = "https://example.invalid/b"\n'
    )
    with pytest.raises(ValueError, match="more than one"):
        listed_report("IBX", path)


def test_an_entry_without_a_url_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "Nameless"\n')
    with pytest.raises(ValueError, match="no `url`"):
        load_reports(path)


def test_add_names_an_entry_from_the_document(tmp_path: Path) -> None:
    """The whole point of the command: the two names come off the document,
    not off a person reading them out of Drive."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "title": "IBX Automation", "tabTitle": "Live version"}))
    path = tmp_path / "reports.toml"
    path.write_text('# a comment worth keeping\n\n[[report]]\nname = "A"\ntab = "B"\nurl = "u"\n')

    added = add_report(str(saved), path)
    assert added == Report(url=str(saved), name="IBX Automation", tab="Live version")
    assert "# a comment worth keeping" in path.read_text()
    assert load_reports(path)[-1] == added


def test_add_refuses_a_document_already_listed(tmp_path: Path) -> None:
    """Two entries for one document publish it twice to one path,
    and the second build overwrites the first."""
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "A"\ntab = "B"\nurl = "u"\n')
    with pytest.raises(ValueError, match="already lists"):
        add_report("u", path)


def test_add_refuses_a_document_that_names_no_tab(tmp_path: Path) -> None:
    """It cannot write down an answer the document does not give,
    and writing an empty one down is what `load_reports` refuses."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "title": "Titled", "tabTitle": ""}))
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "A"\ntab = "B"\nurl = "u"\n')
    with pytest.raises(ValueError, match="no `tab`"):
        add_report(str(saved), path)
    assert len(load_reports(path)) == 1


def test_add_says_which_tabs_there_are_when_the_url_names_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URL pasted without its `?tab=` id is the mistake this command exists
    to survive, and the answer is the list of tabs `TabNotFound` carries,
    not the traceback it used to be printed as."""
    from typer.testing import CliRunner

    from eta_publish import build
    from eta_publish.__main__ import app
    from eta_publish.fetch import TabNotFound

    def no_tab(ref: str, suggestions: str = "rejected") -> object:
        raise TabNotFound("this document has 2 tabs; pass the URL including\n  t.a  Live version")

    monkeypatch.setattr(build, "load", no_tab)
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "A"\ntab = "B"\nurl = "u"\n')

    result = CliRunner().invoke(app, ["add", "https://example.invalid/d/x", "-r", str(path)])
    assert result.exit_code != 0
    assert "t.a  Live version" in result.output
    assert len(load_reports(path)) == 1


def test_a_title_with_a_quotation_mark_stays_one_string(tmp_path: Path) -> None:
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "title": 'The "Deep Hole" Report', "tabTitle": "D2"}))
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "A"\ntab = "B"\nurl = "u"\n')
    add_report(str(saved), path)
    assert load_reports(path)[-1].name == 'The "Deep Hole" Report'


def test_the_project_list_parses() -> None:
    """The committed one, so a typo in it fails here rather than in CI."""
    reports = load_reports()
    assert reports
    assert all(
        "?tab=" in r.url or "&tab=" in r.url or not r.url.startswith("http") for r in reports
    )


def test_one_failure_does_not_stop_the_others(tmp_path: Path) -> None:
    # Named as the entry below names it, and with a tab title to confirm:
    # this test is about a fetch failure, not about a wrong entry.
    good = tmp_path / "good.json"
    good.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    # Unreadable rather than absent:
    # a path that does not exist is taken for a document reference
    # and would reach for the network, and the test suite never does that.
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    reports = [
        Report(url=str(broken), name="gone", tab="Draft 2"),
        Report(url=str(good), name="Digging Out of a Very Deep Hole", tab="Draft 2"),
    ]
    seed_image_index(tmp_path / "site")
    site = build_site(reports, tmp_path / "site", BuildOptions(images=False, archive=False))
    assert [f.report.name for f in site.failed] == ["gone"]
    assert [b.report.name for b in site.built] == ["Digging Out of a Very Deep Hole"]
    assert (tmp_path / "site" / site.built[0].path / "index.html").exists()


def test_a_whole_site_replaces_the_site_but_keeps_a_report_that_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What no report wrote this time is gone, unless its report could not be built.

    A site missing a report beats no site, and the last copy of it beats a missing one.
    """
    import eta_publish.fetch as fetch
    from eta_publish.__main__ import Suggestions, publish

    def unreachable(*args: object, **kwargs: object) -> object:
        raise RuntimeError("Google is not answering")

    monkeypatch.setattr(fetch, "fetch", unreachable)
    out = tmp_path / "site"
    seed_image_index(out)
    kept = out / "reports" / "kept"
    kept.mkdir(parents=True)
    (kept / "doc.json").write_text(json.dumps({"documentId": "abc", "tabId": "t.1"}))
    (kept / "report.html").write_text("the last build of a report that failed")
    (out / "reports" / "dropped").mkdir()
    (out / "reports" / "dropped" / "report.html").write_text("no report writes this any more")
    good = tmp_path / "good.json"
    good.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    reports = [
        Report(url="https://docs.google.com/document/d/abc/edit?tab=t.1"),
        Report(url=str(good), name="Digging Out of a Very Deep Hole", tab="Draft 2"),
    ]

    with pytest.raises(Exit):
        publish(reports, out, Suggestions.REJECTED, False, False, False, archive=False, whole=True)

    assert (kept / "report.html").read_text() == "the last build of a report that failed"
    assert not (out / "reports" / "dropped").exists()
    assert (out / SLUG / "report.html").is_file()
    assert [p.name for p in tmp_path.iterdir() if "building" in p.name] == []


def test_one_report_replaces_only_its_own_directory(tmp_path: Path) -> None:
    from eta_publish.__main__ import Suggestions, publish

    out = tmp_path / "site"
    seed_image_index(out)
    (out / SLUG / "stale.html").write_text("written by an older build of this report")
    (out / "reports" / "other").mkdir()
    (out / "reports" / "other" / "report.html").write_text("another report's")
    good = tmp_path / "good.json"
    good.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))

    publish([Report(url=str(good))], out, Suggestions.REJECTED, False, False, False, archive=False)

    assert not (out / SLUG / "stale.html").exists()
    assert (out / SLUG / "report.html").is_file()
    assert (out / "reports" / "other" / "report.html").read_text() == "another report's"


@pytest.mark.parametrize(
    ("hosted", "src"),
    [
        (
            True,
            'src="https://kkysen.github.io/eta-publish/reports/digging-out-deep-hole-sas-west/images/',
        ),
        (False, 'src="images/'),
    ],
)
def test_the_fragment_links_its_images_where_the_site_serves_them(
    tmp_path: Path, hosted: bool, src: str
) -> None:
    """Squarespace names every upload by a hash, so the fragment links the site's copies."""
    out = tmp_path / "site"
    seed_image_index(out)
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE))
    options = BuildOptions(images=False, archive=False, hosted_media=hosted)
    site = build_site([Report(url=str(saved))], out, options)
    fragment = (out / site.built[0].path / "report.html").read_text()
    assert src in fragment
    # The page is served beside its images either way.
    assert 'src="images/' in (out / site.built[0].path / "index.html").read_text()


def test_a_wrong_entry_leaves_no_files_behind(tmp_path: Path) -> None:
    """A report that failed its own check must not leave a published directory:
    the next run compares against it and finds nothing wrong."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    out = tmp_path / "site"
    site = build_site(
        [Report(url=str(saved), name="Some Other Document", tab="Draft 2")],
        out,
        BuildOptions(images=False, archive=False),
    )
    assert not site.built
    assert "the document is named" in site.failed[0].error
    assert not list(out.rglob("report.html"))


def test_a_saved_response_is_found_by_the_document_it_came_from(tmp_path: Path) -> None:
    """A report's directory is named after its `URL:` line, which is a path and
    not an id, so the response's own `documentId` is what joins it to an entry."""
    written = tmp_path / "reports" / "a-report"
    written.mkdir(parents=True)
    (written / "doc.json").write_text(json.dumps({**FIXTURE, "documentId": "abc", "tabId": "t.1"}))
    assert saved_responses(tmp_path) == {("abc", "t.1"): written}


def test_a_directory_that_is_not_a_saved_response_is_passed_over(tmp_path: Path) -> None:
    """Unreadable, or readable and saying nothing about which document it is."""
    for name, text in (("broken", "{not json"), ("anonymous", "{}")):
        d = tmp_path / "reports" / name
        d.mkdir(parents=True)
        (d / "doc.json").write_text(text)
    assert saved_responses(tmp_path) == {}


def test_offline_builds_from_the_saved_response(tmp_path: Path) -> None:
    """The same bytes as the build that fetched it, without fetching anything:
    a `fetch` reached for here would be a network call in a run asked for none."""
    import eta_publish.build as build_module

    out = tmp_path / "site"
    written = out / "reports" / "digging-out-deep-hole-sas-west"
    written.mkdir(parents=True)
    (written / "doc.json").write_text(
        json.dumps(
            {
                **FIXTURE,
                "documentId": "abc",
                "tabId": "t.1",
                "tabTitle": "Draft 2",
                "suggestions": "rejected",
            }
        )
    )
    report = Report(
        url="https://docs.google.com/document/d/abc/edit?tab=t.1",
        name="Digging Out of a Very Deep Hole",
        tab="Draft 2",
    )

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline reached for the network")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(build_module, "fetch", boom, raising=False)
    seed_image_index(out)
    site = build_site(
        [report], out, BuildOptions(images=False, offline=True, comments=False, archive=False)
    )
    monkeypatch.undo()
    assert [b.path for b in site.built] == ["reports/digging-out-deep-hole-sas-west"]


def test_offline_refuses_a_response_read_the_other_way(tmp_path: Path) -> None:
    """A fetch would go and get the other one. Offline cannot, so it says so
    rather than publishing the document the last build happened to read."""
    out = tmp_path / "site"
    written = out / "reports" / "digging-out-deep-hole-sas-west"
    written.mkdir(parents=True)
    (written / "doc.json").write_text(
        json.dumps({**FIXTURE, "documentId": "abc", "tabId": "t.1", "suggestions": "rejected"})
    )
    site = build_site(
        [Report(url="https://docs.google.com/document/d/abc/edit?tab=t.1", name="A", tab="B")],
        out,
        BuildOptions(offline=True, suggestions="accepted", archive=False),
    )
    assert not site.built
    assert "needs a fetch" in site.failed[0].error


def test_offline_says_which_report_it_has_nothing_saved_for(tmp_path: Path) -> None:
    """Fetching one document in a run asked to fetch nothing is worse than saying so."""
    site = build_site(
        [Report(url="https://docs.google.com/document/d/abc/edit?tab=t.1", name="A", tab="B")],
        tmp_path / "site",
        BuildOptions(offline=True, archive=False),
    )
    assert not site.built
    assert "nothing saved" in site.failed[0].error


def test_reports_are_built_at_once_and_reported_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, doc: Document
) -> None:
    """A list of reports reads as the list it is, whatever order Google answers in,
    and the whole point is that one report's wait is not another's."""
    import time

    import eta_publish.site as site_module

    SLOW = 0.3
    order = ["slow", "quick"]

    def build(ref: str, *args: object, **kwargs: object) -> tuple[Document, str]:
        if ref.endswith("slow"):
            time.sleep(SLOW)
        return doc, f"reports/{ref.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(site_module, "build_one", build)
    reports = [Report(url=f"https://example.invalid/{name}") for name in order]

    started = time.perf_counter()
    site = build_site(reports, tmp_path / "site")
    elapsed = time.perf_counter() - started

    assert [b.path for b in site.built] == ["reports/slow", "reports/quick"]
    # The quick one did not wait its turn behind the slow one.
    # Two sleeps is what sequential costs, one is the floor, and the bound is
    # nearer the floor than the ceiling without being a stopwatch:
    # a loaded runner may be slow, but it cannot make two waits into one.
    assert elapsed < 2 * SLOW


def test_a_note_says_which_report_it_is_about(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    doc: Document,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Several reports are built at once and each writes as it goes,
    so a note about one of them that does not name it names none of them."""
    import eta_publish.site as site_module

    def build(ref: str, *args: object, **kwargs: object) -> tuple[Document, str]:
        name = ref.rsplit("/", 1)[-1]
        console.write(console.note(f"looked up {name}"))
        return doc, f"reports/{name}"

    monkeypatch.setattr(site_module, "build_one", build)
    reports = [
        Report(url=f"https://example.invalid/{name}", name=name.title()) for name in ("one", "two")
    ]

    build_site(reports, tmp_path / "site")

    written = capsys.readouterr().err
    assert "`One`: looked up one" in written
    assert "`Two`: looked up two" in written


def test_the_index_lists_what_built_and_what_did_not(doc: Document) -> None:
    site = Site(
        built=[Built(report=Report(url="u", name="SAS West"), doc=doc, path="reports/sas-west")],
        failed=[Failed(report=Report(url="u2", name="Next"), error="not found")],
    )
    page = index_page(site)
    assert 'href="reports/sas-west/"' in page
    assert doc.title in page
    assert "Next: not found" in page


def test_a_card_summarizes_the_report_by_its_short(doc: Document) -> None:
    """What a blog post's excerpt or `What's New` says, not the search result's preview."""
    doc.meta["Short"] = "The short."
    doc.meta["SEO Description"] = "The SEO description."
    site = Site(built=[Built(report=Report(url="u", name="SAS West"), doc=doc, path="r/s")])
    page = index_page(site)
    assert "The short." in page
    assert "The SEO description." not in page


def test_only_one_document_or_list_at_a_time() -> None:
    """Building several at once is what a list is for,
    and a list is a file that can be reviewed
    rather than a shell line that is right once."""
    from typer.testing import CliRunner

    from eta_publish.__main__ import app

    assert CliRunner().invoke(app, ["all", "one.toml", "two.toml"]).exit_code != 0
    assert CliRunner().invoke(app, ["one", "a.json", "b.json"]).exit_code != 0


def test_one_needs_a_document_to_build() -> None:
    """`all` has a list to fall back on and `one` has nothing:
    a document is the whole of what it was asked."""
    from typer.testing import CliRunner

    from eta_publish.__main__ import app

    assert CliRunner().invoke(app, ["one"]).exit_code != 0


def test_a_missing_list_is_reported_as_a_bad_argument(tmp_path: Path) -> None:
    """Not a traceback:
    naming a file that is not there is a typo, and the message should read like one."""
    from typer.testing import CliRunner

    from eta_publish.__main__ import app

    absent = tmp_path / "absent.toml"
    result = CliRunner().invoke(app, ["all", str(absent)])
    assert result.exit_code != 0
    assert str(absent) in result.output


def test_a_report_directory_is_a_document(tmp_path: Path) -> None:
    """A build writes `doc.json` beside its outputs,
    so what one run wrote is what the next can be handed,
    with no network and no knowing the filename inside it."""
    from typer.testing import CliRunner

    from eta_publish.__main__ import app

    seed_image_index(tmp_path / "site")
    result = CliRunner().invoke(
        app,
        # `--no-archive`, because the docstring's "no network" is the point of
        # the test and looking a source up is a request like any other.
        ["one", str(FIXTURE_DIR), "-o", str(tmp_path / "site"), "--no-images", "--no-archive"],
    )
    assert result.exit_code == 0, result.output
    built = tmp_path / "site" / "reports" / "digging-out-deep-hole-sas-west"
    assert (built / "report.md").is_file()
    assert (built / "doc.json").is_file()


def test_a_build_elsewhere_carries_over_only_what_the_report_still_uses(tmp_path: Path) -> None:
    """What the last build recorded comes along, and a picture nothing names any more does not.

    The point of building into a directory of its own is that a file the build
    no longer writes is not left behind to be published with the rest.
    """
    from eta_publish.build import carry_over

    last = tmp_path / "last"
    (last / "images").mkdir(parents=True)
    (last / IMAGES_JSON).write_text((FIXTURE_DIR / IMAGES_JSON).read_text())
    (last / "doc.json").write_text(json.dumps(FIXTURE))
    (last / "images" / "sas-west-036.png").write_bytes(b"named")
    (last / "images" / "img-0fb4cdcf.jpg").write_bytes(b"named once, not now")
    (last / "report.html").write_text("written by every build")

    carry_over(last, tmp_path / "next", parse(FIXTURE))

    carried = {p.relative_to(tmp_path / "next").as_posix() for p in (tmp_path / "next").rglob("*")}
    assert carried == {"doc.json", IMAGES_JSON, "images", "images/sas-west-036.png"}


def test_a_carried_over_image_is_linked_and_replacing_it_leaves_the_last_build_alone(
    tmp_path: Path,
) -> None:
    """Linked, so a build does not copy 50 MB it changes none of; replaced, never rewritten."""
    from eta_publish.build import carry_over
    from eta_publish.naming import replace_bytes

    last = tmp_path / "last"
    (last / "images").mkdir(parents=True)
    (last / IMAGES_JSON).write_text((FIXTURE_DIR / IMAGES_JSON).read_text())
    (last / "images" / "sas-west-036.png").write_bytes(b"the last build's")

    carry_over(last, tmp_path / "next", parse(FIXTURE))
    carried = tmp_path / "next" / "images" / "sas-west-036.png"
    assert carried.stat().st_ino == (last / "images" / "sas-west-036.png").stat().st_ino

    replace_bytes(carried, b"this build's")
    assert carried.read_bytes() == b"this build's"
    assert (last / "images" / "sas-west-036.png").read_bytes() == b"the last build's"


def test_a_directory_without_a_saved_response_says_so(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from eta_publish.__main__ import app

    (tmp_path / "empty").mkdir()
    result = CliRunner().invoke(app, ["one", str(tmp_path / "empty"), "-o", str(tmp_path / "site")])
    assert result.exit_code != 0
    assert "doc.json" in result.output


def test_a_name_that_is_not_the_documents_is_warned_about(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`reports.toml` names each report, and only the fetch knows if it is right."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE))
    build_site(
        [Report(url=str(saved), name="SAS West")],
        tmp_path / "site",
        BuildOptions(images=False, archive=False),
    )
    warning = capsys.readouterr().err
    assert "reports.toml calls this `SAS West`" in warning
    assert f"`{FIXTURE['title']}`" in warning


def test_the_documents_own_name_is_not_warned_about(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE))
    build_site(
        [Report(url=str(saved), name=str(FIXTURE["title"]))],
        tmp_path / "site",
        BuildOptions(images=False, archive=False),
    )
    assert "reports.toml calls this" not in capsys.readouterr().err


def test_a_tab_that_is_not_the_documents_is_warned_about(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `?tab=` id says nothing a reader can check, so the title is what is checked."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE | {"tabTitle": "Draft 2"}))
    build_site(
        [Report(url=str(saved), tab="Draft 1")],
        tmp_path / "site",
        BuildOptions(images=False, archive=False),
    )
    warning = capsys.readouterr().err
    assert "reports.toml expects the tab `Draft 1`" in warning
    assert "`Draft 2`" in warning


def test_a_response_that_names_no_tab_cannot_confirm_one(tmp_path: Path) -> None:
    """A `?tab=` id names a draft and says nothing about which,
    so a response with no `tabTitle` leaves the entry's one question unanswered,
    and an unanswered question is not a passed check."""
    saved = tmp_path / "doc.json"
    assert "tabTitle" not in FIXTURE
    saved.write_text(json.dumps(FIXTURE))
    site = build_site(
        [Report(url=str(saved), name="Digging Out of a Very Deep Hole", tab="Draft 1")],
        tmp_path / "site",
        BuildOptions(images=False, archive=False),
    )
    assert not site.built
    assert "the tab is named ``" in site.failed[0].error


def test_an_entry_that_names_neither_is_not_warned_about(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both fields are optional: an entry says as much as whoever wrote it wanted."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE))
    build_site(
        [Report(url=str(saved))], tmp_path / "site", BuildOptions(images=False, archive=False)
    )
    assert "reports.toml" not in capsys.readouterr().err


def test_a_url_that_climbs_out_of_the_site_is_refused(doc: Document) -> None:
    """The build writes wherever this says, and the committed-site check
    only ever looks inside `site/`, so a climb would leave no trace there."""
    doc.title = "Digging Out of a Very Deep Hole"
    doc.meta["URL"] = "/../../../../tmp/pwned"
    with pytest.raises(ValueError, match="climbs out of the site"):
        report_path(doc)


def _report_dir(tmp_path: Path, recorded: dict[str, dict[str, str]]) -> Path:
    previous = tmp_path / "reports" / "x"
    (previous / "images").mkdir(parents=True)
    (previous / IMAGES_JSON).write_text(json.dumps(recorded))
    return previous


def test_a_response_whose_images_are_gone_is_not_reused(tmp_path: Path) -> None:
    """The response is committed and the images are not,
    so a fresh checkout has one describing pictures that are not beside it.
    Reused there, the build downloads nothing and publishes a page with no images."""
    previous = _report_dir(tmp_path, {"kix.1": {"file": "img-a.jpg"}})
    assert reusable(previous, BuildOptions(archive=False)) is None


def test_a_response_whose_images_are_there_is_reused(tmp_path: Path) -> None:
    previous = _report_dir(tmp_path, {"kix.1": {"file": "img-a.jpg"}})
    (previous / "images" / "img-a.jpg").write_bytes(b"")
    assert reusable(previous, BuildOptions(archive=False)) == previous / "doc.json"


def test_an_image_the_code_now_names_differently_is_not_on_disk(tmp_path: Path) -> None:
    """The old file still passes `has_its_images`, so the saved response is reused,
    and it has no `contentUri` to download the new name from."""
    doc = build([para("Headline", "TITLE"), field("Source: W125irtjeh.JPG"), image()])
    images = tmp_path / "images"
    images.mkdir()
    (images / "img-a.jpg").write_bytes(b"")
    assert not has_its_figures(tmp_path, doc)
    (images / "W125irtjeh.jpg").write_bytes(b"")
    assert has_its_figures(tmp_path, doc)


def test_a_build_that_wants_no_images_does_not_ask_where_they_are(tmp_path: Path) -> None:
    """It is not going to download them either way,
    so the pictures on disk are not what it is asking about."""
    previous = _report_dir(tmp_path, {"kix.1": {"file": "img-a.jpg"}})
    assert reusable(previous, BuildOptions(images=False, archive=False)) == previous / "doc.json"


def test_a_download_that_turned_up_nothing_does_not_erase_the_index(tmp_path: Path) -> None:
    """`images.json` is the one file that says which pictures a complete build wrote,
    and a build that fetched none of them knows less than it did, not more."""
    recorded = {"kix.1": {"file": "img-a.jpg", "sha256": "abc"}}
    previous = _report_dir(tmp_path, recorded)
    write_image_index(previous, {})
    assert json.loads((previous / IMAGES_JSON).read_text()) == recorded


def test_a_picture_nothing_wrote_has_no_name_to_emit(doc: Document) -> None:
    """The stem is not an answer: an extension is learned by fetching,
    so `images/img-d4734d4b` is a path no browser serves as an image,
    and a page that links one has a hole in it that nothing reports as this."""
    with pytest.raises(ValueError, match="was never written"):
        doc.image_href(doc.images[0])


def test_a_named_picture_is_not_asked_to_be_on_disk(doc: Document) -> None:
    """The file being there is a different question:
    a build that wants no images has no `images` directory,
    and the paths it writes are the right paths to files it did not fetch."""
    doc.image_files = {image.object_id: f"{image.filename}.jpg" for image in doc.images}
    assert doc.image_href(doc.images[0]).endswith(".jpg")


def test_a_build_that_downloaded_nothing_reads_both_back(tmp_path: Path) -> None:
    """Neither the filename nor the shape can be derived, and the files are not
    committed, so `images.json` is the record of both and the only thing such a
    build has to go on."""
    (tmp_path / IMAGES_JSON).write_text(
        json.dumps({"kix.1": {"file": "img-a.jpg", "width": 10, "height": 5}})
    )
    doc = Document()
    read_image_index(tmp_path, doc)
    assert doc.image_files == {"kix.1": "img-a.jpg"}
    assert doc.image_shapes == {"kix.1": (10, 5)}


def test_what_this_build_downloaded_beats_what_the_last_one_recorded(tmp_path: Path) -> None:
    """They differ where a content type or a vector fallback changed,
    and there the file on disk is the one being published."""
    (tmp_path / IMAGES_JSON).write_text(json.dumps({"kix.1": {"file": "img-a.jpg"}}))
    doc = Document(image_files={"kix.1": "img-a.svg"})
    read_image_index(tmp_path, doc)
    assert doc.image_files == {"kix.1": "img-a.svg"}


def test_skipping_the_download_needs_the_record_of_one(tmp_path: Path, doc: Document) -> None:
    """Skipping is for not fetching 18 MB again, not for building in the dark:
    whatever is fetched stays on disk, so that cost is paid once and never again."""
    with pytest.raises(ValueError, match="build it once with the download"):
        require_image_index(tmp_path, doc)


def test_what_the_commands_say_is_not_on_stdout(tmp_path: Path) -> None:
    """A build's product is the files under `site/` and `add`'s is the line it
    wrote into `reports.toml`, so what either says about doing it is commentary,
    the way `cargo build` narrates on stderr and leaves stdout clear.
    Only `--help` answers a question that was asked, and only it uses stdout."""
    from typer.testing import CliRunner

    from eta_publish.__main__ import app

    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "title": "IBX Automation", "tabTitle": "Live version"}))
    path = tmp_path / "reports.toml"
    path.write_text('[[report]]\nname = "A"\ntab = "B"\nurl = "u"\n')

    result = CliRunner().invoke(app, ["add", str(saved), "-r", str(path)])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "added `IBX Automation`, tab `Live version`" in result.stderr

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "eta-publish" in result.stdout


def test_reports_are_separated_from_each_other(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report is a heading and everything under it,
    and two of them run together are one list of warnings rather than two.
    Nothing above the first, which would be a blank line opening the build."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE))
    build_site(
        [Report(url=str(saved)), Report(url=str(saved))],
        tmp_path / "site",
        BuildOptions(images=False, archive=False),
    )
    lines = capsys.readouterr().err.splitlines()
    headings = [i for i, line in enumerate(lines) if line.startswith(("✓", "✗"))]
    assert len(headings) == 2
    assert headings[0] == 0
    assert lines[headings[1] - 1] == ""


def test_a_url_is_listed_without_what_the_browser_added() -> None:
    """`?pli=1` says the reader is signed into more than one account and
    `#heading=` is where their cursor was, and neither names the document."""
    copied = (
        "https://docs.google.com/document/d/1GB5qDuIjDB/edit?pli=1&tab=t.0#heading=h.mkzkbxod1acf"
    )
    assert canonical(copied) == "https://docs.google.com/document/d/1GB5qDuIjDB/edit?tab=t.0"


def test_a_document_named_without_a_tab_keeps_its_url_whole() -> None:
    assert canonical("https://docs.google.com/document/d/1GB5qDuIjDB/edit?pli=1") == (
        "https://docs.google.com/document/d/1GB5qDuIjDB/edit"
    )


def test_what_is_not_a_docs_url_is_left_alone() -> None:
    """A bare document id and a path to a saved response
    are both things `one` accepts, and neither has parts to drop."""
    assert canonical("1GB5qDuIjDB") == "1GB5qDuIjDB"
    assert canonical("site/reports/ibx-automation") == "site/reports/ibx-automation"


def test_the_same_document_copied_twice_is_recognized_as_listed(tmp_path: Path) -> None:
    """The second copy carries a different `?pli=` and a different heading,
    and it is the same document, which is what the refusal is about."""
    path = tmp_path / "reports.toml"
    listed = "https://docs.google.com/document/d/1GB5qDuIjDB/edit?tab=t.0"
    path.write_text(f'[[report]]\nname = "A"\ntab = "B"\nurl = "{listed}"\n')
    with pytest.raises(ValueError, match="already lists"):
        add_report(f"{listed}&pli=1#heading=h.mkzkbxod1acf", path)


def test_a_build_the_archive_did_not_answer_in_full_is_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sixteen sources that all had to get through one build together never did,
    and a capture can still be running a day later."""

    from eta_publish import archive
    from eta_publish.nodes import Archived

    answered: list[str] = []

    def capture(doc: Document, **_: object) -> tuple[int, int]:
        url = archive.missing(doc)[0]
        answered.append(url)
        doc.archives[url] = Archived(
            snapshot=f"https://web.archive.org/web/20261009000000/{url}",
            timestamp="20261009000000",
        )
        for other in archive.missing(doc)[1:]:
            doc.archives[other] = Archived(
                timestamp="20261009", error=archive.STILL_RUNNING, pending=True
            )
        return 1, 0

    monkeypatch.setattr(archive, "capture", capture)

    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps(FIXTURE))
    out = tmp_path / "site"
    seed_image_index(out)
    site = build_site([Report(url=str(saved))], out, BuildOptions(images=False))
    assert site.built
    assert not site.failed
    record = json.loads((out / SLUG / "archives.json").read_text())
    assert record[answered[0]]["timestamp"] == "20261009000000"
    assert not site.failed, site.failed


def test_capturing_without_keys_is_said_once_and_again_after_the_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Said among a document's warnings, it scrolled away under the next report."""
    from eta_publish import __main__, archive, build

    def capture(doc: Document, **_: object) -> tuple[int, int]:
        return 0, 0

    monkeypatch.setattr(archive, "capture", capture)
    monkeypatch.delenv(archive.ACCESS_KEY, raising=False)
    monkeypatch.delenv(archive.SECRET_KEY, raising=False)
    monkeypatch.delenv(archive.CI, raising=False)
    monkeypatch.setattr(build, "ANONYMOUS_WARNED", build.ANONYMOUS_WARNED.__class__())
    monkeypatch.setattr(__main__, "ANONYMOUS_WARNED", build.ANONYMOUS_WARNED)
    doc = parse(FIXTURE)
    doc.archives.clear()
    build.archive_sources(doc)
    build.archive_sources(doc)
    assert capsys.readouterr().err.count("WITHOUT archive.org keys") == 1
    __main__.report_outcome(Site(built=[], failed=[]))
    assert "WITHOUT archive.org keys" in capsys.readouterr().err


def test_one_ctrl_c_stops_a_build_without_waiting_for_its_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Ctrl+C` reaches only the main thread, and the reports are on others.

    Waiting for them to finish is what made the first `Ctrl+C` look like
    nothing and the second a traceback through the thread pool's join.
    """
    import os
    import signal
    import threading
    import time

    import eta_publish.site as site_module
    from eta_publish.archive import Stopped

    released = threading.Event()

    def stuck(*args: object, **kwargs: object) -> object:
        with console.watching() as rows:
            rows.show("https://slow.example/a.pdf", "capture pending")
            released.wait(10)
        raise RuntimeError("released")

    monkeypatch.setattr(site_module, "build_one", stuck)
    # A real `SIGINT`, as `Ctrl+C` sends: one only flagged for the main thread
    # does not wake it from waiting on a report, and so tests nothing here.
    threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGINT)).start()
    started = time.monotonic()
    try:
        with pytest.raises(Stopped) as stopped:
            build_site([Report(url=str(tmp_path / "doc.json"), name="Slow")], tmp_path / "site")
    finally:
        released.set()
    assert time.monotonic() - started < 2
    assert "stopped while building Slow" in str(stopped.value)
    assert "https://slow.example/a.pdf (capture pending, 0s)" in str(stopped.value)


def test_a_stopped_builds_leftovers_are_removed_and_a_running_ones_are_not(tmp_path: Path) -> None:
    """A build stopped partway can leave its directory behind; the next build takes it away."""
    import os
    import subprocess

    from eta_publish.__main__ import abandoned

    gone = subprocess.Popen(["true"])
    gone.wait()
    (tmp_path / f".site-building-{gone.pid}-abc").mkdir()
    (tmp_path / f".site-building-{os.getpid()}-def").mkdir()
    (tmp_path / "site").mkdir()

    abandoned(tmp_path, ".site-building-")

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        f".site-building-{os.getpid()}-def",
        "site",
    ]


def test_the_social_image_is_the_sites_copy_of_the_card(doc: Document) -> None:
    """What to upload as Squarespace's social image, and nothing without a card."""
    doc.card = Image(object_id="io.card", filename="card")
    doc.image_files["io.card"] = "card.jpg"
    assert social_image(doc, "reports/r") == (
        "https://kkysen.github.io/eta-publish/reports/r/images/card.jpg"
    )
    doc.card = None
    assert social_image(doc, "reports/r") == ""


def test_a_card_shows_the_reports_share_card_where_it_has_one(doc: Document) -> None:
    doc.card = Image(object_id="io.card", filename="card")
    doc.image_files["io.card"] = "card.jpg"
    site = Site(built=[Built(report=Report(url="u", name="SAS West"), doc=doc, path="r/s")])
    assert 'src="r/s/images/card.jpg"' in index_page(site)
    doc.card = None
    assert 'class="card"' not in index_page(site)
