"""`eta-publish drafts preview`, with nothing uploaded and no Cloudflare reached.

What can go wrong here is what it uploads, to what name, with which token,
and that it says no before building or uploading when it should.
`upload` is replaced where the command is run, and `subprocess.run` where `upload` is.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from test_site import FIXTURE, SLUG, seed_image_index
from typer.testing import CliRunner, Result

import eta_publish.build as build_module
import eta_publish.preview as preview
from eta_publish.__main__ import app
from eta_publish.naming import UNPUBLISHED_DIR


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # A commit hook sets these for the repository being committed to,
    # and they would send every `git` here to it rather than to `path`.
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "commit", "--allow-empty", "-m", "x")
    monkeypatch.setattr(preview, "ROOT", path)
    return path


def test_branch_refuses_main(repo: Path) -> None:
    with pytest.raises(preview.Refused, match="main"):
        preview.branch()


def test_branch_is_the_branch_it_is_on(repo: Path) -> None:
    git(repo, "checkout", "-b", "foo")

    assert preview.branch() == "foo"


def test_branch_refuses_a_detached_head(repo: Path) -> None:
    git(repo, "checkout", "--detach")

    with pytest.raises(preview.Refused):
        preview.branch()


def commit_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_local_name_is_the_branch_and_its_commit(repo: Path) -> None:
    """Never the branch's own name, which is CI's preview of it."""
    git(repo, "checkout", "-b", "foo")

    assert preview.local_name() == f"foo-{commit_of(repo)}"


def test_local_name_says_dirty_with_an_edited_tracked_file(repo: Path) -> None:
    git(repo, "checkout", "-b", "foo")
    (repo / "a").write_text("1")
    git(repo, "add", "a")
    git(repo, "commit", "-m", "a")
    (repo / "a").write_text("2")

    assert preview.local_name() == f"foo-{commit_of(repo)}-dirty"


def test_local_name_does_not_count_an_untracked_file(repo: Path) -> None:
    git(repo, "checkout", "-b", "foo")
    (repo / "notes.pdf").write_text("")

    assert preview.local_name() == f"foo-{commit_of(repo)}"


def test_local_name_refuses_main(repo: Path) -> None:
    with pytest.raises(preview.Refused, match="main"):
        preview.local_name()


def test_token_refuses_a_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preview, "TOKEN", tmp_path / "t")

    with pytest.raises(preview.Refused):
        preview.token()


def test_token_refuses_a_blank_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "t").write_text("  \n")
    monkeypatch.setattr(preview, "TOKEN", tmp_path / "t")

    with pytest.raises(preview.Refused):
        preview.token()


def test_token_is_the_file_trimmed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "t").write_text("abc\n")
    monkeypatch.setattr(preview, "TOKEN", tmp_path / "t")

    assert preview.token() == "abc"


def files_under(directory: Path) -> dict[str, str]:
    return {
        p.relative_to(directory).as_posix(): p.read_text(errors="replace")
        for p in directory.rglob("*")
        if p.is_file()
    }


class Recorder:
    """Stands in for `subprocess.run`."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, self.returncode)


def test_upload_runs_wrangler_with_the_token_only_in_its_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Recorder()
    monkeypatch.setattr(preview.subprocess, "run", run)

    preview.upload(tmp_path, "foo", "secret")

    [(command, kwargs)] = run.calls
    assert command[:10] == [
        "mise",
        "x",
        "--",
        "bun",
        "x",
        "--bun",
        preview.WRANGLER,
        "pages",
        "deploy",
        str(tmp_path.resolve()),
    ]
    assert ["--project-name", "eta-drafts"] in [command[i : i + 2] for i in range(len(command))]
    assert ["--branch", "foo"] in [command[i : i + 2] for i in range(len(command))]
    assert "secret" not in command
    assert kwargs["cwd"] == preview.ROOT
    environment = kwargs["env"]
    assert isinstance(environment, dict)
    assert environment["CLOUDFLARE_API_TOKEN"] == "secret"
    assert environment["CLOUDFLARE_ACCOUNT_ID"] == preview.ACCOUNT_ID
    assert environment["WRANGLER_SEND_METRICS"] == "false"


def test_upload_raises_when_wrangler_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preview.subprocess, "run", Recorder(returncode=1))

    with pytest.raises(RuntimeError):
        preview.upload(tmp_path, "foo", "secret")


def test_upload_says_when_mise_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("mise")

    monkeypatch.setattr(preview.subprocess, "run", missing)

    with pytest.raises(RuntimeError, match="mise"):
        preview.upload(tmp_path, "foo", "secret")


