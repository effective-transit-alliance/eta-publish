"""What makes a set of reports a site: the list, the paths, and the index.

The per-document build lives in `build.py`.
Here is what only exists once there is more than one report.

Each report lands under its own published path,
taken from the `URL:` line in its front matter,
so the preview URL is the published URL with a different host in front of it.
A report whose header names no URL is not published at all,
since a slug of its headline would be a plausible path and not the published one.
Nor is one with no `Header` section for a URL to be named in.

That is one report failing, not the site:
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
from .naming import IMAGE_DIR, SITE
from .nodes import Document

REPORTS = Path("reports.toml")
"""Which documents the site is built from, committed beside the code."""


class Published(StrEnum):
    """Whether, and how, a report is out on Squarespace.

    Not a yes or no, because "out" is two different things here.
    A page built by hand in Squarespace references nothing this project hosts,
    and one pasted from `report.html` references every picture, video, and stylesheet
    it was built with, so only the second needs any of them served.
    """

    AUTOMATED = "automated"
    """Live, and the live page is this report's `report.html`."""

    MANUAL = "manual"
    """Live, as a page built by hand in Squarespace."""

    DRAFT = "draft"
    """Not out yet."""


@dataclass(frozen=True)
class Report:
    """One entry of `reports.toml`."""

    url: str
    """A Docs URL including its `?tab=` id, or a path to saved JSON."""

    name: str | None = None
    """What the document is called in Drive, which is what a build checks it against.

    Not where the report goes: that is the document's own to say.

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
    """A report that made it, and where it went."""

    report: Report
    doc: Document
    path: str
    """Site-relative directory, e.g. `reports/digging-out-deep-hole-sas-west`."""


@dataclass
class Failed:
    report: Report
    error: str


@dataclass
class Site:
    built: list[Built] = field(default_factory=list)
    failed: list[Failed] = field(default_factory=list)


def social_image(doc: Document, path: str, site_url: str = SITE) -> str:
    """Where the site serves the share card, for uploading as Squarespace's social image.

    Nothing where there is no card, or where no picture of it was written.
    """
    if doc.card is None or doc.card.object_id not in doc.image_files:
        return ""
    return f"{media_base(path, site_url)}/{doc.image_href(doc.card)}"


@dataclass(frozen=True)
class Hosts:
    """Where each half of the site is served: the list's own `[site]`,
    or `SITE` for either it leaves out.

    In the list rather than on the command line, because what is committed is built against them:
    a build that took them from a flag would write a different site for whoever forgot the flag.
    """

    published: str = SITE
    """Where `site/published/` is served, which the live pages link."""

    unpublished: str = SITE
    """Where `site/unpublished/` is served, which the previews are read at."""


def load_hosts(path: Path = REPORTS) -> Hosts:
    """The list's `[site]` URLs, each checked to be one."""
    if not path.exists():
        return Hosts()
    table = tomllib.loads(path.read_text()).get("site", {})
    if not isinstance(table, dict):
        raise ValueError(f"{path}: `site` is not a `[site]` table")
    urls: dict[str, str] = {}
    for key in ("published", "unpublished"):
        url = str(table.get(key, SITE)).strip().rstrip("/")
        if not url.startswith("https://"):
            raise ValueError(f"{path}: `[site] {key} = {url!r}` is not an `https://` URL")
        urls[key] = url
    return Hosts(**urls)


def load_reports(path: Path = REPORTS) -> list[Report]:
    """Read the report list, which is TOML so it can carry comments.

    Comments matter here: a list of documents is where someone needs to say
    "this one is the 2025 rewrite, not the original".
    """
    data = tomllib.loads(path.read_text())
    entries = data.get("report", [])
    reports = []
    for entry in entries:
        url = str(entry.get("url", "")).strip()
        if not url:
            raise ValueError(f"{path}: a [[report]] entry has no `url`")
        # Required rather than defaulted: a draft hosted by mistake is out,
        # and a live report left as a draft by mistake loses its pictures.
        published = str(entry.get("published", ""))
        if published not in set(Published):
            values = ", ".join(f"`{value}`" for value in Published)
            raise ValueError(f"{path}: {url} has `published = {published!r}`, not one of {values}")
        # A string either way, never `None`: an entry states an expectation
        # whatever it says, and one that says nothing says the document is
        # named nothing, which is a disagreement like any other.
        reports.append(
            Report(
                url=url,
                name=str(entry.get("name", "")).strip(),
                tab=str(entry.get("tab", "")).strip(),
                published=Published(published),
            )
        )
    if not reports:
        raise ValueError(f"{path}: no [[report]] entries")
    return reports


