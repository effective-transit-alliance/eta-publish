"""`scripts/drafts-commit.sh`, the drafts commit for each code commit, in repositories made here.

What can go wrong is which drafts commit a code commit's goes on,
on which branch, and what is dropped to put it there,
so the build is a stand-in `uv` that writes the code commit it ran with into `drafts/site/`.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "drafts-commit.sh"

# A stand-in for `uv run eta-publish all ...`: it writes `HEAD`'s message into the site,
# or wherever `--into` says, so a drafts commit's tree says which code it was built with.
FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
out=drafts/site
while (($# > 0)); do
    if [[ $1 == --into ]]; then
        out="$2"
    fi
    shift
done
mkdir -p "$out"
git log -1 --format=%s HEAD > "$out/built-with"
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An `eta-publish` checkout with `drafts/` in it, whose `main` pins the code's first commit."""
    # A commit hook sets these for the repository being committed to,
    # and they would send every `git` here to it.
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
    # None of this machine's own configuration, hooks included.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "t")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "t@example.com")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text(FAKE_UV)
    (bin_dir / "uv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    repo = tmp_path / "eta-publish"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / ".gitignore").write_text("/drafts/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-m", "code 1")

    drafts = repo / "drafts"
    drafts.mkdir()
    git(drafts, "init", "-b", "main")
    (drafts / "publications.toml").write_text("")
    git(drafts, "add", "publications.toml")
    git(drafts, "commit", "-m", "Start the drafts list")
    first = git(repo, "rev-parse", "HEAD")
    # As `eta-drafts` has it: a submodule never checked out,
    # whose directory a clone leaves empty, as git does with any submodule not checked out.
    (drafts / ".gitmodules").write_text(
        '[submodule "eta-publish"]\n\tpath = eta-publish\n\turl = ../eta-publish\n\tupdate = none\n'
    )
    (drafts / "eta-publish").mkdir()
    git(drafts, "add", ".gitmodules")
    git(drafts, "update-index", "--add", "--cacheinfo", f"160000,{first},eta-publish")
    git(drafts, "commit", "-m", "Pin `eta-publish`")
    return repo


def commit_code(repo: Path, message: str, *args: str) -> str:
    (repo / "code").write_text(message)
    git(repo, "add", "code")
    git(repo, "commit", "-m", message, *args)
    return git(repo, "rev-parse", "HEAD")


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args], cwd=repo, check=False, capture_output=True, text=True
    )


def drafts_log(repo: Path, ref: str = "HEAD") -> list[str]:
    """`ref`'s drafts commits, newest first, as `<pin> <subject>`."""
    drafts = repo / "drafts"
    log = []
    for commit in git(drafts, "rev-list", "--first-parent", ref).splitlines():
        pinned = subprocess.run(
            ["git", "rev-parse", "--quiet", "--verify", f"{commit}:eta-publish"],
            cwd=drafts,
            capture_output=True,
            text=True,
        )
        if pinned.returncode == 0:
            subject = git(drafts, "log", "-1", "--format=%s", commit)
            log.append(f"{pinned.stdout.strip()} {subject}")
    return log


def test_head_pins_the_commit_and_rebuilds_with_it(code: Path) -> None:
    second = commit_code(code, "code 2")
    result = run(code, "head")
    assert result.returncode == 0, result.stderr
    drafts = code / "drafts"
    assert git(drafts, "rev-parse", "HEAD:eta-publish") == second
    assert (drafts / "site" / "built-with").read_text() == "code 2\n"
    assert git(drafts, "log", "-1", "--format=%s") == f"`eta-publish` {second[:7]}: code 2"
    trailers = git(drafts, "log", "-1", "--format=%(trailers:key=eta-publish-commit,valueonly)")
    assert trailers == second
    assert git(drafts, "status", "--porcelain") == ""


def test_each_commit_gets_its_own(code: Path) -> None:
    second = commit_code(code, "code 2")
    run(code, "head")
    third = commit_code(code, "code 3")
    run(code, "head")
    assert [line.split()[0] for line in drafts_log(code)][:2] == [third, second]