class Uploads:
    """Stands in for `preview.upload`, recording what it was given."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], str, str]] = []

    def __call__(self, directory: Path, branch: str, token: str) -> None:
        self.calls.append((files_under(directory), branch, token))


def write_drafts_list(path: Path, url: str, hosts: tuple[str, str]) -> None:
    """The drafts' list: a `[site]` at `hosts`, published then unpublished, and `url` if any."""
    path.parent.mkdir(parents=True, exist_ok=True)
    published, unpublished = hosts
    path.write_text(
        f'[site]\npublished = "{published}"\nunpublished = "{unpublished}"\n\n'
        + (
            "[[report]]\n"
            + 'name = "Digging Out of a Very Deep Hole"\n'
            + 'tab = "Draft 2"\n'
            + f'url = "{url}"\n'
            + 'published = "draft"\n'
            if url
            else ""
        )
    )


HOSTS = (f"{preview.PRODUCTION_URL}/published", preview.PRODUCTION_URL)
"""The drafts site's `[site]`, published then unpublished."""


def preview_drafts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str | None = "",
    refused: str | None = None,
    hosts: tuple[str, str] = HOSTS,
    branch: str = "foo",
) -> tuple[Result, Uploads]:
    """`eta-publish drafts preview` in a directory laid out as a checkout with `drafts/`,
    and a `publications.toml` with nothing on it.

    An empty `url` lists nothing, since the command forces the images on
    and a listed publication would try to download them.
    """
    monkeypatch.chdir(tmp_path)
    # This repository's list, with nothing on it, since the drafts are what these tests are about.
    write_drafts_list(tmp_path / "publications.toml", "", HOSTS)
    if url is not None:
        write_drafts_list(tmp_path / "drafts" / "publications.toml", url, hosts)
        if refused is None:
            seed_image_index(tmp_path / "drafts" / "site" / UNPUBLISHED_DIR)
    uploads = Uploads()

    def named() -> str:
        if refused is not None:
            raise preview.Refused(refused)
        return branch

    monkeypatch.setattr(preview, "local_name", named)
    monkeypatch.setattr(preview, "token", lambda: "secret")
    monkeypatch.setattr(preview, "upload", uploads)
    result = CliRunner().invoke(app, ["drafts", "preview", "--no-archive", "--no-comments"])
    return result, uploads


def test_preview_uploads_the_drafts_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, uploads = preview_drafts(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    [(files, branch, token)] = uploads.calls
    assert branch == "foo"
    assert token == "secret"
    assert {"index.html", "robots.txt"} <= files.keys()
    assert "ETA drafts" in files["index.html"]
    assert "secret" not in result.output
    assert list((tmp_path / "drafts").glob(".site-deploy-*")) == []


def test_preview_uploads_every_list_laid_out_as_one_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drafts beside this repository's own, each page labeled with its kind."""
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    result, uploads = preview_drafts(tmp_path, monkeypatch, url=str(saved))

    assert result.exit_code == 0, result.output
    [(files, _, _)] = uploads.calls
    assert "Draft" in files[f"{SLUG}/index.html"]
    assert f"{SLUG}/doc.json" not in files
    assert not (tmp_path / "drafts" / "site" / UNPUBLISHED_DIR / SLUG / "report.html").exists()


def test_preview_refused_builds_and_uploads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, uploads = preview_drafts(tmp_path, monkeypatch, refused="nope")

    assert result.exit_code == 1
    assert "nope" in result.output
    assert uploads.calls == []
    assert not (tmp_path / "drafts" / "site").exists()


def test_preview_without_a_drafts_list_uploads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, uploads = preview_drafts(tmp_path, monkeypatch, url=None)

    assert result.exit_code == 1
    assert uploads.calls == []


def test_preview_with_a_failed_draft_uploads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(*args: object, **kwargs: object) -> object:
        raise RuntimeError("Google is not answering")

    monkeypatch.setattr(build_module, "fetch", unreachable, raising=False)

    result, uploads = preview_drafts(
        tmp_path, monkeypatch, url="https://docs.google.com/document/d/abc/edit?tab=t.1"
    )

    assert result.exit_code == 1
    assert uploads.calls == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("foo", "foo"),
        ("Foo", "foo"),
        ("fix/api", "fix-api"),
        ("a_b.c", "a-b-c"),
        ("v1--x", "v1--x"),
    ],
)
def test_alias_lowercases_and_hyphenates_what_is_not_alphanumeric(name: str, expected: str) -> None:
    assert preview.alias(name) == expected


@pytest.mark.parametrize("name", ["/x", "x/", "-x", "é", "a" * 64])
def test_alias_refuses_what_cloudflare_does_not_say(name: str) -> None:
    with pytest.raises(preview.Refused):
        preview.alias(name)