def listed_report(doc: str, path: Path = REPORTS) -> Report:
    """The entry `doc` names, or `doc` itself as a document named on the command line.

    A name is what anyone remembers a report by, and its URL is what nobody does.
    Picked by name, the entry comes with its expectations,
    so `one` checks the document against them just as `all` would.
    Case is ignored, since nobody types a title's capitals reliably.
    Anything that is not a listed name is a URL, an id, or a saved response, as before:
    no Docs URL or id reads as a report's title.
    """
    if not path.exists():
        return Report(url=doc)
    wanted = doc.strip().casefold()
    matches = [r for r in load_reports(path) if (r.name or "").casefold() == wanted]
    if len(matches) > 1:
        tabs = ", ".join(f"`{r.tab}`" for r in matches)
        raise ValueError(f"{path}: more than one report is named `{doc}`, on tabs {tabs}")
    return matches[0] if matches else Report(url=doc)


def entry_text(url: str, name: str, tab: str, published: Published) -> str:
    """One `[[report]]` block, as `reports.toml` writes them.

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

    They are dropped here so that `reports.toml` is a list of documents
    rather than a list of the moments they were copied,
    and so that the same document pasted twice is recognized as listed.

    Anything that is not a Docs URL is left alone: a bare document id and
    a path to a saved response are both accepted, and neither has parts to drop.
    """
    if "docs.google.com" not in url:
        return url
    doc_id, tab = parse_ref(url)
    return document_url(doc_id, tab or "")


def add_report(url: str, path: Path = REPORTS) -> Report:
    """Append the document at `url` to the report list, named as it names itself.

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
    if any(canonical(report.url) == url for report in load_reports(path)):
        raise ValueError(f"{path}: already lists {url}")

    document = load(url)
    name = str(document.get("title", ""))
    tab = str(document.get("tabTitle", ""))
    for field_name, value in (("name", name), ("tab", tab)):
        if not value:
            # Writing an empty one down is what `load_reports` refuses.
            raise ValueError(f"{url}: the document says no `{field_name}`")

    entry = entry_text(url, name, tab, Published.DRAFT)
    path.write_text(path.read_text().rstrip("\n") + "\n" + entry)
    return Report(url=url, name=name, tab=tab)


def saved_responses(outdir: Path) -> dict[tuple[str, str], Path]:
    """Every response a previous build wrote under `outdir`, by document and tab.

    A report's directory is named after its own `URL:` line, which is a path
    and not an id, so nothing about `reports.toml` says where a given entry's
    last response was written. Reading the responses is what joins the two,
    which is why each records the `documentId` and `tabId` it came from.

    Scanned once for a whole build rather than per report:
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


def saved_for(report: Report, saved: dict[tuple[str, str], Path]) -> Path | None:
    """Where the last build of `report` wrote its response, if it is still there."""
    doc_id, tab = parse_ref(report.url)
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


