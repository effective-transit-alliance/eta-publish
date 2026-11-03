"""`site/published/`: what an `automated` publication's live page links, and nothing else."""

from pathlib import Path

import pytest
from paths import HOST

from eta_publish.naming import PUBLISHED_DIR, UNPUBLISHED_DIR, path_kind
from eta_publish.published import referenced, write_published
from eta_publish.site import Publication, Published

PATH = "reports/r"


def test_what_the_fragment_links_at_the_site_is_what_it_needs() -> None:
    html = (
        f'<link rel="stylesheet" href="{HOST}/assets/publication.css">'
        f'<script src="{HOST}/assets/publication.js"></script>'
        f'<a href="{HOST}/{PATH}/images/a.jpg"><img src="{HOST}/{PATH}/images/web/a-800w.webp"'
        f' srcset="{HOST}/{PATH}/images/web/a-800w.avif 800w,'
        f' {HOST}/{PATH}/images/web/a-1600w.avif 1600w"></a>'
        f'<video src="{HOST}/{PATH}/videos/v.mp4" poster="{HOST}/{PATH}/images/p.jpg"></video>'
    )
    assert referenced(html, PATH, site_url=HOST) == {
        "assets/publication.css",
        "assets/publication.js",
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
    assert referenced(html, PATH, site_url=HOST) == set()


def test_a_relative_link_is_relative_to_the_publication() -> None:
    """What a `--no-hosted-media` fragment links: its pictures beside itself."""
    html = '<img src="images/a.jpg"><link href="../../assets/publication.css">'
    assert referenced(html, PATH, site_url=HOST) == {
        f"{PATH}/images/a.jpg",
        "assets/publication.css",
    }


def test_a_link_names_the_file_percent_encoded() -> None:
    html = f'<img src="{HOST}/{PATH}/images/Platform%20(east).jpg">'
    assert referenced(html, PATH, site_url=HOST) == {f"{PATH}/images/Platform (east).jpg"}


def test_a_link_out_of_the_site_is_refused() -> None:
    with pytest.raises(ValueError, match="outside the site"):
        referenced('<img src="../../../etc/passwd">', PATH, site_url=HOST)


def built(root: Path, path: str, doc_id: str, html: str) -> None:
    """A publication directory as a build leaves it, with a response saying which document it is,
    and the copies a live publication writes for `site/published/`."""
    directory = root / UNPUBLISHED_DIR / path
    directory.mkdir(parents=True)
    (directory / "doc.json").write_text(f'{{"documentId": "{doc_id}", "tabId": "t"}}')
    kind = path_kind(path)
    for stem in (f"{kind}", f"{kind}.published"):
        (directory / f"{stem}.html").write_text(html)
        (directory / f"{stem}.md").write_text("# r\n")
    (directory / "index.html").write_text("the preview")


def entry(doc_id: str, published: Published) -> Publication:
    return Publication(
        url=f"https://docs.google.com/document/d/{doc_id}/edit?tab=t",
        name=doc_id,
        tab="t",
        published=published,
    )


def files(root: Path) -> set[str]:
    out = root / PUBLISHED_DIR
    return {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


def test_only_an_automated_publication_is_hosted_and_only_what_it_links(tmp_path: Path) -> None:
    html = f'<img src="{HOST}/reports/a/images/a.jpg">'
    built(tmp_path, "reports/a", "a", html)
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images").mkdir()
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images/a.jpg").write_bytes(b"a")
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images/unused.jpg").write_bytes(b"u")
    built(tmp_path, "reports/m", "m", html)
    built(tmp_path, "reports/d", "d", html)
    publications = [
        entry("a", Published.AUTOMATED),
        entry("m", Published.MANUAL),
        entry("d", Published.DRAFT),
    ]

    assert write_published(tmp_path, publications, complete=True, site_url=HOST) == []
    assert files(tmp_path) == {
        "reports/a/report.html",
        "reports/a/report.md",
        "reports/a/images/a.jpg",
    }


def test_a_statement_publishes_as_a_statement(tmp_path: Path) -> None:
    built(tmp_path, "statements/s", "s", "")
    write_published(tmp_path, [entry("s", Published.AUTOMATED)], complete=True, site_url=HOST)
    assert files(tmp_path) == {"statements/s/statement.html", "statements/s/statement.md"}


def test_a_live_page_linking_a_missing_file_is_a_problem(tmp_path: Path) -> None:
    built(tmp_path, "reports/a", "a", f'<img src="{HOST}/reports/a/images/a.jpg">')
    publication = entry("a", Published.AUTOMATED)
    [(which, problem)] = write_published(tmp_path, [publication], complete=True, site_url=HOST)
    assert which == publication
    assert "`reports/a/images/a.jpg`" in problem
    # Without the pictures there is nothing to copy, which is not a problem.
    assert write_published(tmp_path, [publication], complete=False, site_url=HOST) == []


def test_a_publication_no_longer_automated_is_no_longer_hosted(tmp_path: Path) -> None:
    built(tmp_path, "reports/a", "a", "")
    write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True, site_url=HOST)
    assert files(tmp_path)
    write_published(tmp_path, [entry("a", Published.MANUAL)], complete=True, site_url=HOST)
    assert files(tmp_path) == set()


def test_a_split_page_hosts_its_pieces_and_what_they_link(tmp_path: Path) -> None:
    built(tmp_path, "reports/a", "a", "")
    for name in ("report.part01.html", "report.published.part01.html"):
        piece = tmp_path / UNPUBLISHED_DIR / "reports/a" / name
        piece.write_text(f'<img src="{HOST}/reports/a/images/a.jpg">')
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images").mkdir()
    (tmp_path / UNPUBLISHED_DIR / "reports/a/images/a.jpg").write_bytes(b"a")
    assert (
        write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True, site_url=HOST)
        == []
    )
    assert "reports/a/report.part01.html" in files(tmp_path)
    assert "reports/a/images/a.jpg" in files(tmp_path)


