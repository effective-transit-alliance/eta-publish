"""`eta-publish drafts`: the drafts in `drafts/`, a clone of the private `eta-drafts`.

    eta-publish drafts site     build the drafts site, every publication labeled with its kind
    eta-publish drafts preview  build the drafts site, and upload it as a preview of this commit
    eta-publish drafts deploy   the same from CI, for any branch, `main` included

See `docs/drafts.md`.
"""

import os
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

from rich.text import Text
from typer import Argument, Exit, Option, Typer

from . import console, drafts_site

# As `pages`, since `preview` is the command: what it holds is the upload to Cloudflare Pages.
from . import preview as pages
from .publish import (
    Archive,
    Comments,
    Images,
    Offline,
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
    clashes,
    load_hosts,
    load_publications,
)

drafts = Typer(
    help="The drafts in `drafts/`, a clone of the private `eta-drafts`; see `docs/drafts.md`.",
    no_args_is_help=True,
)


Branch = Annotated[
    str,
    Option(
        help="the branch the drafts site is built for: `main` is the site itself,"
        " and any other its preview at `<branch>.eta-drafts.pages.dev`"
    ),
]


@drafts.command(no_args_is_help=True)
def site(
    directory: Annotated[
        Path,
        Argument(metavar="DIR", help="where to write it; a new directory, or an empty one"),
    ],
    branch: Branch = pages.PRODUCTION_BRANCH,
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
    except (OSError, ValueError, pages.Refused) as e:
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
    except pages.Refused as e:
        refuse(str(e), what)
    return sites


@drafts.command()
def preview(
    suggestions: Suggested = Suggestions.REJECTED,
    archive: Archive = True,
    comments: Comments = True,
) -> None:
    """Build the drafts site from the working copy, and upload it as a preview of this commit.

    Every publication, the drafts in `drafts/publications.toml` and the ones in `publications.toml`,
    each labeled with its kind, built and laid out as `drafts site` builds them:
    with the code as it is, uncommitted edits included, and from the live documents,
    since the images cannot be rebuilt from anything saved.
    Then uploaded to `<branch>-<commit>.eta-drafts.pages.dev`,
    or `<branch>-<commit>-dirty` with uncommitted edits, behind the drafts site's sign-in,
    with nothing committed or pushed.
    Not to `<branch>.eta-drafts.pages.dev`, which is CI's preview of the branch, on every push.
    Built in a directory of its own, so `site/` and `drafts/site/` are left as they are.

    The preview's pages and fragments link their assets at the preview's own host,
    `<branch>-<commit>.eta-drafts.pages.dev`, so the preview shows its own assets
    and not production's, or the public site's.

    Refused on `main`, whose deploy is the drafts site itself, made from CI.
    Nothing is uploaded when a publication fails to build.
    """
    # Everything that can refuse, before minutes spent building.
    try:
        branch = pages.local_name()
        token = pages.token()
    except pages.Refused as e:
        refuse(str(e))
    build_and_upload(branch, token, suggestions, archive, comments, what="drafts preview")


@drafts.command()
def deploy(
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
        token = pages.ci_token()
    except pages.Refused as e:
        refuse(str(e), what)
    build_and_upload(branch, token, suggestions, archive, comments, what=what)


def build_and_upload(
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
            pages.upload(work / SITE, branch, token)
        except RuntimeError as e:
            refuse(str(e), what)


def refuse(reason: str, what: str = "drafts preview") -> NoReturn:
    """Say why `what` is not done, as a failed build says why, and exit non-zero."""
    log = console.for_stream()
    console.write(console.failed(what, reason), log)
    raise Exit(code=1)
