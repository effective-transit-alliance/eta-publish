"""`site/published/`: what the live Squarespace pages need hosted, and nothing else.

A report published from its `report.html` is that fragment pasted into one code block,
and the fragment links its pictures, its videos, its PDF, and the shared stylesheet and script
at the site's URL, since Squarespace has no way to be handed a directory of them.
Those files have to be served for as long as the page is up,
so they are what this directory holds, beside the fragment itself and `report.md`.

Nothing a page built by hand needs, since it references nothing of ours,
and nothing of a draft, which is not out.
Each file sits at the same path as in `site/unpublished/`,
so a URL the fragment names is served by either one.

Written from what is already under `site/unpublished/` rather than from this build alone:
a report that failed to build this time keeps its last copy there,
and its live page still links every file of that copy.
"""

import html as markup
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from .build import UNWARNED, link_or_copy
from .minify import MIN_ASSETS, min_name
from .naming import ASSET_DIR, PUBLISHED_DIR, SITE, UNPUBLISHED_DIR
from .site import Published, Report, saved_for, saved_responses

PUBLISHED_FILES = ("report.html", "report.md")
"""What every published report carries whatever it links."""

SPLIT_FILES = "report.part*.html"
"""The pieces a `--split` build writes beside `report.html`, for a page pasted in several."""

_ATTRIBUTE = re.compile(r'\s(src|href|poster|srcset)="([^"]*)"')

_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)
"""A URL with a scheme, a host, or only a fragment: nothing that is a file here."""

_OUTPUTS = frozenset({".html", ".md", ".pdf"})
"""What a report writes of its own, once for its preview and once to publish."""

_COPIED = frozenset({".html", ".md", ".css", ".js"})
"""What is copied rather than linked.

A build writes text in place, so a second name for one of these
would change along with the file it was linked from."""


def referenced(html: str, path: str, site_url: str = SITE) -> set[str]:
    """Every file `html` links that the site serves, relative to the site.

    `path` is where the report is, which a relative link is relative to:
    a fragment built with `--no-hosted-media` links its pictures beside itself.
    A `srcset` is a list, each entry a URL and the width it is.

    A link that resolves outside the site is refused,
    since nothing outside it is anything this could serve.
    """
    found: set[str] = set()
    for name, value in _ATTRIBUTE.findall(html):
        # Only a `srcset` is a list: anywhere else a comma is part of the URL,
        # as it is all through a link to a passage, `#:~:text=160,000`.
        candidates = value.split(",") if name == "srcset" else [value]
        for candidate in candidates:
            candidate = markup.unescape(candidate).strip()
            url = candidate.split(" ")[0].partition("#")[0].partition("?")[0]
            if not url:
                continue
            if url.startswith(f"{site_url}/"):
                url = url.removeprefix(f"{site_url}/")
            elif _EXTERNAL.match(url):
                continue
            else:
                url = f"{path}/{url}"
            parts: list[str] = []
            # A link names the file percent-encoded, and the disk does not.
            for part in PurePosixPath(unquote(url)).parts:
                if part == "..":
                    if not parts:
                        raise ValueError(f"`{candidate}` links outside the site")
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            found.add("/".join(parts))
    return found


def published_copy(path: Path) -> Path:
    """The copy of a report's output `path` written for `site/published/`.

    A published report writes each of its outputs twice, and this is the second:
    linking the published host rather than the preview's, and without the warnings.
    Anything else the page links, a picture or the stylesheet, is the same file for both.
    """
    stem, dot, rest = path.name.partition(".")
    # Not `assets/report.css`, which is shared and written once.
    if stem != "report" or path.suffix not in _OUTPUTS:
        return path
    return path.with_name(f"{stem}.{UNWARNED}{dot}{rest}")


def write_published(
    root: Path, reports: list[Report], complete: bool, site_url: str = SITE
) -> list[tuple[Report, str]]:
    """Write `root`'s `published/` from its `unpublished/`, for every `automated` report.

    Replaced whole each time, so a report no longer `automated` is no longer hosted.

    `complete` is a build that has every picture on disk to copy,
    so a file the fragment links and that is not there is a broken live page:
    those come back as each report's problem.
    A build without the pictures has none of them to copy and says nothing of it,
    and since none of them are committed, it writes the same committed files.
    """
    unpublished = root / UNPUBLISHED_DIR
    saved = saved_responses(unpublished)
    staging = root / f".{PUBLISHED_DIR}-building"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    problems: list[tuple[Report, str]] = []
    for report in reports:
        if report.published is not Published.AUTOMATED:
            continue
        directory = saved_for(report, saved)
        if directory is None:
            # Not built here, which is a build of one document somewhere else;
            # a whole build has already said which of its reports failed.
            continue
        path = directory.relative_to(unpublished).as_posix()
        pages = [directory / "report.html", *sorted(directory.glob(SPLIT_FILES))]
        pages = [page for page in pages if UNWARNED not in page.name]
        files = {f"{path}/{name}" for name in PUBLISHED_FILES}
        for page in pages:
            files.add(f"{path}/{page.name}")
            if published_copy(page).is_file():
                files |= referenced(published_copy(page).read_text(), path, site_url)
        # Named rather than read off the page: it links what `report.html` does,
        # but the `.min` assets for the others, and a map is linked from its file, not the page.
        if published_copy(directory / min_name("report.html")).is_file():
            files.add(f"{path}/{min_name('report.html')}")
            files |= {f"{ASSET_DIR}/{f}" for name in MIN_ASSETS for f in (name, f"{name}.map")}
        missing = []
        for name in sorted(files):
            source = published_copy(unpublished / name)
            if not source.is_file():
                missing.append(name)
                continue
            dest = staging / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix in _COPIED:
                shutil.copyfile(source, dest)
            else:
                link_or_copy(source, dest)
        if complete and missing:
            listed = ", ".join(f"`{name}`" for name in missing)
            problems.append((report, f"its `report.html` links files it does not have: {listed}"))
    published = root / PUBLISHED_DIR
    shutil.rmtree(published, ignore_errors=True)
    staging.rename(published)
    return problems
