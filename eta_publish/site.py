"""What makes a set of publications a site: the list, the paths, and the index.

The per-document build lives in `build.py`.
Here is what only exists once there is more than one publication.

Each publication lands under its own published path,
taken from the `URL:` line in its front matter,
so the preview URL is the published URL with a different host in front of it.
A publication whose header names no URL is not published at all,
since a slug of its headline would be a plausible path and not the published one.
Nor is one with no `Header` section for a URL to be named in.

That is one publication failing, not the site:
the others are still built and the exit status still reports it.
"""

import json
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from functools import partial
from pathlib import Path, PurePosixPath

import htpy
from markupsafe import Markup
from rich.console import Console

from . import console
from .archive import Stopped
from .assets import read
from .build import DOC_JSON, BuildOptions, build_one, has_its_images, load, media_base
from .emit.html import Piece, lines, markup, phase_markup, tag
from .fetch import document_url, parse_ref
from .naming import ASSET_DIR, IMAGE_DIR
from .nodes import Document

PUBLICATIONS = Path("publications.toml")
"""Which documents the site is built from, committed beside the code."""


class Published(StrEnum):
    """Whether, and how, a publication is out on Squarespace.

    Not a yes or no, because "out" is two different things here.
    A page built by hand in Squarespace references nothing this project hosts,
    and one pasted from `report.html` references every picture, video, and stylesheet
    it was built with, so only the second needs any of them served.
    """

    AUTOMATED = "automated"
    """Live, and the live page is this publication's `report.html`."""

    MANUAL = "manual"
    """Live, as a page built by hand in Squarespace."""

    DRAFT = "draft"
    """Not out yet."""


@dataclass(frozen=True)
class Publication:
    """One entry of `publications.toml`."""

    url: str
    """A Docs URL including its `?tab=` id, or a path to saved JSON."""

    name: str | None = None
    """What the document is called in Drive, which is what a build checks it against.

    Not where the publication goes: that is the document's own to say.

    `None` is a document named on the command line, which states no expectation.
    An entry always states one, `""` included:
    a field left empty says the document is called nothing, which no document is."""

    tab: str | None = None
    """What the tab in `url` is called, checked the same way.

    The `?tab=` id is opaque, so nothing about the URL says which draft it points at,
    and publishing last year's draft is the mistake nothing else can catch.

    `None` on the same terms as `name`."""

    published: Published = Published.DRAFT
    """Whether it is out, and how.

    A document named on the command line is a draft:
    nothing says it is out, and assuming it is would host it."""


@dataclass
class Built:
    """A publication that made it, and where it went."""

    publication: Publication
    doc: Document
    path: str
    """Site-relative directory, e.g. `reports/digging-out-deep-hole-sas-west`."""


@dataclass
class Failed:
    publication: Publication
    error: str


@dataclass
class Site:
    built: list[Built] = field(default_factory=list)
    failed: list[Failed] = field(default_factory=list)


def social_image(doc: Document, path: str, site_url: str) -> str:
    """Where the site serves the share card, for uploading as Squarespace's social image.

    Nothing where there is no card, or where no picture of it was written.
    """
    if doc.card is None or doc.card.object_id not in doc.image_files:
        return ""
    return f"{media_base(path, site_url)}/{doc.image_href(doc.card)}"


@dataclass(frozen=True)
class Hosts:
    """Where each half of the site is served: the list's own `[site]`.

    In the list rather than on the command line, because what is committed is built against them:
    a build that took them from a flag would write a different site for whoever forgot the flag.
    And with no default, because a default is a host someone forgot to change,
    and the PDF, read away from the site, carries its links wherever it goes.
    """

    published: str
    """Where `site/published/` is served, which the live pages link."""

    unpublished: str
    """Where `site/unpublished/` is served, which the previews are read at."""


