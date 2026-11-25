"""The drafts site: its layout, its index, its hosts, and `eta-publish drafts site`.

Built from saved responses, so nothing here reaches Google or Cloudflare.
"""

import json
from pathlib import Path

import pytest
from test_site import FIXTURE, SLUG, seed_image_index
from typer.testing import CliRunner, Result

from eta_publish import drafts_site
from eta_publish.__main__ import app
from eta_publish.naming import UNPUBLISHED_DIR
from eta_publish.parse import parse
from eta_publish.preview import PRODUCTION_URL, Refused
from eta_publish.site import Built, Hosts, Publication, Published, Site


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def files_under(directory: Path) -> dict[str, str]:
    return {
        p.relative_to(directory).as_posix(): p.read_text()
        for p in directory.rglob("*")
        if p.is_file()
    }


def tree(root: Path, listed: str, files: dict[str, str]) -> drafts_site.Tree:
    write(root, files)
    return drafts_site.Tree(listed=Path(listed), built=root, site=Site())


def test_assemble_lays_every_list_out_as_one_tree(tmp_path: Path) -> None:
    public = tree(
        tmp_path / "public",
        "publications.toml",
        {
            "unpublished/index.html": "public index",
            "unpublished/index.min.html": "public index, minified",
            "unpublished/robots.txt": "robots",
            "unpublished/assets/page.css": "css",
            "unpublished/reports/a/report.html": "a",
            "unpublished/reports/a/doc.json": "{}",
            "published/reports/a/report.html": "a, published",
        },
    )
    drafts = tree(
        tmp_path / "drafts",
        "drafts/publications.toml",
        {
            "unpublished/index.html": "drafts index",
            "unpublished/robots.txt": "robots",
            "unpublished/assets/page.css": "css",
            "unpublished/reports/b/report.html": "b",
            "unpublished/reports/b/doc.json": "{}",
        },
    )
    into = tmp_path / "site"

    drafts_site.assemble([public, drafts], into, "the index")

    served = files_under(into)
    assert served.pop("assets/logo.svg")
    assert served == {
        "index.html": "the index",
        "robots.txt": "robots",
        "assets/page.css": "css",
        "reports/a/report.html": "a",
        "reports/b/report.html": "b",
        "published/reports/a/report.html": "a, published",
    }
    assert (into / "reports/b/report.html").stat().st_ino == (
        tmp_path / "drafts/unpublished/reports/b/report.html"
    ).stat().st_ino


def test_assemble_refuses_a_shared_file_the_builds_disagree_on(tmp_path: Path) -> None:
    public = tree(tmp_path / "public", "publications.toml", {"unpublished/assets/page.css": "one"})
    drafts = tree(
        tmp_path / "drafts", "drafts/publications.toml", {"unpublished/assets/page.css": "two"}
    )
    into = tmp_path / "site"

    with pytest.raises(Refused) as refused:
        drafts_site.assemble([public, drafts], into, "the index")

    said = str(refused.value)
    assert "`/assets/page.css`" in said
    assert "`publications.toml`" in said
    assert "`drafts/publications.toml`" in said
    assert not into.exists()


def built(published: Published, path: str) -> Built:
    publication = Publication(url=path, name=path, tab="Draft", published=published)
    return Built(publication=publication, doc=parse(FIXTURE), path=path)


def test_the_index_groups_every_list_by_kind() -> None:
    public = Site(
        built=[built(Published.AUTOMATED, "reports/a"), built(Published.MANUAL, "reports/m")]
    )
    drafts = Site(built=[built(Published.DRAFT, "reports/d")])

    page = drafts_site.index_page([public, drafts])

    draft = page.index("Draft</h2>")
    automated = page.index("Automatically Published</h2>")
    manual = page.index("Manually Published</h2>")
    assert draft < page.index('href="reports/d/"') < automated
    assert automated < page.index('href="reports/a/"') < manual
    assert manual < page.index('href="reports/m/"')


