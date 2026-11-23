"""The drafts site, `eta-drafts.pages.dev`: every publication there is, each labeled with its kind.

`docs/drafts-plan.md` says what it is for: one place to see what a change to this code
does to every publication, the drafts in `eta-drafts` and this repository's own alike.
So it shows all three kinds of publication, built by the same code,
and every publication's page says which kind it is (see `site.KINDS`).

One deployment, laid out as the Pages workflow lays out the public site:

    /            every list's `site/unpublished/`, side by side
    /published/  every list's `site/published/`
    /index.html  every publication, in a group for each kind

which is where the drafts' list's `[site]` says the drafts are served,
and where this repository's are built to be served for the drafts site.
One tree, with each publication at its own path, as it is on the live site:
a draft never rewrites a published report, since a path, once published, stays live.
So two publications at one path, in one list or across both, are refused by `site.clashes`,
as `assemble` refuses two different files at one path.

Without `doc.json`, as the Pages workflow deploys the public site:
it carries the email address behind every person chip, and nothing served reads it.
"""

import filecmp
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import htpy
from markupsafe import Markup

from .assets import read
from .build import DOC_JSON
from .emit.html import BANNER_CSS, Piece, kind_class, lines, markup, tag
from .minify import min_name
from .naming import ASSET_DIR, PUBLISHED_DIR, UNPUBLISHED_DIR
from .preview import PRODUCTION_BRANCH, PRODUCTION_URL, Refused, previewed
from .site import INDEX_CSS, KINDS, Hosts, Site, index_entry, label, newest_first

DRAFTS_INDEX_CSS = read("drafts-index.css")
"""What the drafts site's index adds to `INDEX_CSS` and `BANNER_CSS`: its headings for each kind."""

DRAFTS_HOSTS = Hosts(published=f"{PRODUCTION_URL}/{PUBLISHED_DIR}", unpublished=PRODUCTION_URL)
"""Where the production drafts site serves every list's publications,
and so what the drafts' list's `[site]` has to say."""

REPLACED = frozenset({"index.html", min_name("index.html")})
"""What each list's `site/unpublished/` has at its top that the drafts site does not serve:
its own index, which lists that list alone, in favor of `index_page`,
and the index's `.min` copy, which nothing links."""


@dataclass(frozen=True)
class Tree:
    """One list's build, as `assemble` takes it."""

    listed: Path
    """The list it was built from, as each refusal names it."""

    built: Path
    """The output directory it was built in, holding `UNPUBLISHED_DIR` and maybe `PUBLISHED_DIR`."""

    site: Site


def hosts(branch: str) -> Hosts:
    """Where the drafts site serves every list's publications for `branch`:
    `DRAFTS_HOSTS` for the production branch,
    and the same paths on the branch's preview for any other.

    For this repository's list too, not its own `[site]`, which is the public site:
    linked there, the pages would show the assets `main` published,
    and not those of the code being looked at.
    """
    if branch == PRODUCTION_BRANCH:
        return DRAFTS_HOSTS
    return previewed(DRAFTS_HOSTS, branch)


def drafts_hosts(listed: Hosts, branch: str) -> Hosts:
    """The drafts' hosts for `branch`, refusing a list whose `[site]` is not `DRAFTS_HOSTS`.

    Anywhere else and the drafts' absolute links would name files the deployment does not have.
    """
    if listed != DRAFTS_HOSTS:
        raise Refused(
            f"the drafts list's `[site]` is `published = {listed.published!r}`, "
            f"`unpublished = {listed.unpublished!r}`, and the drafts site serves the drafts at "
            f"`published = {DRAFTS_HOSTS.published!r}`, "
            f"`unpublished = {DRAFTS_HOSTS.unpublished!r}`"
        )
    return hosts(branch)