def load_hosts(path: Path = PUBLICATIONS) -> Hosts:
    """The list's `[site]` URLs, each checked to be one."""
    table = tomllib.loads(path.read_text()).get("site")
    if table is None:
        raise ValueError(f"{path}: has no `[site]` table saying where the site is served")
    if not isinstance(table, dict):
        raise ValueError(f"{path}: `site` is not a `[site]` table")
    urls: dict[str, str] = {}
    for key in ("published", "unpublished"):
        if key not in table:
            raise ValueError(f"{path}: `[site]` has no `{key}` URL")
        url = str(table[key]).strip().rstrip("/")
        if not url.startswith("https://"):
            raise ValueError(f"{path}: `[site] {key} = {url!r}` is not an `https://` URL")
        urls[key] = url
    return Hosts(**urls)


def load_publications(path: Path = PUBLICATIONS) -> list[Publication]:
    """Read the publication list, which is TOML so it can carry comments.

    Comments matter here: a list of documents is where someone needs to say
    "this one is the 2025 rewrite, not the original".
    """
    data = tomllib.loads(path.read_text())
    entries = data.get("report", [])
    publications = []
    for entry in entries:
        url = str(entry.get("url", "")).strip()
        if not url:
            raise ValueError(f"{path}: a [[report]] entry has no `url`")
        # Required rather than defaulted: a draft hosted by mistake is out,
        # and a live publication left as a draft by mistake loses its pictures.
        published = str(entry.get("published", ""))
        if published not in set(Published):
            values = ", ".join(f"`{value}`" for value in Published)
            raise ValueError(f"{path}: {url} has `published = {published!r}`, not one of {values}")
        # A string either way, never `None`: an entry states an expectation
        # whatever it says, and one that says nothing says the document is
        # named nothing, which is a disagreement like any other.
        publications.append(
            Publication(
                url=url,
                name=str(entry.get("name", "")).strip(),
                tab=str(entry.get("tab", "")).strip(),
                published=Published(published),
            )
        )
    if not publications:
        raise ValueError(f"{path}: no [[report]] entries")
    return publications


def listed_publication(doc: str, path: Path = PUBLICATIONS) -> Publication:
    """The entry `doc` names, or `doc` itself as a document named on the command line.

    A name is what anyone remembers a publication by, and its URL is what nobody does.
    Picked by name, the entry comes with its expectations,
    so `one` checks the document against them just as `all` would.
    Case is ignored, since nobody types a title's capitals reliably.
    Anything that is not a listed name is a URL, an id, or a saved response, as before:
    no Docs URL or id reads as a publication's title.
    """
    if not path.exists():
        return Publication(url=doc)
    wanted = doc.strip().casefold()
    matches = [r for r in load_publications(path) if (r.name or "").casefold() == wanted]
    if len(matches) > 1:
        tabs = ", ".join(f"`{r.tab}`" for r in matches)
        raise ValueError(f"{path}: more than one publication is named `{doc}`, on tabs {tabs}")
    return matches[0] if matches else Publication(url=doc)


def entry_text(url: str, name: str, tab: str, published: Published) -> str:
    """One `[[report]]` block, as `publications.toml` writes them.

    Built as text rather than dumped from a table
    because the file is mostly comments:
    "this one is the 2025 rewrite, not the original" is the reason it is TOML
    at all, and a round trip through `tomllib` would drop every line of it.

    The values go through `json.dumps`, which is a TOML basic string
    for anything a Drive title can hold: the same quoting, the same escapes.
    A title with a quotation mark in it is a title, not a syntax error.
    """
    return (
        "\n[[report]]\n"
        f"name = {json.dumps(name)}\n"
        f"tab = {json.dumps(tab)}\n"
        f"url = {json.dumps(url)}\n"
        f"published = {json.dumps(str(published))}\n"
    )


