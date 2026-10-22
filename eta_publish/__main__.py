"""`eta-publish`: Google Docs in, a publishable site out.

Four commands, because there are four things to do:

    eta-publish all             every publication in `publications.toml`, into `site/unpublished/`
    eta-publish one <doc>       one document, wherever you point it or by its listed name
    eta-publish add <url>       write that document's entry into the list
    eta-publish logo            write the logo charts carry from the logo as drawn

`all` and `one` write the logo first too, so an edited one is never left behind.

`all` is what the workflow runs and what the committed site is built from.
`one` is for a document before it is on the list, or one publication off it,
and takes a Docs URL, a bare id, a saved Docs response, or a name from the list.

Both build the same way and write the same index,
so the common case and the real case stay on the same code.
Each publication lands under the path its own front matter gives it.
"""

import glob
import os
import shutil
import signal
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from rich.text import Text
from typer import Argument, BadParameter, Exit, Option, Typer

from . import console, format, minify
from .build import (
    ANONYMOUS_WARNED,
    UNWARNED,
    BuildOptions,
    anonymous_warning,
    asset_base,
    check_code_block_size,
)
from .format import ROOT
from .logo import LOGO, write_logo
from .naming import ASSET_DIR, UNPUBLISHED_DIR
from .published import write_published
from .site import (
    PUBLICATIONS,
    Failed,
    Hosts,
    Publication,
    Site,
    add_publication,
    build_site,
    index_page,
    label,
    listed_publication,
    load_hosts,
    load_publications,
    saved_for,
    saved_responses,
)


class Suggestions(StrEnum):
    """How to resolve the document's open suggestions.

    An enum, so `--suggestions` cannot be handed a mode the API does not have.
    """

    REJECTED = "rejected"
    ACCEPTED = "accepted"


