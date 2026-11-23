"""`eta-publish drafts`: the drafts in `drafts/`, a clone of the private `eta-drafts`.

    eta-publish drafts preview  build the drafts, and upload them as this branch's preview

See `docs/drafts-plan.md`.
"""

from typing import NoReturn

from typer import Exit, Typer

from . import console

# As `pages`, since `preview` is the command: what it holds is the upload to Cloudflare Pages.
from . import preview as pages
from .publish import (
    Archive,
    Comments,
    Suggested,
    Suggestions,
    publication_outcome,
    publish,
)
from .site import (
    DRAFTS,
    PUBLICATIONS,
    SITE,
    load_hosts,
    load_publications,
)

drafts = Typer(
    help="The drafts in `drafts/`, a clone of the private `eta-drafts`; see `docs/drafts-plan.md`."
)


@drafts.command()
def preview(
    suggestions: Suggested = Suggestions.REJECTED,
    archive: Archive = True,
    comments: Comments = True,
) -> None:
    """Build the drafts from the working copy, and upload them as this branch's preview.

    Built as `all` builds them, from `drafts/publications.toml` into `drafts/site/`,
    with the code as it is, uncommitted edits included, and from the live documents,
    since the images cannot be rebuilt from anything saved.
    Then uploaded to `<branch>.eta-drafts.pages.dev`, behind the drafts site's sign-in,
    with nothing committed or pushed.

    The preview's pages and fragments link their assets at the preview's own host,
    `<branch>.eta-drafts.pages.dev`, wherever the list's `[site]` says `eta-drafts.pages.dev`,
    so the preview shows its own branch's assets and not production's.

    Refused on `main`, whose deploy is the drafts site itself.
    Nothing is uploaded when a draft fails to build.
    """
    path = DRAFTS / PUBLICATIONS
    # Everything that can refuse, before minutes spent building.
    try:
        branch = pages.branch()
        token = pages.token()
    except pages.Refused as e:
        refuse(str(e))
    try:
        listed = load_publications(path)
        hosts = pages.previewed(load_hosts(path), branch)
    except (OSError, ValueError, pages.Refused) as e:
        refuse(str(e))
    site = publish(
        listed,
        DRAFTS / SITE,
        suggestions,
        split=False,
        images=True,
        comments=comments,
        archive=archive,
        listed=listed,
        whole=True,
        hosts=hosts,
    )
    publication_outcome(site)
    log = console.for_stream()
    log.line()
    with pages.staged(DRAFTS / SITE) as staged:
        try:
            pages.upload(staged, branch, token)
        except RuntimeError as e:
            refuse(str(e))


def refuse(reason: str) -> NoReturn:
    """Say why the preview is not uploaded, as a failed build says why, and exit non-zero."""
    log = console.for_stream()
    console.write(console.failed("drafts preview", reason), log)
    raise Exit(code=1)