def test_alias_allows_the_longest_label() -> None:
    assert preview.alias("a" * 63) == "a" * 63


def test_previewed_moves_production_to_the_branch_with_the_same_paths() -> None:
    hosts = preview.Hosts(
        published=f"{preview.PRODUCTION_URL}/published", unpublished=preview.PRODUCTION_URL
    )

    assert preview.previewed(hosts, "Fix/API") == preview.Hosts(
        published="https://fix-api.eta-drafts.pages.dev/published",
        unpublished="https://fix-api.eta-drafts.pages.dev",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://eta-drafts.pages.dev.example.com",
        "https://other.eta-drafts.pages.dev",
        "https://eta-drafts.pages.devx/published",
    ],
)
def test_previewed_refuses_a_host_that_is_not_production(url: str) -> None:
    with pytest.raises(preview.Refused, match="not at"):
        preview.previewed(preview.Hosts(published=url, unpublished=preview.PRODUCTION_URL), "foo")


def test_preview_builds_the_fragments_at_the_branchs_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({**FIXTURE, "tabTitle": "Draft 2"}))
    result, uploads = preview_drafts(tmp_path, monkeypatch, url=str(saved), branch="Fix/API")

    assert result.exit_code == 0, result.output
    [(files, branch, _)] = uploads.calls
    assert "https://fix-api.eta-drafts.pages.dev" in files[f"{SLUG}/report.html"]
    for name, text in files.items():
        if name.endswith(".html"):
            assert f"{preview.PRODUCTION_URL}" not in text, name
    assert branch == "Fix/API"


def test_preview_with_a_host_that_is_not_production_builds_and_uploads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, uploads = preview_drafts(
        tmp_path,
        monkeypatch,
        hosts=("https://example.com/published", "https://example.com"),
    )

    assert result.exit_code == 1
    assert "https://example.com" in result.output
    assert uploads.calls == []
    assert not (tmp_path / "drafts" / "site" / UNPUBLISHED_DIR / "index.html").exists()


def test_preview_leaves_the_committed_drafts_hosts_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = preview_drafts(tmp_path, monkeypatch, branch="foo")

    assert result.exit_code == 0, result.output
    assert preview.PRODUCTION_URL in (tmp_path / "drafts" / "publications.toml").read_text()


def test_preview_with_a_drafts_directory_but_no_list_says_which_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "drafts").mkdir()
    result, uploads = preview_drafts(tmp_path, monkeypatch, url=None)

    assert result.exit_code == 1
    assert "drafts/publications.toml" in result.output
    assert uploads.calls == []


def test_ci_token_refuses_outside_github_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret")

    with pytest.raises(preview.Refused, match="GitHub Actions"):
        preview.ci_token()
    assert os.environ["CLOUDFLARE_API_TOKEN"] == "secret"


def test_ci_token_refuses_a_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", " ")

    with pytest.raises(preview.Refused, match="CLOUDFLARE_API_TOKEN"):
        preview.ci_token()


def test_ci_token_takes_the_token_out_of_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret\n")

    assert preview.ci_token() == "secret"
    assert "CLOUDFLARE_API_TOKEN" not in os.environ


def deploy_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, branch: str
) -> tuple[Result, Uploads]:
    """`eta-publish drafts deploy --branch <branch>`, laid out as `preview_drafts` lays it out."""
    monkeypatch.chdir(tmp_path)
    write_drafts_list(tmp_path / "publications.toml", "", HOSTS)
    write_drafts_list(tmp_path / "drafts" / "publications.toml", "", HOSTS)
    uploads = Uploads()
    monkeypatch.setattr(preview, "upload", uploads)
    result = CliRunner().invoke(
        app, ["drafts", "deploy", "--branch", branch, "--no-archive", "--no-comments"]
    )
    return result, uploads


def test_deploy_refuses_outside_github_actions_and_uploads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret")
    result, uploads = deploy_drafts(tmp_path, monkeypatch, "main")

    assert result.exit_code == 1
    assert "GitHub Actions" in " ".join(result.output.split())
    assert uploads.calls == []


@pytest.mark.parametrize("branch", ["main", "Fix/API"])
def test_deploy_in_github_actions_uploads_the_drafts_site_for_any_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, branch: str
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret")
    result, uploads = deploy_drafts(tmp_path, monkeypatch, branch)

    assert result.exit_code == 0, result.output
    [(files, deployed, token)] = uploads.calls
    assert deployed == branch
    assert token == "secret"
    assert "ETA drafts" in files["index.html"]
    assert "secret" not in result.output