def test_the_index_says_when_a_kind_has_none() -> None:
    page = drafts_site.index_page([Site(built=[built(Published.DRAFT, "reports/d")])])

    assert page.count("None yet.") == 2


def test_the_index_says_each_kind_as_its_pages_banners_do() -> None:
    """Less what only one publication has to link: its live page, and the file pasted live."""
    page = drafts_site.index_page([Site(built=[built(Published.DRAFT, "reports/d")])])

    etany = '<a href="https://www.etany.org">etany.org</a>'
    repository = "https://github.com/effective-transit-alliance/eta-publish"
    assert '<p class="kind-says">not published yet</p>' in page
    assert f'<p class="kind-says">live on {etany}</p>' in page
    assert (
        f'<p class="kind-says">live on {etany} using '
        f'<a href="{repository}"><code>eta-publish</code></a></p>'
    ) in page


def test_the_hosts_are_production_on_main_and_the_preview_elsewhere() -> None:
    assert drafts_site.hosts("main") == Hosts(
        published=f"{PRODUCTION_URL}/published", unpublished=PRODUCTION_URL
    )
    assert drafts_site.hosts("Fix/API") == Hosts(
        published="https://fix-api.eta-drafts.pages.dev/published",
        unpublished="https://fix-api.eta-drafts.pages.dev",
    )


def test_a_drafts_list_served_anywhere_else_is_refused() -> None:
    listed = Hosts(published=f"{PRODUCTION_URL}/elsewhere", unpublished=PRODUCTION_URL)

    with pytest.raises(Refused, match="elsewhere"):
        drafts_site.drafts_hosts(listed, "main")


def write_list(path: Path, url: str | None, published: str) -> None:
    """A list at the drafts site's hosts, of the fixture at `url` if there is one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    hosts = drafts_site.DRAFTS_HOSTS
    path.write_text(
        f'[site]\npublished = "{hosts.published}"\nunpublished = "{hosts.unpublished}"\n\n'
        + (
            "[[report]]\n"
            'name = "Digging Out of a Very Deep Hole"\n'
            'tab = "Draft 2"\n'
            f'url = "{url}"\n'
            f'published = "{published}"\n'
            if url
            else ""
        )
    )


def build_drafts_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, clash: bool) -> Result:
    """`eta-publish drafts site out` with the fixture in `publications.toml`,
    and in `drafts/publications.toml` too, at the same path, if `clash`."""
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    write_list(tmp_path / "publications.toml", str(saved), "manual")
    write_list(tmp_path / "drafts" / "publications.toml", str(saved) if clash else None, "draft")
    for site in ("site", "drafts/site"):
        seed_image_index(tmp_path / site / UNPUBLISHED_DIR)
    return CliRunner().invoke(
        app, ["drafts", "site", "out", "--no-images", "--no-archive", "--no-comments"]
    )


def test_drafts_site_builds_both_lists_into_one_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = build_drafts_site(tmp_path, monkeypatch, clash=False)

    assert result.exit_code == 0, result.output
    out = tmp_path / "out"
    assert (out / SLUG / "report.html").is_file()
    assert not (out / SLUG / "doc.json").exists()
    assert "Manually Published" in (out / SLUG / "index.html").read_text()
    assert "ETA drafts" in (out / "index.html").read_text()
    assert not (tmp_path / "site" / UNPUBLISHED_DIR / SLUG / "report.html").exists()
    assert list((tmp_path / "drafts").glob(".site-deploy-*")) == []


def test_drafts_site_refuses_two_lists_with_a_publication_at_one_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = build_drafts_site(tmp_path, monkeypatch, clash=True)

    assert result.exit_code == 1
    said = " ".join(result.output.split())
    assert "in `publications.toml`" in said
    assert "in `drafts/publications.toml`" in said
    assert f"both at `/{SLUG}`" in said
    assert not (tmp_path / "out").exists()


def test_drafts_site_refuses_a_directory_with_something_in_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x").write_text("x")
    result = build_drafts_site(tmp_path, monkeypatch, clash=False)

    assert result.exit_code == 1
    assert (tmp_path / "out" / "x").read_text() == "x"