def canonical(url: str) -> str:
    """A Docs URL with nothing in it but the document and the tab.

    A URL copied out of the address bar carries whatever the browser had:
    `?pli=1` says the reader is signed into more than one account, and
    `#heading=h.mkzkbxod1acf` is where their cursor was. Neither says
    anything about the document, and the fetch already ignores both.

    They are dropped here so that `publications.toml` is a list of documents
    rather than a list of the moments they were copied,
    and so that the same document pasted twice is recognized as listed.

    Anything that is not a Docs URL is left alone: a bare document id and
    a path to a saved response are both accepted, and neither has parts to drop.
    """
    if "docs.google.com" not in url:
        return url
    doc_id, tab = parse_ref(url)
    return document_url(doc_id, tab or "")


def add_publication(url: str, path: Path = PUBLICATIONS) -> Publication:
    """Append the document at `url` to the publication list, named as it names itself.

    `name` and `tab` are the document's own `title` and `tabTitle`,
    which is the only reason this command exists:
    they are required to be right, and a person copying two titles out of
    Drive by hand is the step that gets them wrong.

    An entry whose `url` is already listed is refused rather than duplicated:
    two entries for one document publish it twice to the same path,
    and the second build silently overwrites the first.

    A document being added is a draft until someone says otherwise.
    """
    url = canonical(url)
    if any(canonical(publication.url) == url for publication in load_publications(path)):
        raise ValueError(f"{path}: already lists {url}")

    document = load(url)
    name = str(document.get("title", ""))
    tab = str(document.get("tabTitle", ""))
    for field_name, value in (("name", name), ("tab", tab)):
        if not value:
            # Writing an empty one down is what `load_publications` refuses.
            raise ValueError(f"{url}: the document says no `{field_name}`")

    entry = entry_text(url, name, tab, Published.DRAFT)
    path.write_text(path.read_text().rstrip("\n") + "\n" + entry)
    return Publication(url=url, name=name, tab=tab)


def saved_responses(outdir: Path) -> dict[tuple[str, str], Path]:
    """Every response a previous build wrote under `outdir`, by document and tab.

    A publication's directory is named after its own `URL:` line, which is a path
    and not an id, so nothing about `publications.toml` says where a given entry's
    last response was written. Reading the responses is what joins the two,
    which is why each records the `documentId` and `tabId` it came from.

    Scanned once for a whole build rather than per publication:
    a site is a directory of them, and each answer is the same walk.
    """
    found: dict[tuple[str, str], Path] = {}
    for saved in sorted(outdir.glob(f"*/*/{DOC_JSON}")) + sorted(outdir.glob(f"*/{DOC_JSON}")):
        try:
            document = json.loads(saved.read_text())
        except OSError, ValueError:
            # Not a saved response, whatever else it is.
            continue
        key = (str(document.get("documentId", "")), str(document.get("tabId", "")))
        if all(key):
            found.setdefault(key, saved.parent)
    return found


def saved_for(publication: Publication, saved: dict[tuple[str, str], Path]) -> Path | None:
    """Where the last build of `publication` wrote its response, if it is still there."""
    doc_id, tab = parse_ref(publication.url)
    return saved.get((doc_id, tab or ""))


def reusable(previous: Path | None, options: BuildOptions) -> Path | None:
    """The response a fetch may reuse, which is not every response there is.

    Drive answering that the document has not been edited is not enough on its own.
    The response is committed and the images it describes are not,
    so a fresh checkout has one describing pictures that are not beside it,
    and a `contentUri` expires within the hour and is never saved.
    Reused there, the build downloads nothing,
    the emitters have no filename to write,
    and the page publishes with every image missing.
    Fetching the document again is what turns up the URIs to download from,
    and it is only the cost of the build that a fresh checkout is doing anyway.

    A `--no-images` build reuses it regardless:
    it is not going to download them either way,
    and the pictures on disk are not what it is asking about.
    """
    if previous is None:
        return None
    if options.images and not has_its_images(previous):
        return None
    return previous / DOC_JSON