def report_path(doc: Document) -> str:
    """Where this report goes on the site, from its own front matter.

    The leading slash is dropped because the site is a directory tree,
    and a report published at the root of a domain
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

    All three refusals are this one report's, not the site's:
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
            "add one, as the other reports have"
        )
    if ".." in PurePosixPath(slug).parts or PurePosixPath(slug).is_absolute():
        raise ValueError(f"the `URL:` line is `{doc.slug}`, which climbs out of the site")
    return slug


def label(report: Report) -> str:
    """What to call this report in the log.

    Its entry in `reports.toml`, and the URL for a document built without one,
    which is what `eta-publish one` passes. In one place because the heading
    and the notes written under it have to agree: the same report named two
    ways reads as two reports.
    """
    return report.name or report.url


def verifier(report: Report) -> Callable[[Document], None]:
    """What `build_one` calls once the document is parsed and before it is written.

    A disagreement is found after the fetch and has to stop the build before the emit,
    or a report that failed its own check leaves a directory of published files behind,
    which the next run compares against and finds nothing wrong with.

    A callback rather than the `Report` itself,
    because which entry a document was supposed to be
    is a question about `reports.toml` and not about building a document.
    """

    def verify(doc: Document) -> None:
        said = disagreements(report, doc)
        if said:
            raise ValueError("; ".join(said))

    return verify


def source(report: Report, previous: Path | None, options: BuildOptions) -> str:
    """What to build this report from: the document, or the last response saved for it.

    A report with no saved response cannot be built offline,
    and neither can one saved with its suggestions resolved the other way.
    Saying so is better than fetching one document
    in a run that was asked not to fetch anything.
    """
    if not options.offline:
        return report.url
    if previous is None:
        raise ValueError(
            f"nothing saved under the output directory for {report.url}; "
            "build it once with a fetch before building it offline"
        )
    # A fetch would notice this and go and get the other one.
    # Offline cannot, so it says so rather than publishing the document
    # read the way the last build happened to read it.
    saved_as = str(json.loads((previous / DOC_JSON).read_text()).get("suggestions", ""))
    if saved_as != options.suggestions:
        raise ValueError(
            f"what is saved for {report.url} has its suggestions {saved_as or 'unrecorded'}, "
            f"and this build wants them {options.suggestions}; "
            "reading the document the other way needs a fetch"
        )
    return str(previous)


MAX_AT_ONCE = 8
"""How many reports to build at once.

A build is almost entirely waiting on Google, so these overlap well.
A ceiling rather than one thread a report, because the calls are rate limited
at the other end and thirty asking at once is a way to be told to wait.
"""


def build_site(
    reports: list[Report],
    outdir: Path,
    options: BuildOptions | None = None,
    read_from: Path | None = None,
) -> Site:
    """Build every report, keeping going when one of them cannot be built.

    A document that cannot be fetched says nothing about the next one,
    and a site missing one report beats no site at all.

    Several at a time, because nearly all of a build is waiting for a reply.
    Each carries its own HTTP client the whole way down, which is not tidiness
    but a requirement: the client under the Google libraries is `httplib2`,
    and one shared across threads takes the interpreter down in the allocator
    rather than raising anything.

    Reported in the order the list gives rather than the order they finish,
    which also means the first one's warnings are printed
    while the rest are still running.

    What the last build left is read from `read_from`, `outdir` by default,
    and a report built from another directory carries over what it reads.
    """
    options = options or BuildOptions()
    # Always, not only offline: a fetch reuses one too, when Drive says
    # the document behind it has not been edited since it was written.
    saved = saved_responses(read_from or outdir)
    site = Site()
    log = console.for_stream()

    def build(report: Report) -> tuple[Document, str]:
        previous = saved_for(report, saved)
        named = label(report)
        # Named for the whole of the build, so the notes it writes along the
        # way say which report they are about. Several reports are built at
        # once and each writes as it goes, so an unattributed line is one the
        # reader has to guess the owner of.
        with (
            console.about(named),
            console.stepping(partial(rows.show, named)),
        ):
            try:
                return build_one(
                    source(report, previous, options),
                    outdir,
                    options,
                    verify=verifier(report),
                    cached=reusable(previous, options),
                    previous=previous,
                    read_from=read_from,
                    publishes=report.published is Published.AUTOMATED,
                )
            finally:
                rows.drop(named)
                along()

    # The whole build as one bar, and a line under it per report saying what it
    # is doing: a report is printed only once it and every one listed before it
    # are done, which on a build that archives can be minutes of nothing.
    with (
        console.progress("building reports", len(reports), quiet=True) as along,
        console.watching() as rows,
    ):
        return _built(reports, build, site, log, options)


def _built(
    reports: list[Report],
    build: Callable[[Report], tuple[Document, str]],
    site: Site,
    log: Console,
    options: BuildOptions,
) -> Site:
    """Run `build` over every report at once, writing each out in list order as it is done."""
    pool = ThreadPoolExecutor(max_workers=max(1, min(len(reports), MAX_AT_ONCE)))
    started = [(report, pool.submit(build, report)) for report in reports]
    try:
        for index, (report, building) in enumerate(started):
            # A blank line between reports and none above the first:
            # a report is a heading and everything under it, and a run of them
            # with nothing between is one list of warnings rather than three.
            if index:
                log.line()
            named = label(report)
            try:
                doc, path = building.result()
            except Exception as e:
                # Broad on purpose: a fetch, parse, disagreement, or disk failure
                # is the same decision here,
                # which is to keep going and say which report did not make it.
                console.write(console.failed(named, str(e)), log)
                site.failed.append(Failed(report=report, error=str(e)))
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
                        if report.published is Published.AUTOMATED
                        else options.unpublished_url,
                    ),
                ),
            ]
            console.write(console.built(named, path, doc.warnings, log, paste), log)
            site.built.append(Built(report=report, doc=doc, path=path))
    except KeyboardInterrupt:
        # Not waited on: `Ctrl+C` reaches only this thread, and the reports
        # are on others, each in the middle of a request that can take a
        # minute. Waiting for them is what made one `Ctrl+C` look like
        # nothing, and a second one a traceback through the joining.
        pool.shutdown(wait=False, cancel_futures=True)
        running = [label(report) for report, building in started if building.running()]
        said = "stopped"
        if running:
            said += " while building " + ", ".join(running)
        waiting = console.waiting_on()
        if waiting:
            said += "; waiting on:\n" + "\n".join(f"  {line}" for line in waiting)
        raise Stopped(said) from None
    pool.shutdown()
    return site


def disagreements(report: Report, doc: Document) -> list[str]:
    """Where `reports.toml` and the document it points at do not match.

    Only checkable here, after the fetch:
    nothing in `reports.toml` says what the document is called
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
        ("calls this", report.name, "the document is named", doc.file_title),
        ("expects the tab", report.tab, "the tab is named", doc.tab_title),
    )
    return [
        f"reports.toml {said} `{expected}`, but {found_label} `{found}`"
        for said, expected, found_label, found in checks
        if expected is not None and expected != found
    ]