def test_an_amend_replaces_the_drafts_commit(code: Path) -> None:
    commit_code(code, "code 2")
    run(code, "head")
    amended = commit_code(code, "code 2, amended", "--amend")
    result = run(code, "head")
    assert result.returncode == 0, result.stderr
    assert "dropping 1" in result.stderr
    log = drafts_log(code)
    assert log[0] == f"{amended} `eta-publish` {amended[:7]}: code 2, amended"
    # Then the pin made by hand, of the commit before.
    assert log[1].endswith("Pin `eta-publish`")


def test_a_code_branch_gets_a_drafts_branch_of_its_own(code: Path) -> None:
    git(code, "switch", "-c", "foo")
    on_foo = commit_code(code, "on foo")
    result = run(code, "head")
    assert result.returncode == 0, result.stderr
    drafts = code / "drafts"
    assert git(drafts, "branch", "--show-current") == "foo"
    assert git(drafts, "rev-parse", "foo:eta-publish") == on_foo
    assert drafts_log(code, "main")[0].endswith("Pin `eta-publish`")


def test_a_commit_after_a_gap_is_left_to_ci(code: Path) -> None:
    commit_code(code, "code 2")
    commit_code(code, "code 3")
    result = run(code, "head")
    assert result.returncode == 0, result.stderr
    assert "left to CI" in result.stderr
    assert drafts_log(code)[0].endswith("Pin `eta-publish`")


def test_uncommitted_code_is_not_built(code: Path) -> None:
    commit_code(code, "code 2")
    (code / "code").write_text("not committed")
    result = run(code, "head")
    assert "left to CI" in result.stderr
    assert drafts_log(code)[0].endswith("Pin `eta-publish`")


def test_a_commit_made_by_hand_is_never_dropped(code: Path) -> None:
    commit_code(code, "code 2")
    run(code, "head")
    drafts = code / "drafts"
    (drafts / "publications.toml").write_text("# pulled\n")
    git(drafts, "commit", "-am", "Pull the drafts")
    commit_code(code, "code 2, amended", "--amend")
    result = run(code, "head")
    assert result.returncode == 1
    assert "Pull the drafts" in result.stderr
    assert git(drafts, "log", "-1", "--format=%s") == "Pull the drafts"


def test_missing_lists_every_commit_with_no_drafts_commit_oldest_first(code: Path) -> None:
    second = commit_code(code, "code 2")
    third = commit_code(code, "code 3")
    result = run(code, "missing", "main")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [second, third]
    git(code, "checkout", "--quiet", "--detach", second)
    assert run(code, "commit").returncode == 0
    git(code, "checkout", "--quiet", "main")
    assert run(code, "missing", "main").stdout.split() == [third]


def test_missing_counts_both_sides_of_a_merge(code: Path) -> None:
    """Each side of a merge is pinned in turn, and neither pin has the other in its history,
    so going by the last pin alone lists the other side again, forever."""
    git(code, "switch", "--quiet", "-c", "side")
    # A file of its own, so the merge has nothing to resolve.
    (code / "side").write_text("on side")
    git(code, "add", "side")
    git(code, "commit", "-m", "on side")
    side = git(code, "rev-parse", "HEAD")
    git(code, "switch", "--quiet", "main")
    on_main = commit_code(code, "on main")
    for pinned in (on_main, side):
        git(code, "checkout", "--quiet", "--detach", pinned)
        assert run(code, "commit").returncode == 0
    git(code, "switch", "--quiet", "main")
    git(code, "merge", "--quiet", "--no-ff", "-m", "merge side", "side")
    merge = git(code, "rev-parse", "HEAD")
    result = run(code, "missing", "main")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [merge]


def test_check_builds_without_touching_the_drafts(code: Path) -> None:
    commit_code(code, "code 2")
    result = run(code, "check")
    assert result.returncode == 0, result.stderr
    assert not (code / "drafts" / "site").exists()
    assert not list(code.glob(".drafts-check-*"))
