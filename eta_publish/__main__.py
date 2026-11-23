"""`eta-publish`: Google Docs in, a publishable site out.

Seven commands, because there are seven things to do:

    eta-publish all             every publication in `publications.toml`, into `site/unpublished/`,
                                and in `drafts/publications.toml`, into `drafts/site/unpublished/`
    eta-publish one <doc>       one document, wherever you point it or by its listed name
    eta-publish add <url>       write that document's entry into the list
    eta-publish logo            write the logo charts carry from the logo as drawn
    eta-publish drafts site     build the drafts site, every publication labeled with its kind
    eta-publish drafts preview  build the drafts site, and upload it as this branch's preview
    eta-publish drafts deploy   the same from CI, for any branch, `main` included

`all` and `one` write the logo first too, so an edited one is never left behind.

`all` is what the workflow runs and what the committed site is built from.
`one` is for a document before it is on the list, or one publication off it,
and takes a Docs URL, a bare id, a saved Docs response, or a name from the list.

Both build the same way and write the same index,
so the common case and the real case stay on the same code.
Each publication lands under the path its own front matter gives it.
"""

import os
import shutil
import signal
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

from rich.text import Text
from typer import Argument, BadParameter, Exit, Option, Typer

from . import console, drafts_site, preview
from .format import ROOT
from .logo import LOGO, write_logo
from .publish import (
    Archive,
    Comments,
    EmbedAssets,
    HostedMedia,
    Images,
    Offline,
    Outdir,
    SourceBrackets,
    Split,
    Suggested,
    Suggestions,
    abandoned,
    publication_outcome,
    publish,
)
from .site import (
    DRAFTS,
    PUBLICATIONS,
    SITE,
    Hosts,
    Publication,
    Site,
    add_publication,
    clashes,
    listed_publication,
    load_hosts,
    load_publications,
)

app = Typer(context_settings={"help_option_names": ["-h", "--help"]}, help=__doc__)


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


@drafts.command(name="deploy")
def deploy_drafts(
    branch: Annotated[
        str,
        Option(
            help="the `eta-drafts` branch being deployed: `main` is the drafts site itself,"
            " and any other its preview at `<branch>.eta-drafts.pages.dev`"
        ),
    ],
    suggestions: Suggested = Suggestions.REJECTED,
    archive: Archive = True,
    comments: Comments = True,
) -> None:
    """Build the drafts site and upload it for `--branch`: what `eta-drafts`'s workflow runs.

    As `drafts preview` does, for any branch, `main` included,
    with the Cloudflare token in `$CLOUDFLARE_API_TOKEN`.
    Only in GitHub Actions, where what is built is what is committed:
    from a working copy, a deploy is `drafts preview`.
    """
    what = "drafts deploy"
    try:
        token = preview.ci_token()
    except preview.Refused as e:
        refuse(str(e), what)
    deploy(branch, token, suggestions, archive, comments, what=what)


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
