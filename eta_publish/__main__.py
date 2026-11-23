"""`eta-publish`: Google Docs in, a publishable site out.

Six commands, because there are six things to do:

    eta-publish all             every publication in `publications.toml`, into `site/unpublished/`,
                                and in `drafts/publications.toml`, into `drafts/site/unpublished/`
    eta-publish one <doc>       one document, wherever you point it or by its listed name
    eta-publish add <url>       write that document's entry into the list
    eta-publish logo            write the logo charts carry from the logo as drawn
    eta-publish drafts site     build the drafts site, every publication labeled with its kind
    eta-publish drafts preview  build the drafts site, and upload it as this branch's preview

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
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

from rich.text import Text
from typer import Argument, BadParameter, Exit, Option, Typer

from . import console, drafts_site, format, minify, preview
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
    DRAFTS,
    PUBLICATIONS,
    SITE,
    Failed,
    Hosts,
    Publication,
    Site,
    add_publication,
    build_site,
    clashes,
    index_page,
    label,
    listed_publication,
    load_hosts,
    load_publications,
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
    outdir: Outdir = SITE,
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
    so `eta-publish all` with no arguments rebuilds the site as it ships,
    and the drafts' site too, from a clone of `eta-drafts` in `drafts/`.
    Without a `drafts/`, as in CI, only the site; a `drafts/` without its list is an error.
    """
    lists = [(publications, outdir)]
    if into is None and committed(publications, outdir) and DRAFTS.is_dir():
        lists.append((DRAFTS / PUBLICATIONS, DRAFTS / SITE))
    # Every list read before anything is built,
    # so a mistake in the second is not found after minutes spent on the first.
    loaded = []
    for path, _ in lists:
        if path == DRAFTS / PUBLICATIONS and not path.exists():
            raise BadParameter(
                f"`{DRAFTS}/` is there but `{path}` is not: "
                "the drafts are built from it, so a clone of `eta-drafts` without it is broken",
                param_hint="LIST",
            )
        try:
            loaded.append((load_publications(path), load_hosts(path)))
        except (OSError, ValueError) as e:
            # Typer's own wording for a bad argument, because that is what it is.
            raise BadParameter(str(e), param_hint="LIST") from e
    log = console.for_stream()
    sites = []
    for (path, site_dir), (listed, hosts) in zip(lists, loaded, strict=True):
        if len(lists) > 1:
            # Each list's publications and summary under its name,
            # since both summaries would otherwise read the same.
            log.line()
            console.write(Text(str(path), style="bold"), log)
        sites.append(
            publish(
                listed,
                site_dir,
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
        )
    publication_outcome(*sites)


def committed(publications: Path, outdir: Path) -> bool:
    """Whether this is the committed list built into the committed site.

    Only then are the drafts built as well:
    a different list or a different site is a build of that, and of nothing else.
    By where they are, so `-o site` is the same build as leaving it out.
    """
    return publications.resolve() == PUBLICATIONS.resolve() and outdir.resolve() == SITE.resolve()


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
    outdir: Outdir = SITE,
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
    site = publish(
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
    publication_outcome(site)


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
        minify.page(
            outdir / built.path / "index.html", asset_base(built.path), linked=minify.PAGE_ASSETS
        )
        # `report.html` or `statement.html`, its `--split` pieces, and the published copy of each.
        # Not a fragment carrying its stylesheet and script, which links no `.min` ones.
        if not options.embed_assets:
            for page in sorted((outdir / built.path).glob(f"{publication_kind(built.doc)}*.html")):
                if minify.is_min(page.name):
                    continue
                published = page.name.split(".")[1] == UNWARNED
                url = options.published_url if published else options.unpublished_url
                minify.page(page, f"{url}/{ASSET_DIR}")

    # The one to paste, and so the one whose size matters.
    for built in site.built:
        publication = outdir / built.path / f"{publication_kind(built.doc)}.html"
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


drafts = Typer(
    help="The drafts in `drafts/`, a clone of the private `eta-drafts`; see `docs/drafts-plan.md`."
)
app.add_typer(drafts, name="drafts")


Branch = Annotated[
    str,
    Option(
        help="the branch the drafts site is built for: `main` is the site itself,"
        " and any other its preview at `<branch>.eta-drafts.pages.dev`"
    ),
]


@drafts.command(name="site")
def drafts_site_command(
    directory: Annotated[
        Path,
        Argument(metavar="DIR", help="where to write it; a new directory, or an empty one"),
    ],
    branch: Branch = preview.PRODUCTION_BRANCH,
    suggestions: Suggested = Suggestions.REJECTED,
    images: Images = True,
    archive: Archive = True,
    comments: Comments = True,
    offline: Offline = False,
) -> None:
    """Build the drafts site, every publication with its kind on it, into DIR, uploading nothing.

    To look at before uploading it,
    or to build without the network from what the last builds saved.
    """
    what = "drafts site"
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        refuse(f"`{directory}` is there and not an empty directory, so nothing is written", what)
    with drafts_workspace(what) as work:
        sites = build_drafts_site(
            work, branch, suggestions, images, archive, comments, offline, what=what
        )
        if directory.exists():
            directory.rmdir()
        shutil.move(work / SITE, directory)
    publication_outcome(*sites)


DRAFTS_WORK = ".site-deploy-"
"""What a build of the drafts site names the directory it works in, in `drafts/`,
followed by its process id: see `abandoned`."""


@contextmanager
def drafts_workspace(what: str) -> Generator[Path]:
    """A directory in `drafts/` to build the drafts site in, removed once it is done with.

    In `drafts/`, beside `drafts/site/`, so its parts can be links to one another
    and none of it is in `/tmp`.
    In a clone of `eta-drafts`, so `git status` there shows it while it is there.
    """
    if not DRAFTS.is_dir():
        refuse(f"no `{DRAFTS}/`, the clone of `eta-drafts` the drafts are built from", what)
    prefix = f"{DRAFTS_WORK}{os.getpid()}-"
    abandoned(DRAFTS, DRAFTS_WORK)
    work = Path(tempfile.mkdtemp(dir=DRAFTS, prefix=prefix))
    with console.cleaned_up(lambda: shutil.rmtree(work, ignore_errors=True)):
        yield work


def build_drafts_site(
    work: Path,
    branch: str,
    suggestions: Suggestions,
    images: bool,
    archive: bool,
    comments: bool,
    offline: bool,
    *,
    what: str,
) -> list[Site]:
    """Build the drafts site for `branch` into `work`, as `work/site/`, laid out to upload.

    `publications.toml` and `drafts/publications.toml`, each built as `all` builds it,
    reading what its last build saved in `site/` or `drafts/site/` and leaving that as it is,
    with its links at the drafts site and a label on each page saying which kind it is,
    each in a directory of its own in `work`, then laid out as one tree by `drafts_site`.

    Refused, with nothing laid out, when two publications are at one path:
    checked once both lists are built, since only a document's build fetches it,
    and its path is the document's own `URL:` line.
    """
    lists = [
        (PUBLICATIONS, SITE, "eta-publish"),
        (DRAFTS / PUBLICATIONS, DRAFTS / SITE, DRAFTS.name),
    ]
    # Every list read before anything is built, as `all` reads them.
    loaded: list[tuple[list[Publication], Hosts]] = []
    try:
        public = load_publications(PUBLICATIONS)
        loaded.append((public, drafts_site.hosts(branch)))
        listed = load_publications(DRAFTS / PUBLICATIONS)
        loaded.append((listed, drafts_site.drafts_hosts(load_hosts(DRAFTS / PUBLICATIONS), branch)))
    except (OSError, ValueError, preview.Refused) as e:
        refuse(str(e), what)
    log = console.for_stream()
    trees = []
    for (path, outdir, name), (publications, hosts) in zip(lists, loaded, strict=True):
        log.line()
        console.write(Text(str(path), style="bold"), log)
        site = publish(
            publications,
            outdir,
            suggestions,
            split=False,
            images=images,
            comments=comments,
            offline=offline,
            archive=archive,
            listed=publications,
            into=work / name,
            hosts=hosts,
        )
        trees.append(drafts_site.Tree(listed=path, built=work / name, site=site))
    sites = [tree.site for tree in trees]
    found = clashes((tree.listed, tree.site.built) for tree in trees)
    if found:
        refuse("two publications at one path: " + "; ".join(found), what)
    try:
        drafts_site.assemble(trees, work / SITE, drafts_site.index_page(sites))
    except preview.Refused as e:
        refuse(str(e), what)
    return sites


@drafts.command(name="preview")
def preview_drafts(
    suggestions: Suggested = Suggestions.REJECTED,
    archive: Archive = True,
    comments: Comments = True,
) -> None:
    """Build the drafts site from the working copy, and upload it as this branch's preview.

    Every publication, the drafts in `drafts/publications.toml` and the ones in `publications.toml`,
    each labeled with its kind, built and laid out as `drafts site` builds them:
    with the code as it is, uncommitted edits included, and from the live documents,
    since the images cannot be rebuilt from anything saved.
    Then uploaded to `<branch>.eta-drafts.pages.dev`, behind the drafts site's sign-in,
    with nothing committed or pushed.
    Built in a directory of its own, so `site/` and `drafts/site/` are left as they are.

    The preview's pages and fragments link their assets at the preview's own host,
    `<branch>.eta-drafts.pages.dev`, so the preview shows its own branch's assets
    and not production's, or the public site's.

    Refused on `main`, whose deploy is the drafts site itself, made from CI.
    Nothing is uploaded when a publication fails to build.
    """
    # Everything that can refuse, before minutes spent building.
    try:
        branch = preview.branch()
        token = preview.token()
    except preview.Refused as e:
        refuse(str(e))
    deploy(branch, token, suggestions, archive, comments, what="drafts preview")


def deploy(
    branch: str,
    token: str,
    suggestions: Suggestions,
    archive: bool,
    comments: bool,
    *,
    what: str,
) -> None:
    """Build the drafts site for `branch`, and upload it there with `token`, if all of it built."""
    with drafts_workspace(what) as work:
        sites = build_drafts_site(
            work, branch, suggestions, True, archive, comments, offline=False, what=what
        )
        publication_outcome(*sites)
        log = console.for_stream()
        log.line()
        try:
            preview.upload(work / SITE, branch, token)
        except RuntimeError as e:
            refuse(str(e), what)


def refuse(reason: str, what: str = "drafts preview") -> NoReturn:
    """Say why `what` is not done, as a failed build says why, and exit non-zero."""
    log = console.for_stream()
    console.write(console.failed(what, reason), log)
    raise Exit(code=1)


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
