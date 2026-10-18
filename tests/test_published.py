"""`site/published/`: what an `automated` report's live page links, and nothing else."""

from pathlib import Path

import pytest

from eta_publish.naming import PUBLISHED_DIR, SITE, UNPUBLISHED_DIR
from eta_publish.published import referenced, write_published
from eta_publish.site import Published, Report

PATH = "reports/r"


def test_what_the_fragment_links_at_the_site_is_what_it_needs() -> None:
    html = (
        f'<link rel="stylesheet" href="{SITE}/assets/report.css">'
        f'<script src="{SITE}/assets/report.js"></script>'
        f'<a href="{SITE}/{PATH}/images/a.jpg"><img src="{SITE}/{PATH}/images/web/a-800w.webp"'
        f' srcset="{SITE}/{PATH}/images/web/a-800w.avif 800w,'
        f' {SITE}/{PATH}/images/web/a-1600w.avif 1600w"></a>'
        f'<video src="{SITE}/{PATH}/videos/v.mp4" poster="{SITE}/{PATH}/images/p.jpg"></video>'
    )
    assert referenced(html, PATH) == {
        "assets/report.css",
        "assets/report.js",
        f"{PATH}/images/a.jpg",
        f"{PATH}/images/web/a-800w.webp",
        f"{PATH}/images/web/a-800w.avif",
        f"{PATH}/images/web/a-1600w.avif",
        f"{PATH}/videos/v.mp4",
        f"{PATH}/images/p.jpg",
    }


def test_a_link_anywhere_else_is_not_ours_to_host() -> None:
    """A link to a passage is commas all the way through, and is still one link."""
    html = (
        '<a href="https://example.com/a#:~:text=160,000,-per%20day">x</a>'
        '<a href="#fn1">1</a><a href="mailto:a@example.com">a</a>'
        '<a href="https://example.com/?a=1&amp;b=2">b</a>'
    )
    assert referenced(html, PATH) == set()


def test_a_relative_link_is_relative_to_the_report() -> None:
    """What a `--no-hosted-media` fragment links: its pictures beside itself."""
    html = '<img src="images/a.jpg"><link href="../../assets/report.css">'
    assert referenced(html, PATH) == {f"{PATH}/images/a.jpg", "assets/report.css"}


def test_a_link_names_the_file_percent_encoded() -> None:
    html = f'<img src="{SITE}/{PATH}/images/Platform%20(east).jpg">'
    assert referenced(html, PATH) == {f"{PATH}/images/Platform (east).jpg"}


def test_a_link_out_of_the_site_is_refused() -> None:
    with pytest.raises(ValueError, match="outside the site"):
        referenced('<img src="../../../etc/passwd">', PATH)


def built(root: Path, path: str, doc_id: str, html: str) -> None:
    """A report directory as a build leaves it, with a response saying which document it is."""
    directory = root / UNPUBLISHED_DIR / path
    directory.mkdir(parents=True)
    (directory / "doc.json").write_text(f'{{"documentId": "{doc_id}", "tabId": "t"}}')
    (directory / "report.html").write_text(html)
    (directory / "report.md").write_text("# r\n")
    (directory / "index.html").write_text("the preview")


def entry(doc_id: str, published: Published) -> Report:
    return Report(
        url=f"https://docs.google.com/document/d/{doc_id}/edit?tab=t",
        name=doc_id,
        tab="t",
        published=published,
    )


def files(root: Path) -> set[str]:
    out = root / PUBLISHED_DIR
    return {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


def test_only_an_automated_report_is_hosted_and_only_what_it_links(tmp_path: Path) -> None:
    html = f'<img src="{SITE}/reports/a/images/a.jpg">'
    built(tmp_path, "reports/a", "a", html)
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images").mkdir()
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images/a.jpg").write_bytes(b"a")
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images/unused.jpg").write_bytes(b"u")
    built(tmp_path, "reports/m", "m", html)
    built(tmp_path, "reports/d", "d", html)
    reports = [
        entry("a", Published.AUTOMATED),
        entry("m", Published.MANUAL),
        entry("d", Published.DRAFT),
    ]

    assert write_published(tmp_path, reports, complete=True) == []
    assert files(tmp_path) == {
        "reports/a/report.html",
        "reports/a/report.md",
        "reports/a/images/a.jpg",
    }


def test_a_live_page_linking_a_missing_file_is_a_problem(tmp_path: Path) -> None:
    built(tmp_path, "reports/a", "a", f'<img src="{SITE}/reports/a/images/a.jpg">')
    report = entry("a", Published.AUTOMATED)
    [(which, problem)] = write_published(tmp_path, [report], complete=True)
    assert which == report
    assert "`reports/a/images/a.jpg`" in problem
    # Without the pictures there is nothing to copy, which is not a problem.
    assert write_published(tmp_path, [report], complete=False) == []


def test_a_report_no_longer_automated_is_no_longer_hosted(tmp_path: Path) -> None:
    built(tmp_path, "reports/a", "a", "")
    write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True)
    assert files(tmp_path)
    write_published(tmp_path, [entry("a", Published.MANUAL)], complete=True)
    assert files(tmp_path) == set()


def test_a_split_page_hosts_its_pieces_and_what_they_link(tmp_path: Path) -> None:
    built(tmp_path, "reports/a", "a", "")
    piece = tmp_path / UNPUBLISHED_DIR / "reports/a/report.part01.html"
    piece.write_text(f'<img src="{SITE}/reports/a/images/a.jpg">')
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images").mkdir()
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images/a.jpg").write_bytes(b"a")
    assert write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True) == []
    assert "reports/a/report.part01.html" in files(tmp_path)
    assert "reports/a/images/a.jpg" in files(tmp_path)
