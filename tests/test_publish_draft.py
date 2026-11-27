"""`eta-publish publish`: a draft's entry, and what was saved for it, moved into the public list.

Laid out as a checkout is, with a clone of `eta-drafts` in `drafts/`,
since the command works on both lists where they are.
"""

import json
from pathlib import Path

import pytest
from docs_json import PUBLICATION_URL as URL
from paths import FIXTURE_DIR, HOSTS, SLUG
from typer.testing import CliRunner, Result

from eta_publish.__main__ import app
from eta_publish.archive import ARCHIVES_JSON
from eta_publish.build import IMAGES_JSON
from eta_publish.naming import UNPUBLISHED_DIR
from eta_publish.site import Published, load_publications

NAME = "Digging Out of a Very Deep Hole"
SITE = f'[site]\npublished = "{HOSTS.published}"\nunpublished = "{HOSTS.unpublished}"\n'

PUBLIC = (
    f"# The public list.\n{SITE}\n"
    '[[report]]\nname = "Live"\ntab = "Tab 1"\n'
    'url = "https://docs.google.com/document/d/live/edit?tab=t.0"\npublished = "manual"\n'
)

DRAFTS = (
    f"# The drafts.\n{SITE}\n"
    "# The one about the hole, which is the 2026 rewrite.\n"
    f'[[report]]\nname = "{NAME}"\ntab = "Draft 2"\nurl = "{URL}"\n'
    '# kept with it\npublished = "draft"\nnote = "a field nothing reads"\n'
    "\n"
    '[[statement]]\nname = "Other"\ntab = "Tab 1"\n'
    'url = "https://docs.google.com/document/d/other/edit?tab=t.0"\npublished = "draft"\n'
)


def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, saved: bool = True) -> Path:
    """Both lists, and what the drafts' last build saved for the report, as a fetch writes it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "publications.toml").write_text(PUBLIC)
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "publications.toml").write_text(DRAFTS)
    built = tmp_path / "drafts" / "site" / UNPUBLISHED_DIR / SLUG
    if saved:
        built.mkdir(parents=True)
        fixture = json.loads((FIXTURE_DIR / "doc.json").read_text())
        saved_as = {"documentId": "abc", "tabId": "t.1", "tabTitle": "Draft 2"}
        doc = {**fixture, **saved_as, "suggestions": "rejected"}
        (built / "doc.json").write_text(json.dumps(doc))
        (built / IMAGES_JSON).write_text((FIXTURE_DIR / IMAGES_JSON).read_text())
        (built / ARCHIVES_JSON).write_text("{}\n")
    return built


def publish(*args: str) -> Result:
    return CliRunner().invoke(app, ["publish", *args])


def unchanged(tmp_path: Path) -> bool:
    return (tmp_path / "publications.toml").read_text() == PUBLIC and (
        tmp_path / "drafts" / "publications.toml"
    ).read_text() == DRAFTS


def test_publish_moves_the_entry_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In its own table, with its comments and fields, and only `published` changed.

    To `automated` with no `--as`, since new publications should be automated.
    """
    checkout(tmp_path, monkeypatch)
    result = publish(NAME.upper())
    assert result.exit_code == 0, result.output

    public = (tmp_path / "publications.toml").read_text()
    assert public.startswith(PUBLIC)
    assert public.removeprefix(PUBLIC) == (
        "\n# The one about the hole, which is the 2026 rewrite.\n"
        f'[[report]]\nname = "{NAME}"\ntab = "Draft 2"\nurl = "{URL}"\n'
        '# kept with it\npublished = "automated"\nnote = "a field nothing reads"\n'
    )
    assert (tmp_path / "drafts" / "publications.toml").read_text() == (
        f"# The drafts.\n{SITE}\n"
        '[[statement]]\nname = "Other"\ntab = "Tab 1"\n'
        'url = "https://docs.google.com/document/d/other/edit?tab=t.0"\npublished = "draft"\n'
    )
    assert "commit in both repositories" in result.stderr
    assert result.stdout == ""


