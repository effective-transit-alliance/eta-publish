"""`eta-publish drafts preview`, with nothing uploaded and no Cloudflare reached.

What can go wrong here is what it uploads, to what name, with which token,
and that it says no before building or uploading when it should.
`upload` is replaced where the command is run, and `subprocess.run` where `upload` is.
"""

import os
import subprocess
from pathlib import Path

import pytest
from test_site import seed_image_index, write_list
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


def write_site(site: Path, *, published: bool = True) -> None:
    files = [
        "unpublished/index.html",
        "unpublished/reports/x/report.html",
        "unpublished/reports/x/doc.json",
    ]
    if published:
        files += ["published/reports/x/report.html", "published/reports/x/doc.json"]
    for name in files:
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)


def files_under(directory: Path) -> set[str]:
    return {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}


def test_staged_holds_what_is_served_without_doc_json(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_site(site)

    with preview.staged(site) as directory:
        assert files_under(directory) == {
            "index.html",
            "reports/x/report.html",
            "published/reports/x/report.html",
        }
        assert directory.parent == site.parent
        assert (directory / "index.html").stat().st_ino == (
            site / "unpublished" / "index.html"
        ).stat().st_ino

    assert not directory.exists()


def test_staged_is_removed_when_the_block_raises(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_site(site)

    seen: list[Path] = []
    with pytest.raises(ValueError, match="boom"), preview.staged(site) as directory:
        seen.append(directory)
        raise ValueError("boom")

    assert seen
    assert not seen[0].exists()


def test_staged_without_a_published_site_has_no_published_directory(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_site(site, published=False)

    with preview.staged(site) as directory:
        assert not (directory / "published").exists()


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
        self.calls: list[tuple[set[str], str, str]] = []

    def __call__(self, directory: Path, branch: str, token: str) -> None:
        self.calls.append((files_under(directory), branch, token))


def preview_drafts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str | None = "",
    refused: str | None = None,
) -> tuple[Result, Uploads]:
    """`eta-publish drafts preview` in a directory laid out as a checkout with `drafts/`.

    An empty `url` lists nothing, since the command forces the images on
    and a listed publication would try to download them.
    """
    monkeypatch.chdir(tmp_path)
    if url is not None:
        write_list(tmp_path / "drafts" / "publications.toml", url, listed=bool(url))
        if refused is None:
            seed_image_index(tmp_path / "drafts" / "site" / UNPUBLISHED_DIR)
    uploads = Uploads()

    def branch() -> str:
        if refused is not None:
            raise preview.Refused(refused)
        return "foo"

    monkeypatch.setattr(preview, "branch", branch)
    monkeypatch.setattr(preview, "token", lambda: "secret")
    monkeypatch.setattr(preview, "upload", uploads)
    result = CliRunner().invoke(app, ["drafts", "preview", "--no-archive", "--no-comments"])
    return result, uploads


def test_preview_uploads_the_built_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, uploads = preview_drafts(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    [(files, branch, token)] = uploads.calls
    assert branch == "foo"
    assert token == "secret"
    assert {"index.html", "robots.txt"} <= files
    assert "secret" not in result.output
    assert list((tmp_path / "drafts").glob(".site-preview-*")) == []


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


def test_preview_with_a_drafts_directory_but_no_list_says_which_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "drafts").mkdir()
    result, uploads = preview_drafts(tmp_path, monkeypatch, url=None)

    assert result.exit_code == 1
    assert "drafts/publications.toml" in result.output
    assert uploads.calls == []