def index_page(sites: list[Site]) -> str:
    """The drafts site's front page: every publication of `sites`, in a group for each kind.

    Grouped by the kind each entry says it is, whichever list it is in,
    with what did not build in its group, as the public site's index has them.
    """
    sections: list[Piece] = []
    for kind, (name, says) in KINDS.items():
        built = [b for site in sites for b in site.built if b.publication.published is kind]
        failed = [f for site in sites for f in site.failed if f.publication.published is kind]
        entries = [index_entry(b) for b in sorted(built, key=newest_first)]
        sections += [
            tag.h2(class_=f"kind-heading {kind_class(name)}")[name],
            tag.p(class_="kind-says")[says],
            tag.ul["\n", lines(entries), "\n"] if entries else tag.p(class_="meta")["None yet."],
            *(tag.p(class_="failed")[f"{label(f.publication)}: {f.error}"] for f in failed),
        ]
    page: list[Piece] = [
        htpy.meta(charset="utf-8"),
        htpy.meta(name="viewport", content="width=device-width, initial-scale=1"),
        # As every page of the site has it: none of this is for a search engine,
        # and the sign-in in front of it is not something a crawler is meant to rely on.
        htpy.meta(name="robots", content="noindex, nofollow"),
        tag.title["ETA drafts"],
        htpy.link(rel="icon", type="image/svg+xml", href=f"{ASSET_DIR}/logo.svg"),
        tag.style[Markup(f"\n{INDEX_CSS}\n{BANNER_CSS}\n{DRAFTS_INDEX_CSS}")],
        tag.h1["ETA drafts"],
        tag.p[
            "Every ETA publication, the drafts included, built from the Google Docs "
            "by the same code, warnings included. Not the published pages."
        ],
        *sections,
    ]
    return markup([Markup("<!doctype html>"), "\n", lines(page), "\n"])


def assemble(trees: list[Tree], into: Path, index: str) -> None:
    """Lay out the built `trees` in `into`, a new directory, as the drafts site serves them.

    Each tree's `UNPUBLISHED_DIR` at the root and its `PUBLISHED_DIR` under `published/`,
    all in one tree, with `index` as its index.
    Hard links rather than copies, since the images and videos are most of it,
    so `into` has to be on the same disk as every tree.

    Run after `site.clashes` has found none, so what two trees both have is what every
    build writes beside its publications: the shared `assets/`, and `robots.txt`.
    Built from the same code in the same run, those come out the same,
    and are served once. Two that differ are refused, naming both,
    and nothing is written: either one served is the other build's pages
    linking a file they were not built with, which is what the drafts site is there to catch,
    and no rule for picking one would make both sets of pages right.
    """
    files: dict[PurePosixPath, tuple[Path, Path]] = {}
    differ = []
    for tree in trees:
        for part, under in (
            (UNPUBLISHED_DIR, PurePosixPath()),
            (PUBLISHED_DIR, PurePosixPath(PUBLISHED_DIR)),
        ):
            top = tree.built / part
            if not top.is_dir():
                continue
            for source in sorted(top.rglob("*")):
                rel = PurePosixPath(source.relative_to(top).as_posix())
                if source.is_dir() or rel.name == DOC_JSON:
                    continue
                if part == UNPUBLISHED_DIR and str(rel) in REPLACED:
                    continue
                dest = under / rel
                if dest not in files:
                    files[dest] = (source, tree.listed)
                    continue
                first, first_listed = files[dest]
                if not filecmp.cmp(first, source, shallow=False):
                    builds = f"`{first_listed}` and `{tree.listed}`"
                    differ.append(f"`/{dest}` differs between the builds of {builds}")
    if differ:
        raise Refused("; ".join(differ))
    into.mkdir()
    for dest, (source, _) in files.items():
        (into / dest).parent.mkdir(parents=True, exist_ok=True)
        os.link(source, into / dest)
    (into / "index.html").write_text(index)
    # The index's icon, which a list's build only writes once it has a publication.
    icon = into / ASSET_DIR / "logo.svg"
    if not icon.exists():
        icon.parent.mkdir(exist_ok=True)
        icon.write_text(read("logo.svg"))