def test_a_published_draft_builds_offline_in_the_public_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What was saved for it moves, and the public list builds it from that with no fetch.

    As `manual`, which `--as manual` says.
    The other entries here were never built, so have nothing saved, and fail offline:
    only this one's outcome is the point.
    """
    built = checkout(tmp_path, monkeypatch)
    result = publish(NAME, "--as", "manual")
    assert result.exit_code == 0, result.output
    assert load_publications(tmp_path / "publications.toml")[-1].published is Published.MANUAL
    moved = tmp_path / "site" / UNPUBLISHED_DIR / SLUG
    assert not built.exists()
    assert sorted(p.name for p in moved.iterdir()) == [ARCHIVES_JSON, "doc.json", IMAGES_JSON]
    assert f"drafts/site/{UNPUBLISHED_DIR}/{SLUG}" in result.stderr

    result = CliRunner().invoke(
        app, ["all", "--offline", "--no-images", "--no-archive", "--no-comments"]
    )
    public = result.output.partition("drafts/publications.toml")[0]
    assert f"✓ {SLUG} · {NAME}" in public, result.output
    assert (moved / "report.html").is_file()


def test_publish_by_url_as_copied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A URL out of the address bar, with what the browser added, names the same draft."""
    checkout(tmp_path, monkeypatch)
    result = publish(f"{URL}&pli=1#heading=h.x")
    assert result.exit_code == 0, result.output
    assert load_publications(tmp_path / "publications.toml")[-1].name == NAME


def test_publish_with_nothing_saved_moves_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A draft never built has nothing to move, and the entry is all there is to publish."""
    checkout(tmp_path, monkeypatch, saved=False)
    result = publish(NAME)
    assert result.exit_code == 0, result.output
    assert load_publications(tmp_path / "publications.toml")[-1].name == NAME
    assert "nothing saved for it" in result.stderr


def test_publish_refuses_to_publish_as_a_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A draft moved into the public list is out, so `draft` is not one of the ways it can be."""
    checkout(tmp_path, monkeypatch)
    result = publish(NAME, "--as", "draft")
    assert result.exit_code != 0
    assert "--as" in result.output
    assert unchanged(tmp_path)


def test_publish_refuses_what_is_not_a_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name the public list has is not a draft, though it names a publication."""
    checkout(tmp_path, monkeypatch)
    result = publish("Live")
    assert result.exit_code != 0
    assert "lists no draft named or at `Live`" in result.output
    assert unchanged(tmp_path)


def test_publish_refuses_a_name_two_drafts_have(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two tabs of one document are two drafts by one name, and only the URL says which."""
    checkout(tmp_path, monkeypatch)
    drafts = tmp_path / "drafts" / "publications.toml"
    two = drafts.read_text() + (
        f'\n[[report]]\nname = "{NAME}"\ntab = "Draft 3"\n'
        'url = "https://docs.google.com/document/d/abc/edit?tab=t.2"\npublished = "draft"\n'
    )
    drafts.write_text(two)
    result = publish(NAME)
    assert result.exit_code != 0
    assert "more than one draft is named" in result.output
    assert drafts.read_text() == two
    assert (tmp_path / "publications.toml").read_text() == PUBLIC


def test_publish_refuses_a_document_the_public_list_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two entries for one document publish it twice to one path, as `add` refuses."""
    checkout(tmp_path, monkeypatch)
    public = tmp_path / "publications.toml"
    listed = PUBLIC + f'\n[[report]]\nname = "A"\ntab = "B"\nurl = "{URL}"\npublished = "manual"\n'
    public.write_text(listed)
    result = publish(NAME)
    assert result.exit_code != 0
    assert "already lists" in result.output
    assert public.read_text() == listed
    assert (tmp_path / "drafts" / "publications.toml").read_text() == DRAFTS


def test_publish_refuses_a_path_the_public_site_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Something there already is a publication there, which a draft never replaces."""
    built = checkout(tmp_path, monkeypatch)
    there = tmp_path / "site" / UNPUBLISHED_DIR / SLUG
    there.mkdir(parents=True)
    result = publish(NAME)
    assert result.exit_code != 0
    assert "is there already" in result.output
    assert unchanged(tmp_path)
    assert (built / "doc.json").is_file()
