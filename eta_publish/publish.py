"""Building a list of publications into a site, for every command that builds one.

`all` and `one` in `__main__`, and the `drafts` commands in `drafts`,
all build through `publish`, and offer the options it takes spelled the same way.
"""

import glob
import os
import shutil
import tempfile
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from typer import Exit, Option

from . import console, format, minify
from .build import (
    ANONYMOUS_WARNED,
    UNWARNED,
    BuildOptions,
    anonymous_warning,
    asset_base,
    check_code_block_size,
)
from .logo import write_logo
from .naming import ASSET_DIR, PARTIAL, UNPUBLISHED_DIR, partial_name
from .published import write_published
from .site import (
    Failed,
    Hosts,
    Publication,
    Site,
    build_site,
    index_page,
    label,
    publication_kind,
    saved_for,
    saved_responses,
)
from .staff import STAFF_JSON, look_up, read_staff, write_staff


class Suggestions(StrEnum):
    """How to resolve the document's open suggestions.

    An enum, so `--suggestions` cannot be handed a mode the API does not have.
    """

    REJECTED = "rejected"
    ACCEPTED = "accepted"


Outdir = Annotated[
    Path,
    Option("-o", "--outdir", help="where the site is written; `site/` is the committed one"),
]
Suggested = Annotated[
    Suggestions,
    Option("--suggestions", help="how to resolve open suggestions; rejected is what the doc says"),
]
Split = Annotated[
    bool,
    Option(help="write the HTML as numbered pieces cut at h2, for oversized publications"),
]
Images = Annotated[
    bool,
    Option(help="download the images; the output references them either way"),
]
Archive = Annotated[
    bool,
    Option(help="look up or ask for a capture of every source not already archived"),
]
Offline = Annotated[
    bool,
    Option(help="rebuild from the responses saved by the last build; no network"),
]
EmbedAssets = Annotated[
    bool,
    Option(
        help="carry the stylesheet and script in `report.partial.html`"
        " rather than linking the site's, for a fragment to paste before the site is pushed"
    ),
]
HostedMedia = Annotated[
    bool,
    Option(help="link `report.partial.html`'s images and videos where the site serves them"),
]
SourceBrackets = Annotated[
    bool,
    Option(
        help="show each cited link's bracketed number in the text;"
        " off, it is in the box hovering opens and in the Sources list"
    ),
]
Comments = Annotated[
    bool,
    Option(help="ask how many comment threads are open; the slowest thing a build does"),
]
"""The options the commands that build share, spelled once,
so commands that build the same way offer the same switches."""


def publish(
    publications: list[Publication],
    outdir: Path,
    suggestions: Suggestions,
    split: bool,
    images: bool,
    comments: bool,
    offline: bool = False,
    archive: bool = True,
    listed: list[Publication] | None = None,
    whole: bool = False,
    into: Path | None = None,
    hosted_media: bool = True,
    embed_assets: bool = False,
    source_brackets: bool = False,
    *,
    hosts: Hosts,
) -> Site:
    """Build these publications and write the index over them.

    One document and a whole list end here alike.
    A publish of one publication is a publish of a list with one entry,
    down to the index page, which is the page that says what failed.

    Built into a directory of its own beside `outdir`, reading what the last
    build left in `outdir`, and only then put in its place: nothing reads a file
    halfway through being rewritten, and nothing the build no longer writes,
    like an image taken out of a document, outlives it. `whole` is a build of
    the entire list, which replaces the entire site; otherwise only the publications
    built are replaced. `into` builds there and leaves `outdir` as it is.

    Every preview page says which kind of publication it is.

    Then `published/` is written from what was installed, for the `automated`
    publications in `listed`, the whole list whichever of it was built.

    Ends with the line saying how it went, and leaves the exit status to
    `publication_outcome`, so a list with a publication that failed
    does not stop the next being built.
    Two publications at one path do: the build is refused then and there, with `Exit`,
    since nothing says which of the two belongs at that path.
    """
    write_logo()
    options = BuildOptions(
        suggestions=str(suggestions),
        split=split,
        images=images,
        archive=archive,
        comments=comments,
        offline=offline,
        hosted_media=hosted_media,
        embed_assets=embed_assets,
        source_brackets=source_brackets,
        banners=True,
        unpublished_url=hosts.unpublished,
        published_url=hosts.published,
    )
    if into is not None:
        site = write_site(publications, into, options, read_from=outdir)
        host(site, into, listed or [], images, options.published_url)
    else:
        outdir.mkdir(parents=True, exist_ok=True)
        abandoned(outdir.parent, f".{outdir.name}-building-")
        staging = Path(
            tempfile.mkdtemp(dir=outdir.parent, prefix=f".{outdir.name}-building-{os.getpid()}-")
        )
        with console.cleaned_up(lambda: shutil.rmtree(staging, ignore_errors=True)):
            site = write_site(publications, staging, options, read_from=outdir)
            install(site, staging, outdir, whole)
        host(site, outdir, listed or [], images, options.published_url)
    summarize(site)
    return site