def publication_path(doc: Document) -> str:
    """Where this publication goes on the site, from its own front matter.

    The leading slash is dropped because the site is a directory tree,
    and a publication at the root of a domain
    would otherwise write to the root of the filesystem.

    A path that climbs is refused for the same reason and a stronger one:
    `URL: /../../etc` is a document choosing a directory outside the site,
    and the check that the committed site is what a build writes
    only ever looks inside `site/`, so it would not notice.

    A document that names no URL at all is refused rather than guessed at,
    since a slug of the headline is a plausible path and not the published one.
    That is two refusals rather than one, because it is two mistakes:
    a `Header` section with no `URL:` line in it,
    and no `Header` section at all, which is what a document has
    when its `Header` line is styled as body text rather than as a heading.
    Naming the one that happened is the difference between
    a line to go and add and a line to go and restyle.

    All three refusals are this one publication's, not the site's:
    `build_site` goes on to the next.
    """
    slug = doc.slug.strip("/")
    if not slug and not doc.has_header:
        raise ValueError(
            "no `Header` section, so nothing says where this publishes; "
            "add one, styling its heading as a heading rather than as body text"
        )
    if not slug:
        raise ValueError(
            "no `URL:` line in the `Header` section, so nothing says where this publishes; "
            "add one, as the other publications have"
        )
    if ".." in PurePosixPath(slug).parts or PurePosixPath(slug).is_absolute():
        raise ValueError(f"the `URL:` line is `{doc.slug}`, which climbs out of the site")
    return slug


def label(publication: Publication) -> str:
    """What to call this publication in the log.

    Its entry in `publications.toml`, and the URL for a document built without one,
    which is what `eta-publish one` passes. In one place because the heading
    and the notes written under it have to agree: the same publication named two
    ways reads as two publications.
    """
    return publication.name or publication.url


def verifier(publication: Publication) -> Callable[[Document], None]:
    """What `build_one` calls once the document is parsed and before it is written.

    A disagreement is found after the fetch and has to stop the build before the emit,
    or a publication that failed its own check leaves a directory of published files behind,
    which the next run compares against and finds nothing wrong with.

    A callback rather than the `Publication` itself,
    because which entry a document was supposed to be
    is a question about `publications.toml` and not about building a document.
    """

    def verify(doc: Document) -> None:
        said = disagreements(publication, doc)
        if said:
            raise ValueError("; ".join(said))

    return verify


def source(publication: Publication, previous: Path | None, options: BuildOptions) -> str:
    """What to build this publication from: the document, or the last response saved for it.

    A publication with no saved response cannot be built offline,
    and neither can one saved with its suggestions resolved the other way.
    Saying so is better than fetching one document
    in a run that was asked not to fetch anything.
    """
    if not options.offline:
        return publication.url
    if previous is None:
        raise ValueError(
            f"nothing saved under the output directory for {publication.url}; "
            "build it once with a fetch before building it offline"
        )
    # A fetch would notice this and go and get the other one.
    # Offline cannot, so it says so rather than publishing the document
    # read the way the last build happened to read it.
    saved_as = str(json.loads((previous / DOC_JSON).read_text()).get("suggestions", ""))
    if saved_as != options.suggestions:
        raise ValueError(
            f"what is saved for {publication.url} has its suggestions {saved_as or 'unrecorded'}, "
            f"and this build wants them {options.suggestions}; "
            "reading the document the other way needs a fetch"
        )
    return str(previous)


MAX_AT_ONCE = 8
"""How many publications to build at once.

A build is almost entirely waiting on Google, so these overlap well.
A ceiling rather than one thread a publication, because the calls are rate limited
at the other end and thirty asking at once is a way to be told to wait.
"""