def test_a_publication_with_warnings_publishes_its_copies_without_them(tmp_path: Path) -> None:
    """Warnings are for reviewing a build; a published page, its Markdown and its PDF carry none."""
    built(tmp_path, "reports/a", "a", "")
    directory = tmp_path / UNPUBLISHED_DIR / "reports/a"
    (directory / "report.html").write_text('<div class="warnings">Warnings</div>')
    (directory / "report.published.md").write_text("clean")
    (directory / "report.pdf").write_bytes(b"warned")
    (directory / "report.published.pdf").write_bytes(b"clean")
    (directory / "report.published.html").write_text(
        f'<p>clean</p><a href="{HOST}/reports/a/report.pdf">PDF</a>'
    )
    assert (
        write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True, site_url=HOST)
        == []
    )
    published = tmp_path / PUBLISHED_DIR / "reports/a"
    assert (published / "report.html").read_text().startswith("<p>clean</p>")
    assert (published / "report.md").read_text() == "clean"
    assert (published / "report.pdf").read_bytes() == b"clean"
    assert not list(published.glob("report.published.*"))


def test_a_site_served_elsewhere_hosts_what_links_there() -> None:
    other = "https://reports.example.org"
    html = f'<img src="{other}/{PATH}/images/a.jpg"><img src="{HOST}/{PATH}/images/b.jpg">'
    assert referenced(html, PATH, other) == {f"{PATH}/images/a.jpg"}


def test_a_minified_page_is_hosted_with_the_minified_assets_and_their_maps(
    tmp_path: Path,
) -> None:
    """Named rather than read off it: its links are unquoted, and a map is linked from its file."""
    built(tmp_path, "reports/a", "a", "")
    directory = tmp_path / UNPUBLISHED_DIR / "reports/a"
    (directory / "report.min.html").write_text("the preview's")
    (directory / "report.published.min.html").write_text("the live page's")
    assets = tmp_path / UNPUBLISHED_DIR / "assets"
    assets.mkdir()
    for name in ("publication.min.css", "publication.min.js"):
        (assets / name).write_text(name)
        (assets / f"{name}.map").write_text("{}")

    assert (
        write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True, site_url=HOST)
        == []
    )
    assert files(tmp_path) == {
        "reports/a/report.html",
        "reports/a/report.md",
        "reports/a/report.min.html",
        "assets/publication.min.css",
        "assets/publication.min.css.map",
        "assets/publication.min.js",
        "assets/publication.min.js.map",
    }
    published = tmp_path / PUBLISHED_DIR / "reports/a/report.min.html"
    assert published.read_text() == "the live page's"


def test_a_split_page_hosts_the_minified_copy_of_each_piece(tmp_path: Path) -> None:
    """Each piece's own, published copy and not the preview's, and not itself as a piece."""
    built(tmp_path, "reports/a", "a", "")
    directory = tmp_path / UNPUBLISHED_DIR / "reports/a"
    for name in ("report.part01.html", "report.published.part01.html"):
        (directory / name).write_text("")
    (directory / "report.part01.min.html").write_text("the preview's")
    (directory / "report.published.part01.min.html").write_text("the live page's")
    assets = tmp_path / UNPUBLISHED_DIR / "assets"
    assets.mkdir()
    for name in ("publication.min.css", "publication.min.js"):
        (assets / name).write_text(name)
        (assets / f"{name}.map").write_text("{}")

    assert (
        write_published(tmp_path, [entry("a", Published.AUTOMATED)], complete=True, site_url=HOST)
        == []
    )
    hosted = files(tmp_path)
    assert "reports/a/report.part01.min.html" in hosted
    assert "reports/a/report.part01.min.min.html" not in hosted
    assert "assets/publication.min.js.map" in hosted
    published = tmp_path / PUBLISHED_DIR / "reports/a/report.part01.min.html"
    assert published.read_text() == "the live page's"