app = Typer(context_settings={"help_option_names": ["-h", "--help"]}, help=__doc__)

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
        help="carry the stylesheet and script in `report.html` rather than linking the site's,"
        " for a fragment to paste before the site is pushed"
    ),
]
HostedMedia = Annotated[
    bool,
    Option(help="link `report.html`'s images and videos where the site serves them"),
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
"""The options `all` and `one` share, spelled once,
so two commands that build the same way offer the same switches."""


@app.command(name="all")
def build_all(
    publications: Annotated[
        Path,
        Argument(metavar="LIST", help="a `.toml` list of publications"),
    ] = PUBLICATIONS,
    outdir: Outdir = Path("site"),
    suggestions: Suggested = Suggestions.REJECTED,
    split: Split = False,
    hosted_media: HostedMedia = True,
    embed_assets: EmbedAssets = False,
    source_brackets: SourceBrackets = False,
    images: Images = True,
    archive: Archive = True,
    comments: Comments = True,
    offline: Offline = False,
    into: Annotated[
        Path | None,
        Option(
            help="build here instead, reading the last build from OUTDIR and leaving it as it is"
        ),
    ] = None,
) -> None:
    """Build every publication in a list, into a site with an index.

    Both defaults name the committed thing,
    so `eta-publish all` with no arguments rebuilds the site as it ships.
    """
    try:
        listed = load_publications(publications)
        hosts = load_hosts(publications)
    except (OSError, ValueError) as e:
        # Typer's own wording for a bad argument, because that is what it is.
        raise BadParameter(str(e), param_hint="LIST") from e
    publish(
        listed,
        outdir,
        suggestions,
        split,
        images,
        comments,
        offline,
        archive,
        listed=listed,
        whole=True,
        into=into,
        hosted_media=hosted_media,
        embed_assets=embed_assets,
        source_brackets=source_brackets,
        hosts=hosts,
    )


@app.command(name="one")
def build_one_publication(
    doc: Annotated[
        str,
        Argument(
            metavar="DOC",
            help="a Google Doc URL (including its `?tab=` id), an id, saved Docs API JSON,"
            " or a publication's `name` in the list",
        ),
    ],
    publications: Annotated[
        Path,
        Option("-p", "--publications", help="the list a name is looked up in"),
    ] = PUBLICATIONS,
    outdir: Outdir = Path("site"),
    suggestions: Suggested = Suggestions.REJECTED,
    split: Split = False,
    hosted_media: HostedMedia = True,
    embed_assets: EmbedAssets = False,
    source_brackets: SourceBrackets = False,
    images: Images = True,
    archive: Archive = True,
    comments: Comments = True,
) -> None:
    """Build one document, before it is on the list or instead of it.

    Named by its entry, it is checked against that entry as `all` checks it.
    Otherwise the publication has no entry, so there is nothing saying what it should be called
    and nothing to hold it up against: what the document says, it publishes as.
    """
    try:
        publication = listed_publication(doc, publications)
        # The whole list, since what is hosted is every `automated` publication there is,
        # and one publication built is not the others taken off the host.
        listed = load_publications(publications) if publications.exists() else []
        hosts = load_hosts(publications)
    except (OSError, ValueError) as e:
        raise BadParameter(str(e), param_hint="DOC") from e
    publish(
        [publication],
        outdir,
        suggestions,
        split,
        images,
        comments,
        archive=archive,
        listed=listed,
        hosted_media=hosted_media,
        embed_assets=embed_assets,
        source_brackets=source_brackets,
        hosts=hosts,
    )


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

    Then `published/` is written from what was installed, for the `automated`
    publications in `listed`, the whole list whichever of it was built.
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
    publication_outcome(site)
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
    """
    outdir = root / UNPUBLISHED_DIR
    site = build_site(publications, outdir, options, read_from=read_from / UNPUBLISHED_DIR)

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(index_page(site))

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
        minify.page(
            outdir / built.path / "index.html", asset_base(built.path), linked=minify.PAGE_ASSETS
        )
        # `report.html`, its `--split` pieces, and the published copy of each.
        # Not a fragment carrying its stylesheet and script, which links no `.min` ones.
        if not options.embed_assets:
            for page in sorted((outdir / built.path).glob("report*.html")):
                if minify.is_min(page.name):
                    continue
                published = page.name.split(".")[1] == UNWARNED
                url = options.published_url if published else options.unpublished_url
                minify.page(page, f"{url}/{ASSET_DIR}")

    # The one to paste, and so the one whose size matters.
    for built in site.built:
        publication = outdir / built.path / "report.html"
        pasted = publication.with_name(minify.min_name(publication.name))
        if pasted.exists():
            check_code_block_size(built.doc, pasted)
        elif publication.exists():
            check_code_block_size(built.doc, publication)
    return site


def install(site: Site, built: Path, outdir: Path, whole: bool) -> None:
    """Put what was built in `built` where it is published, `outdir`.

    A whole site replaces the whole site, keeping only what the last build
    wrote for a publication that failed this time: a site missing a publication beats no
    site at all, and an older copy of it beats a missing one.
    Otherwise each publication built replaces its own directory and nothing else,
    along with the index and the shared assets every page links.

    Both are output directories, holding `UNPUBLISHED_DIR`.
    """
    if whole:
        for failed in site.failed:
            previous = saved_for(failed.publication, saved_responses(outdir / UNPUBLISHED_DIR))
            if previous is None:
                continue
            kept = built / previous.relative_to(outdir)
            if not kept.exists():
                shutil.copytree(previous, kept)
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
    for name in ("index.html", minify.min_name("index.html"), "robots.txt"):
        (built / name).replace(outdir / name)


def publication_outcome(site: Site) -> None:
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
    if ANONYMOUS_WARNED.is_set():
        # Last, so it is what is on screen when the build ends.
        log.line()
        console.write(anonymous_warning(), log)
    # Non-zero when anything failed, even though the rest of the site was written,
    # so an unattended run cannot fail quietly.
    if site.failed:
        raise Exit(code=1)


@app.command()
def add(
    url: Annotated[
        str,
        Argument(metavar="URL", help="a Google Doc URL, including the `?tab=` id to publish"),
    ],
    publications: Annotated[
        Path,
        Option("-p", "--publications", help="the list to append to"),
    ] = PUBLICATIONS,
) -> None:
    """Append a document to `publications.toml`, named as the document names itself.

    `name` and `tab` have to be right, and copying two titles out of Drive by hand
    is the step that gets them wrong, so they are read off the document rather than typed.
    """
    try:
        added = add_publication(url, publications)
    except (OSError, ValueError, LookupError, RuntimeError) as e:
        # `LookupError` and `RuntimeError` are `TabNotFound` and `FetchFailed`,
        # which only this command can raise: a fetch that fails inside
        # `build_site` is one publication's failure there.
        # `TabNotFound` carries the list of tabs to pick from, which is the
        # answer to a URL pasted without its `?tab=` id.
        raise BadParameter(str(e), param_hint="URL") from e
    # On stderr, like everything else these commands say.
    # What `add` produces is the line it wrote into `publications.toml`;
    # saying that it wrote it is commentary on having done so,
    # and stdout is left for something a caller would want to read.
    log = console.for_stream()
    console.write(console.added(publications, added.name or "", added.tab or "", log), log)


@app.command()
def logo() -> None:
    """Write `assets/logo.svg` from `assets/logo.src.svg`, minified by `svgo`.

    Every build does this first anyway; this is for an edit to the logo on its own.
    """
    log = console.for_stream()
    changed = write_logo()
    console.write(Text(f"{'wrote' if changed else 'unchanged:'} {LOGO.relative_to(ROOT)}"), log)


def main() -> None:
    # One `Ctrl+C` stops the run, says what it was doing, and cleans up after
    # it: see `console.stopped` for why that is a handler and not an `except`.
    signal.signal(signal.SIGINT, lambda _signal, _frame: console.stopped())
    try:
        app()
    except KeyboardInterrupt as interrupted:
        # Raised rather than signalled, by something that knew more about what
        # it was waiting on: the archive, asked from this thread.
        console.stopped(str(interrupted))


if __name__ == "__main__":
    main()