def build_site(
    publications: list[Publication],
    outdir: Path,
    options: BuildOptions,
    read_from: Path | None = None,
) -> Site:
    """Build every publication, keeping going when one of them cannot be built.

    A document that cannot be fetched says nothing about the next one,
    and a site missing one publication beats no site at all.

    Several at a time, because nearly all of a build is waiting for a reply.
    Each carries its own HTTP client the whole way down, which is not tidiness
    but a requirement: the client under the Google libraries is `httplib2`,
    and one shared across threads takes the interpreter down in the allocator
    rather than raising anything.

    Reported in the order the list gives rather than the order they finish,
    which also means the first one's warnings are printed
    while the rest are still running.

    What the last build left is read from `read_from`, `outdir` by default,
    and a publication built from another directory carries over what it reads.
    """
    # Always, not only offline: a fetch reuses one too, when Drive says
    # the document behind it has not been edited since it was written.
    saved = saved_responses(read_from or outdir)
    site = Site()
    log = console.for_stream()

    def build(publication: Publication) -> tuple[Document, str]:
        previous = saved_for(publication, saved)
        named = label(publication)
        # Named for the whole of the build, so the notes it writes along the
        # way say which publication they are about. Several publications are built at
        # once and each writes as it goes, so an unattributed line is one the
        # reader has to guess the owner of.
        with (
            console.about(named),
            console.stepping(partial(rows.show, named)),
        ):
            try:
                return build_one(
                    source(publication, previous, options),
                    outdir,
                    options,
                    verify=verifier(publication),
                    cached=reusable(previous, options),
                    previous=previous,
                    read_from=read_from,
                    publishes=publication.published is Published.AUTOMATED,
                )
            finally:
                rows.drop(named)
                along()

    # The whole build as one bar, and a line under it per publication saying what it
    # is doing: a publication is printed only once it and every one listed before it
    # are done, which on a build that archives can be minutes of nothing.
    with (
        console.progress("building publications", len(publications), quiet=True) as along,
        console.watching() as rows,
    ):
        return _built(publications, build, site, log, options)


def _built(
    publications: list[Publication],
    build: Callable[[Publication], tuple[Document, str]],
    site: Site,
    log: Console,
    options: BuildOptions,
) -> Site:
    """Run `build` over every publication at once, writing each out in list order as it is done."""
    pool = ThreadPoolExecutor(max_workers=max(1, min(len(publications), MAX_AT_ONCE)))
    started = [(publication, pool.submit(build, publication)) for publication in publications]
    try:
        for index, (publication, building) in enumerate(started):
            # A blank line between publications and none above the first:
            # a publication is a heading and everything under it, and a run of them
            # with nothing between is one list of warnings rather than three.
            if index:
                log.line()
            named = label(publication)
            try:
                doc, path = building.result()
            except Exception as e:
                # Broad on purpose: a fetch, parse, disagreement, or disk failure
                # is the same decision here,
                # which is to keep going and say which publication did not make it.
                console.write(console.failed(named, str(e)), log)
                site.failed.append(Failed(publication=publication, error=str(e)))
                continue
            paste = [
                ("SEO title", doc.title),
                ("SEO description", doc.meta.get("SEO Description", "")),
                # A blog post's excerpt, or a page's line in `What's New`.
                ("Short", doc.meta.get("Short", "")),
                # Where the page that shows it is: only a live page's is published.
                (
                    "Social image",
                    social_image(
                        doc,
                        path,
                        options.published_url
                        if publication.published is Published.AUTOMATED
                        else options.unpublished_url,
                    ),
                ),
            ]
            console.write(console.built(named, path, doc.warnings, log, paste), log)
            site.built.append(Built(publication=publication, doc=doc, path=path))
    except KeyboardInterrupt:
        # Not waited on: `Ctrl+C` reaches only this thread, and the publications
        # are on others, each in the middle of a request that can take a
        # minute. Waiting for them is what made one `Ctrl+C` look like
        # nothing, and a second one a traceback through the joining.
        pool.shutdown(wait=False, cancel_futures=True)
        running = [label(publication) for publication, building in started if building.running()]
        said = "stopped"
        if running:
            said += " while building " + ", ".join(running)
        waiting = console.waiting_on()
        if waiting:
            said += "; waiting on:\n" + "\n".join(f"  {line}" for line in waiting)
        raise Stopped(said) from None
    pool.shutdown()
    return site