def host(site: Site, root: Path, listed: list[Publication], images: bool, site_url: str) -> None:
    """Write `root`'s `published/`, counting a live page left missing a file as a failure.

    A failure rather than a warning: the publication built,
    but a page already out is linking a picture nobody is serving.
    """
    log = console.for_stream()
    for publication, problem in write_published(root, listed, complete=images, site_url=site_url):
        log.line()
        console.write(console.failed(label(publication), problem), log)
        site.failed.append(Failed(publication=publication, error=problem))


def abandoned(parent: Path, prefix: str) -> None:
    """Remove what a build stopped partway left in `parent`, named `prefix<pid>-`.

    A stopped build removes its own directory, but its other threads can
    still be writing into it as it does, and so put some of it back before
    the process is gone. One whose process is no longer running is left over
    from that, and nothing else will ever remove it; one whose process is
    running is another build's, and is left alone.
    """
    for leftover in parent.glob(f"{glob.escape(prefix)}*"):
        pid = leftover.name.removeprefix(prefix).partition("-")[0]
        if not pid.isdigit() or _running(int(pid)):
            continue
        shutil.rmtree(leftover, ignore_errors=True)


def _running(pid: int) -> bool:
    """Whether a process `pid` exists, which is all a signal 0 asks."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_site(
    publications: list[Publication], root: Path, options: BuildOptions, read_from: Path
) -> Site:
    """Build the publications under `root`, reading what the last build left under `read_from`.

    Both are output directories, holding `UNPUBLISHED_DIR` and not the publications themselves.

    The staff page is read once here, for every publication, unless offline,
    and what it lists is saved for the next build: see `staff.STAFF_JSON`.
    """
    outdir = root / UNPUBLISHED_DIR
    staff = read_staff(read_from / UNPUBLISHED_DIR)
    if not options.offline:
        staff = look_up(staff)
    options = replace(options, staff=staff)
    site = build_site(publications, outdir, options, read_from=read_from / UNPUBLISHED_DIR)

    # Before anything is laid out or put in place: of two publications at one path,
    # whichever claimed the path second was refused before it wrote anything, and has said so,
    # but the first is still no more the one meant there than the second.
    # So the whole build, not the two publications.
    if site.clashed:
        raise Exit(code=1)

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(index_page(site))
    write_staff(outdir, staff)

    # Belt to the `noindex` the pages carry, and the weaker half of the pair:
    # a crawler reads `robots.txt` from the root of the host,
    # so under a project page like `<user>.github.io/eta-publish/` this file asks
    # nothing of anyone. It is here for whoever serves these pages from a root later,
    # and so that the intent is visible in the site rather than only in the
    # emitter. Remove it, and the `noindex`, when the publications go out.
    (outdir / "robots.txt").write_text("User-agent: *\nDisallow: /\n")

    # Once, over everything just written, rather than per file as it was
    # written: `biome` costs far more to start than to run.
    format.tree(outdir)

    # After the formatting, which `minify` starts from and `biome` would undo.
    minify.page(outdir / "index.html", "", linked=())
    if site.built:
        minify.assets(outdir / ASSET_DIR)
    for built in site.built:
        kind = publication_kind(built.doc)
        minify.page(
            outdir / built.path / f"{kind}.html", asset_base(built.path), linked=minify.PAGE_ASSETS
        )
        # `report.partial.html` or `statement.partial.html`, its `--split` pieces,
        # and the published copy of each.
        # Not a fragment carrying its stylesheet and script, which links no `.min` ones.
        if not options.embed_assets:
            for page in sorted((outdir / built.path).glob(f"{kind}*.{PARTIAL}.html")):
                published = page.name.split(".")[1] == UNWARNED
                url = options.published_url if published else options.unpublished_url
                minify.page(page, f"{url}/{ASSET_DIR}")

    for built in site.built:
        index_links(outdir / built.path, publication_kind(built.doc))

    # The one to paste, and so the one whose size matters.
    for built in site.built:
        publication = outdir / built.path / partial_name(publication_kind(built.doc))
        pasted = publication.with_name(minify.min_name(publication.name))
        if pasted.exists():
            check_code_block_size(built.doc, pasted)
        elif publication.exists():
            check_code_block_size(built.doc, publication)
    return site


def index_links(directory: Path, kind: str) -> None:
    """Link `index.html` in a publication's `directory` to its page, `report.html`,
    and `index.min.html` to `report.min.html`, if it has one.

    So the directory is a page at its own URL, `/reports/<slug>/`, as the site serves it,
    while the page is named for what it is beside `report.md` and `report.pdf`.
    A link rather than a copy, so the two cannot differ;
    relative, so it holds wherever the tree is moved.
    Both uploads follow it, GitHub Pages' artifact with `tar --dereference`
    and `wrangler pages deploy`, so each serves `index.html` as the page.

    After the formatting and the minifying, which would otherwise each read the page twice.
    """
    for name in ("index.html", minify.min_name("index.html")):
        target = name.replace("index", kind, 1)
        link = directory / name
        link.unlink(missing_ok=True)
        if (directory / target).is_file():
            link.symlink_to(target)


def install(site: Site, built: Path, outdir: Path, whole: bool) -> None:
    """Put what was built in `built` where it is published, `outdir`.

    A whole site replaces the whole site, keeping only what the last build
    wrote for a publication that failed this time: a site missing a publication beats no
    site at all, and an older copy of it beats a missing one.
    Otherwise each publication built replaces its own directory and nothing else,
    along with the index, the shared assets every page links, and `STAFF_JSON`.

    Both are output directories, holding `UNPUBLISHED_DIR`.
    """
    if whole:
        for failed in site.failed:
            previous = saved_for(failed.publication, saved_responses(outdir / UNPUBLISHED_DIR))
            if previous is None:
                continue
            kept = built / previous.relative_to(outdir)
            if not kept.exists():
                # `index.html` stays a link to `report.html`, rather than a second copy of it.
                shutil.copytree(previous, kept, symlinks=True)
        old = outdir.with_name(f"{built.name}-old")
        outdir.rename(old)
        built.rename(outdir)
        shutil.rmtree(old)
        return
    built = built / UNPUBLISHED_DIR
    outdir = outdir / UNPUBLISHED_DIR
    outdir.mkdir(exist_ok=True)
    for entry in site.built:
        shutil.rmtree(outdir / entry.path, ignore_errors=True)
        (outdir / entry.path).parent.mkdir(parents=True, exist_ok=True)
        (built / entry.path).rename(outdir / entry.path)
    for shared in (ASSET_DIR,):
        shutil.rmtree(outdir / shared, ignore_errors=True)
        (built / shared).rename(outdir / shared)
    for name in ("index.html", minify.min_name("index.html"), "robots.txt", STAFF_JSON):
        (built / name).replace(outdir / name)


def summarize(site: Site) -> None:
    """One line saying how the build went.

    Where each publication went is on that publication's own heading, said as it was
    built rather than listed again once they all were.
    Each failure has already been said, with the reason, as it happened:
    repeating the names here without their reasons would only be the same
    list read a second time, so this counts them instead.
    """
    log = console.for_stream()
    if site.built or site.failed:
        # Off the last publication's warnings, since it is about all of them.
        log.line()
    console.write(
        console.summary(
            len(site.built),
            len(site.failed),
            sum(len(built.doc.warnings) for built in site.built),
        ),
        log,
    )


def publication_outcome(*sites: Site) -> None:
    """What is said once every site is built, and the exit status they add up to."""
    if ANONYMOUS_WARNED.is_set():
        # Last, so it is what is on screen when the build ends.
        log = console.for_stream()
        log.line()
        console.write(anonymous_warning(), log)
    # Non-zero when anything failed, even though the rest of the site was written,
    # so an unattended run cannot fail quietly.
    if any(site.failed for site in sites):
        raise Exit(code=1)
