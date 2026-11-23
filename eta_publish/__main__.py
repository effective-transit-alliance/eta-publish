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

import signal
from pathlib import Path
from typing import Annotated

from rich.text import Text
from typer import Argument, BadParameter, Option, Typer

from . import console
from .drafts import drafts
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
    publication_outcome,
    publish,
)
from .site import (
    DRAFTS,
    PUBLICATIONS,
    SITE,
    add_publication,
    listed_publication,
    load_hosts,
    load_publications,
)

app = Typer(context_settings={"help_option_names": ["-h", "--help"]}, help=__doc__)
app.add_typer(drafts, name="drafts")


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