def disagreements(publication: Publication, doc: Document) -> list[str]:
    """Where `publications.toml` and the document it points at do not match.

    Only checkable here, after the fetch:
    nothing in `publications.toml` says what the document is called
    or which of its tabs a `?tab=` id picks out.

    Every expectation is compared, and nothing about a value exempts it:
    an unanswered question is not a passed check,
    and a blank is not a shorter entry.
    Only a document named straight on the command line is skipped,
    which is not an entry and holds no expectation to compare.

    Not warnings: the document is fine and this file is wrong about it,
    which is nothing for the writers to fix
    and not something to publish past either.
    """
    checks = (
        ("calls this", publication.name, "the document is named", doc.file_title),
        ("expects the tab", publication.tab, "the tab is named", doc.tab_title),
    )
    return [
        f"publications.toml {said} `{expected}`, but {found_label} `{found}`"
        for said, expected, found_label, found in checks
        if expected is not None and expected != found
    ]


INDEX_CSS = read("index.css")


def _newest_first(built: Built) -> tuple[bool, int]:
    """Newest first, as a list of publications reads.

    An undated publication has not been published yet, so it goes after them, in the list's order.
    """
    published = built.doc.published
    return published is None, -(published or date.min).toordinal()


def index_page(site: Site) -> str:
    """The site's front page: every publication, and anything that did not build.

    Failures are on the page, not only in the log, because the page is what people read.
    A publication quietly missing from a list of four is hard to notice;
    a line saying which one failed and why is not.
    """
    entries: list[Piece] = []
    for built in sorted(site.built, key=_newest_first):
        doc = built.doc
        meta = [m for m in (doc.dateline, ", ".join(doc.contributors)) if m]
        warned = f" · {len(doc.warnings)} warning(s)" if doc.warnings else ""
        # The phase above the title, as the publication itself carries it:
        # a draft has to say so wherever it is read, and this list is where
        # someone picks which publication to open.
        phase = [Markup(phase_markup(doc.phase))] if doc.phase else []
        # The share card, as a link to the publication shows it everywhere else.
        # Decorative here: the title beside it is the same words, and a link.
        thumbnail: list[Piece] = []
        if doc.card is not None and doc.card.object_id in doc.image_files:
            src = f"{built.path}/{IMAGE_DIR}/{doc.image_href(doc.card)}"
            thumbnail.append(
                tag.a(href=f"{built.path}/", tabindex="-1", aria_hidden="true")[
                    htpy.img(class_="card", src=src, alt="", loading="lazy")
                ]
            )
        entries.append(
            tag.li[
                *thumbnail,
                *phase,
                tag.a(href=f"{built.path}/")[tag.strong[doc.title]],
                # What a blog post's excerpt or `What's New` says, so the card says the same.
                tag.div(class_="short")[doc.meta.get("Short", "")],
                tag.div(class_="meta")[" · ".join(meta), warned],
            ]
        )
    failures = [
        tag.p(class_="failed")[f"{f.publication.name or f.publication.url}: {f.error}"]
        for f in site.failed
    ]
    page: list[Piece] = [
        htpy.meta(charset="utf-8"),
        htpy.meta(name="viewport", content="width=device-width, initial-scale=1"),
        # Until the publications are published, nothing here should be findable.
        # `robots.txt` only asks a crawler not to fetch a page,
        # which leaves one already indexed where it is;
        # `noindex` is what takes it back out,
        # and it is the only one of the two that a project page can carry at all,
        # since `robots.txt` is read from the root of the host
        # and these pages are served from a path under it.
        # Remove this, and `site/unpublished/robots.txt`, when the publications go out.
        htpy.meta(name="robots", content="noindex, nofollow"),
        tag.title["ETA publication previews"],
        htpy.link(rel="icon", type="image/svg+xml", href=f"{ASSET_DIR}/logo.svg"),
        tag.style[Markup(f"\n{INDEX_CSS}")],
        tag.h1["ETA publication previews"],
        tag.p["Built from the Google Docs, warnings included. Not the published pages."],
        tag.ul["\n", lines(entries), "\n"],
        *failures,
    ]
    return markup([Markup("<!doctype html>"), "\n", lines(page), "\n"])