INDEX_CSS = read("index.css")


def _newest_first(built: Built) -> tuple[bool, int]:
    """Newest first, as a list of publications reads.

    An undated report has not been published yet, so it goes after them, in the list's order.
    """
    published = built.doc.published
    return published is None, -(published or date.min).toordinal()


def index_page(site: Site) -> str:
    """The site's front page: every report, and anything that did not build.

    Failures are on the page, not only in the log, because the page is what people read.
    A report quietly missing from a list of four is hard to notice;
    a line saying which one failed and why is not.
    """
    entries: list[Piece] = []
    for built in sorted(site.built, key=_newest_first):
        doc = built.doc
        meta = [m for m in (doc.dateline, ", ".join(doc.contributors)) if m]
        warned = f" · {len(doc.warnings)} warning(s)" if doc.warnings else ""
        # The phase above the title, as the report itself carries it:
        # a draft has to say so wherever it is read, and this list is where
        # someone picks which report to open.
        phase = [Markup(phase_markup(doc.phase))] if doc.phase else []
        # The share card, as a link to the report shows it everywhere else.
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
        tag.p(class_="failed")[f"{f.report.name or f.report.url}: {f.error}"] for f in site.failed
    ]
    page: list[Piece] = [
        htpy.meta(charset="utf-8"),
        htpy.meta(name="viewport", content="width=device-width, initial-scale=1"),
        # Until the reports are published, nothing here should be findable.
        # `robots.txt` only asks a crawler not to fetch a page,
        # which leaves one already indexed where it is;
        # `noindex` is what takes it back out,
        # and it is the only one of the two that a project page can carry at all,
        # since `robots.txt` is read from the root of the host
        # and these pages are served from a path under it.
        # Remove this, and `site/unpublished/robots.txt`, when the reports go out.
        htpy.meta(name="robots", content="noindex, nofollow"),
        tag.title["ETA report previews"],
        tag.style[Markup(f"\n{INDEX_CSS}")],
        tag.h1["ETA report previews"],
        tag.p["Built from the Google Docs, warnings included. Not the published pages."],
        tag.ul["\n", lines(entries), "\n"],
        *failures,
    ]
    return markup([Markup("<!doctype html>"), "\n", lines(page), "\n"])
