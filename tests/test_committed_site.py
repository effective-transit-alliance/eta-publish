"""The committed site is what an offline build of it writes, and holds up as published.

`site/` is the site this project publishes, and every file in it a build wrote:
the reports, the index, the shared assets. A change to the code changes what a
build writes, so a commit that leaves `site/` as the old code wrote it publishes
pages no commit of the code would produce. This rebuilds all of it, offline and
without the images, and compares. It runs in the background from the moment
collection ends, so it costs the suite about what the slowest test does.

When it differs, read the diff: it is exactly what the change does to the
published reports. Accept it with `pytest --regenerate-snapshots`.

The rest of this file asks of every report what a published report has to be,
whatever document it came from: what `test_real_document.py` asks of one.
"""

import difflib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from paths import ROOT, SITE

from eta_publish.emit.html import CODE_BLOCK_LIMIT


def committed() -> set[str]:
    """Every file under `site/` in the index, relative to `site/`.

    The index rather than the working tree, because the index is the commit:
    a file the build writes that is not staged is a commit missing it.
    Read from the working tree, which a commit hook has made the index.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "site"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return {path.removeprefix("site/") for path in listed.split("\0") if path}


def published(built: Path) -> set[str]:
    """Every file the build wrote that `.gitignore` does not leave out."""
    written = sorted(p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file())
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input="\n".join(f"site/{path}" for path in written),
        capture_output=True,
        text=True,
    ).stdout.split()
    return set(written) - {path.removeprefix("site/") for path in ignored}


def test_the_committed_site_is_what_an_offline_build_writes(
    built_site: Path, regenerate_snapshots: bool
) -> None:
    expected = committed()
    actual = published(built_site)
    if regenerate_snapshots:
        for path in expected - actual:
            (SITE / path).unlink(missing_ok=True)
        for path in actual:
            (SITE / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(built_site / path, SITE / path)
        return

    problems = [f"no longer written: site/{path}" for path in sorted(expected - actual)]
    problems += [f"written and not committed: site/{path}" for path in sorted(actual - expected)]
    for path in sorted(expected & actual):
        theirs = (SITE / path).read_text() if (SITE / path).exists() else ""
        ours = (built_site / path).read_text()
        if theirs != ours:
            diff = difflib.unified_diff(
                theirs.splitlines(keepends=True),
                ours.splitlines(keepends=True),
                f"site/{path} (committed)",
                f"site/{path} (built)",
            )
            problems.append("".join(list(diff)[:60]))
    assert not problems, (
        "an offline build of the site differs from what is committed. Read the diff "
        "before accepting it, then rerun with --regenerate-snapshots.\n\n" + "\n".join(problems)
    )


# ---- properties that must hold for any published report -------------


def reports() -> list[str]:
    """Every report directory in the committed site, by its path under `site/`."""
    return sorted(p.parent.relative_to(SITE).as_posix() for p in SITE.glob("*/*/doc.json"))


@pytest.fixture(params=reports())
def report(request: pytest.FixtureRequest, built_site: Path) -> Path:
    return built_site / request.param


def without_warnings(html: str) -> str:
    """The report as a reader reads it: a warning quotes the line it is about.

    Laid out by `biome`, which breaks a tag before its closing `>`.
    """
    return re.sub(r'<div class="warnings"\s*>.*?</div\s*>', "", html, flags=re.DOTALL)


def test_ids_are_unique_and_every_link_resolves(report: Path) -> None:
    for name in ("report.html", "index.html"):
        html = (report / name).read_text()
        ids = re.findall(r'id="([^"]+)"', html)
        assert len(ids) == len(set(ids)), name
        refs = set(re.findall(r'id="fnref(\d+)"', html))
        notes = set(re.findall(r'id="fn(\d+)"', html))
        backlinks = set(re.findall(r'href="#fnref(\d+)"', html))
        assert refs == notes == backlinks, name
        for target in re.findall(r'href="#([^"]+)"', html):
            assert target in ids, f"{name}: #{target}"


def test_no_editorial_note_reaches_a_published_output(report: Path) -> None:
    """`Source:`, `Image Source`, and `SVG:` name assets for whoever assembles the page.

    Not `drive.google.com` in general, as `test_real_document.py` asks of its
    report: a caption can cite a file in Drive on purpose.
    """
    typst = (report / "report.typ").read_text()
    # Everything after the `#show: report.with(...)` call, which is the report itself.
    typst_body = re.split(r"^\)$", typst, maxsplit=1, flags=re.MULTILINE)[-1]
    html_body = without_warnings((report / "report.html").read_text())
    for emitted in (html_body, typst_body):
        for note in ("Source:", "Image Source", "SVG:"):
            assert note not in emitted, note


def test_no_chip_email_reaches_any_output(report: Path) -> None:
    """A person chip carries an email beside the name, and the address is not the report's."""
    emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", (report / "doc.json").read_text()))
    for name in ("index.html", "report.html", "report.md", "report.typ"):
        emitted = (report / name).read_text()
        for email in emails:
            assert email not in emitted, f"{name}: {email}"


def test_the_fragment_fits_in_one_code_block(report: Path) -> None:
    """Squarespace allows 400 KB, and the fragment is meant to be pasted whole."""
    assert (report / "report.html").stat().st_size < CODE_BLOCK_LIMIT


def test_every_figure_is_described(report: Path) -> None:
    """Every picture on the page carries alt text or a caption."""
    page = (report / "report.html").read_text()
    for figure in re.findall(r"<figure\b.*?</figure>", page, flags=re.DOTALL):
        described = re.search(r'alt="[^"]+"', figure) or "<figcaption" in figure
        assert described, figure[:200]


def test_the_records_are_json(report: Path) -> None:
    for name in ("doc.json", "images.json", "archives.json", "embeds.json"):
        if (report / name).exists():
            json.loads((report / name).read_text())
