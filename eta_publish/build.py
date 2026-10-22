"""The build itself: fetch, emit, compile, and the checks around them."""

import glob
import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
lazy import os
lazy import shutil
lazy import subprocess

from rich.console import RenderableType
lazy from PIL import Image as Pillow
lazy from PIL import UnidentifiedImageError

from . import console
from .archive import (
    ACCESS_KEY,
    ANONYMOUS_EVERY,
    ARCHIVES_JSON,
    IA_CONFIG,
    KEYS_PAGE,
    SECRET_KEY,
    anonymous_allowed,
    capture,
    check_pending,
    count_pages,
    have_keys,
    missing,
    read_archive_index,
    uncounted,
    write_archive_index,
)
from .checks import check, check_described, check_pages, plural
from .docs_json import JsonObject
from .embeds import (
    EMBEDS_JSON,
    check_embeds,
    look_up,
    read_embed_index,
    write_captions,
    write_embed_index,
)
from .embeds import download as download_embeds
from .emit.html import CODE_BLOCK_LIMIT, CODE_BLOCK_WARN, HtmlEmitter, publication_page
from .emit.markdown import MarkdownEmitter
from .emit.typst import TypstEmitter
from .logo import LOGO, warning_poster
from .naming import (
    ASSET_DIR,
    IMAGE_DIR,
    LIVE_SITE,
    PRINT_DIR,
    VIDEO_DIR,
    WEB_DIR,
    video_frame_name,
    warning_poster_name,
)
from .nodes import Document, Shown, Span
from .parse import parse, read_review
from .style import style
lazy from .assets import read
lazy from .fetch import fetch
lazy from .images import (
    download,
    original_name,
    svg_description,
    write_print_copies,
    write_web_copies,
)
lazy from .pdf import TypstMissing, compile_pdf, install_template
lazy from .site import check_kind, publication_kind, publication_path


@dataclass(frozen=True)
class BuildOptions:
    """Everything the command line can vary about one build.

    A record rather than six parameters:
    all of these have to reach `build_one` from the argument parser,
    and a positional list that long is where a caller transposes two flags.
    """

    suggestions: str = "rejected"
    split: bool = False
    images: bool = True

    archive: bool = True
    """Whether to ask the Wayback Machine about the sources the publication cites.

    On, because a link is archived at the moment it is cited or not at the
    moment it is cited. Off is for a build that should touch nothing: the
    record still decides what every output says, so the pages are the same
    either way for a source already in it.
    """

    offline: bool = False
    """Whether to rebuild from the responses a previous build saved.

    No credentials, no network, and no way to notice a document that changed.
    A rebuild of what is committed, for a change to this code rather than to a doc.
    """

    unpublished_url: str = field(kw_only=True)
    """Where `site/unpublished/` is served, which a preview's absolute links start with:
    `publications.toml`'s `[site] unpublished`."""

    published_url: str = field(kw_only=True)
    """Where `site/published/` is served, which a live page's absolute links start with:
    `publications.toml`'s `[site] published`."""

    embed_assets: bool = False
    """Whether `report.html` carries its stylesheet and script rather than linking them.

    Linked by default, at `published_url`,
    so a fragment is 28 KB smaller and every publication shares one copy.
    A linked copy only exists once the site is pushed, though,
    so embedding is for a fragment to paste before then.
    """

    source_brackets: bool = False
    """Whether a cited link shows its `[n]` in the text where the device hovers.

    Off, the number is in the box hovering opens and in the Sources list,
    and not in the sentence, where a second numbering beside the footnotes' clutters it.
    """

    hosted_media: bool = True
    """Whether `report.html` links its images and videos where the site serves them.

    The fragment is pasted into Squarespace, which has no way to upload a
    folder of images and names each one it is given by a hash nobody can
    predict, so each would otherwise be uploaded by hand and its link copied
    back one at a time. Linked on the site instead, the files the build already
    wrote are the ones the page shows. Off, it links them relative to itself,
    for a page served beside its `images/`.
    """

    comments: bool = True
    """Whether to ask how many comment threads are open.

    The one expensive question a build asks: it is a text export of the whole
    document rather than an API call, and it costs more than fetching the
    document does. Left unasked, the last answer stands, the way it already
    does for the service account that cannot ask it at all.
    """


DOC_JSON = "doc.json"
IMAGES_JSON = "images.json"
"""The saved API response, written by every build beside its outputs."""


def load(
    ref: str,
    suggestions: str = "rejected",
    comments: bool = True,
    cached: Path | None = None,
) -> JsonObject:
    """Resolve a reference to the document it names.

    A saved response can be the file itself or the directory holding it,
    so whatever a previous run produced can be handed straight back
    without knowing the filename inside it.

    Which tab to read is part of the reference, as `?tab=` in the URL,
    which is the only way it can be named in `publications.toml`.
    """
    path = Path(ref)
    if path.is_dir():
        saved = path / DOC_JSON
        if not saved.is_file():
            raise FileNotFoundError(f"{path} holds no {DOC_JSON}; is it a publication directory?")
        return json.loads(saved.read_text())
    if path.is_file():
        return json.loads(path.read_text())

    return fetch(ref, suggestions=suggestions, comments=comments, cached=cached)


REVIEW_KEYS = ("openSuggestions", "openComments")
"""What the fetch records about the editing still open on a document.

Left out of the response entirely when the account could not read it,
which is not the same as there being none.
"""


def carry_over_review(document: JsonObject, saved: Path) -> None:
    """Keep the last answer about suggestions and comments where this run has none.

    Reading suggestions needs edit access,
    and reading comments needs an export the service account is refused,
    which is what rebuilds the site in CI.
    Without this it would write a page saying nothing is open,
    differ from the committed one, and fail the check that the two match
    over something no document changed.
    A stale count beats a wrong one.
    """
    previous: JsonObject = {}
    if saved.is_file():
        try:
            previous = json.loads(saved.read_text())
        except OSError, ValueError:
            previous = {}
    for key in REVIEW_KEYS:
        if key not in document and key in previous:
            document[key] = previous[key]


def carry_over(previous: Path, dest: Path, doc: Document) -> None:
    """Copy what the last build of this publication left that this one reads.

    A build writes into a directory of its own and reads the last one's,
    so nothing is read from a file it is halfway through rewriting,
    and nothing it no longer writes is left behind:
    an image taken out of the document is not carried over, and so is gone.

    The records, which say what no saved response can: what each image was
    written as, what the archive and each platform said. And the files they
    name, which are not committed and so are only on disk: the images, the
    downloaded SVGs this document still links, and the embeds' thumbnails and
    videos. Those are hard-linked rather than copied, which is 50 MB a build
    does not copy; every write to one goes through `replace_bytes`, which puts
    a new file in its place and leaves the last build's copy alone.
    The records are copied, since each is rewritten.

    Not the print copies, the PDF, or the outputs: every build writes those.
    """
    if previous.resolve() == dest.resolve():
        return
    dest.mkdir(parents=True, exist_ok=True)
    media: list[str] = []
    for record in (DOC_JSON, IMAGES_JSON, ARCHIVES_JSON, EMBEDS_JSON):
        if not (previous / record).is_file():
            continue
        shutil.copyfile(previous / record, dest / record)
        if record not in (IMAGES_JSON, EMBEDS_JSON):
            continue
        try:
            entries = json.loads((previous / record).read_text())
        except ValueError:
            continue
        files = [entry["file"] for entry in entries.values() if entry.get("file")]
        media += [f"{folder}/{name}" for name in files for folder in (IMAGE_DIR, VIDEO_DIR)]
    media += [f"{IMAGE_DIR}/{original_name(image)}" for image in doc.images if image.vector]
    # The copies a page shows, with the record of what each was made from:
    # `write_web_copies` keeps those still made from the same picture and
    # removes the rest, so carrying all of them costs nothing and saves encoding.
    web = previous / IMAGE_DIR / WEB_DIR
    if web.is_dir():
        media += [f"{IMAGE_DIR}/{WEB_DIR}/{copy.name}" for copy in web.iterdir()]
    for name in media:
        if (previous / name).is_file():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            link_or_copy(previous / name, dest / name)


def link_or_copy(source: Path, dest: Path) -> None:
    """`source` at `dest` as a second name for the same file, or a copy across filesystems."""
    dest.unlink(missing_ok=True)
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy2(source, dest)


def fragment_emitter(
    image_base: str,
    linked: str,
    pdf_href: str = "",
    source_brackets: bool = False,
    *,
    site_url: str,
) -> HtmlEmitter:
    """The emitter for `report.html`: linking its stylesheet and script at `linked`, if given,
    and carrying them otherwise."""
    return HtmlEmitter(
        image_base=image_base,
        inline_css=not linked,
        inline_js=not linked,
        asset_base=linked,
        pdf_href=pdf_href,
        source_brackets=source_brackets,
        site_url=site_url,
    )


def write_split(
    doc: Document,
    outdir: Path,
    image_base: str = IMAGE_DIR,
    linked: str = "",
    source_brackets: bool = False,
    stem: str = "report",
    *,
    site_url: str,
) -> list[Path]:
    """One file per piece, named so paste order is obvious."""
    emitter = fragment_emitter(
        image_base, linked, source_brackets=source_brackets, site_url=site_url
    )
    pieces = [emitter.join(emitter.wrapped(group)) for group in emitter.groups(doc)]
    written = []
    for n, piece in enumerate(pieces, start=1):
        dest = outdir / f"{stem}.part{n:02d}.html"
        dest.write_text(piece)
        written.append(dest)
    return written


def write_image_index(
    dest: Path, written: dict[str, Path], unpublished: dict[str, str] | None = None
) -> None:
    """Record what each image was written as, and what is in it.

    The images are not committed,
    so without this nothing says whether a rebuild fetched the same pictures.

    The filename is here because it cannot be derived:
    a Docs `inlineObject` says nothing about what kind of file it is,
    so `.jpg` or `.png` is learned by fetching.

    The pixel size is here because only the written file knows it:
    Docs says how large an image is placed, not how large it is,
    and the crop applied on the way down changes the shape of the file.
    The HTML lays a row of figures out by it,
    and a build without the images has to write the same page.

    Only written when images were downloaded:
    a `--no-images` build knows nothing about them
    and must not replace what a real build recorded.

    A download that turned up nothing is the same thing arrived at differently,
    and is why an empty result is refused rather than written.
    The caller only asks when the document has images,
    so nothing to record means none of them could be fetched,
    and recording that would erase the one file
    that says which pictures a complete build wrote.
    """
    if not written and (dest / IMAGES_JSON).exists():
        return
    index = {
        object_id: {
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **_pixel_size(path),
            **_description(path),
        }
        for object_id, path in sorted(written.items())
    }
    for object_id, why in (unpublished or {}).items():
        index[object_id] = {"unpublished": why}
    index = dict(sorted(index.items()))
    (dest / IMAGES_JSON).write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")


def _pixel_size(path: Path) -> dict[str, int]:
    """`path`'s width and height, or nothing for a file that has no pixels.

    An SVG has none: it is a drawing rather than a grid, and Pillow will not open one.
    Nothing else reads a size it did not get,
    so this stays a missing key rather than a guess.
    """
    try:
        with Pillow.open(path) as opened:
            return {"width": opened.width, "height": opened.height}
    except OSError, UnidentifiedImageError:
        return {}


def _description(path: Path) -> dict[str, str]:
    """What an SVG says it shows, as alt text, or nothing for any other file."""
    if path.suffix != ".svg":
        return {}
    alt = svg_description(path.read_bytes())
    return {"alt": alt} if alt else {}


def has_its_figures(dest: Path, doc: Document) -> bool:
    """Whether every figure's file is on disk under the name this build gives it.

    `has_its_images` asks the same of the names the last build wrote,
    which is not enough when the code now names an image differently:
    the old file is still there, the saved response is reused,
    and it has no `contentUri` to download the new name from.
    The extension is not known until the download, so any one will do.
    """
    images = dest / IMAGE_DIR
    return all(
        any(images.glob(f"{glob.escape(figure.image.filename)}.*"))
        for figure in doc.figures
        if figure.image.filename and not figure.image.vector
    )


def has_its_images(dest: Path) -> bool:
    """Whether the last build's image files are still beside its response.

    The images are not committed and the response is,
    so a fresh checkout has a saved response describing pictures that are not there.
    Reusing that response is what makes the build write a page with no images in it:
    a saved `contentUri` expires within the hour and so is never saved,
    which leaves the download nothing to fetch from
    and the emitters no filename to write.

    Asked of `images.json` rather than of the directory,
    because only the index says which files a complete build wrote.
    An index that is missing or unreadable is not evidence that anything is gone,
    so it reads as present and the build goes on to answer the question itself.
    """
    try:
        recorded = json.loads((dest / IMAGES_JSON).read_text())
    except OSError, ValueError:
        return True
    return all(
        (dest / IMAGE_DIR / entry["file"]).exists()
        for entry in recorded.values()
        if "file" in entry
    )


def read_image_index(dest: Path, doc: Document) -> None:
    """Tell `doc` what the last build's images were written as, and how large.

    Neither can be derived. A Docs `inlineObject` says nothing about what kind
    of file it is, so `.jpg` or `.png` is learned by fetching; Docs says how
    large an image is placed rather than how large it is, and the crop applied
    on the way down changes the shape of the file.

    The files are not committed and `images.json` is, which makes it the record
    of both. A build that downloads them learns it first-hand and this changes
    nothing; a build that skips the download has nothing else to go on, and
    `require_image_index` is why it can count on this being here.
    """
    index = dest / IMAGES_JSON
    if not index.exists():
        return
    for object_id, entry in json.loads(index.read_text()).items():
        if "file" in entry:
            doc.image_files.setdefault(object_id, entry["file"])
        if "width" in entry and "height" in entry:
            doc.image_shapes.setdefault(object_id, (entry["width"], entry["height"]))
        if "alt" in entry:
            doc.image_alts.setdefault(object_id, entry["alt"])
        if "unpublished" in entry:
            doc.unpublished.setdefault(object_id, entry["unpublished"])


def require_image_index(dest: Path, doc: Document) -> None:
    """Refuse to skip the download when nothing records what was downloaded.

    Skipping is for not fetching 18 MB again, not for building in the dark.
    Whatever is fetched stays on disk and `download` leaves it there,
    so the cost this avoids is paid once and never again,
    and one build that pays it leaves the `images.json` every later one reads.

    Without it there is no filename and no shape, and the page that comes out
    links every picture by a stem with no extension and lays the rows out
    differently from the page beside it in the repository.
    """
    if not (dest / IMAGES_JSON).exists():
        raise ValueError(
            f"no {IMAGES_JSON} here, so nothing says what this publication's "
            f"{len(doc.images)} images were written as; "
            "build it once with the download before building it without"
        )


OBJECT_PROPERTIES = {
    "inlineObjects": "inlineObjectProperties",
    "positionedObjects": "positionedObjectProperties",
}
"""Where each kind of embedded object keeps the object itself.

An image floating on the page and one sitting in the text
are the same `embeddedObject` reached by a different name.
Both carry a `contentUri`, so both have to be stripped of it,
including `positionedObjects`, which nothing reads yet.
"""


def without_content_uris(document: JsonObject) -> JsonObject:
    """The response as it is worth saving: no `contentUri` values.

    A `contentUri` is a signed URL that expires within the hour,
    so a saved one is dead on arrival and changes on every fetch,
    which made re-publishing an unedited document a diff in a committed file.

    The parser treats an inline object with `imageProperties` as an image
    whether or not a URI came with it,
    so everything but the download works from a saved response.
    """
    stripped = dict(document)
    for collection, properties in OBJECT_PROPERTIES.items():
        objects = document.get(collection)
        if not objects:
            continue
        stripped[collection] = {
            object_id: _without_uri(embedded, properties) for object_id, embedded in objects.items()
        }
    return stripped


def _without_uri(embedded_object: JsonObject, properties_key: str) -> JsonObject:
    properties = embedded_object.get(properties_key, {})
    embedded = properties.get("embeddedObject", {})
    if "imageProperties" not in embedded:
        return embedded_object
    image_properties = {k: v for k, v in embedded["imageProperties"].items() if k != "contentUri"}
    return {
        **embedded_object,
        properties_key: {
            **properties,
            "embeddedObject": {**embedded, "imageProperties": image_properties},
        },
    }


# The stylesheets and the script every publication page shares, and the formatter
# each is read by. Written once per build rather than into each page.
SHARED_ASSETS = (
    "page.css",
    "publication.css",
    "publication.js",
    # The pages' tab icon, as well as what a chart credited to ETA carries.
    "logo.svg",
)


def write_assets(siteroot: Path, doc: Document) -> list[Path]:
    """The one copy of what every publication page links.

    Written as they are; `format.tree` lays out and checks the whole build
    afterwards, these among the rest.
    """
    dest = siteroot / ASSET_DIR
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name in SHARED_ASSETS:
        path = dest / name
        path.write_text(read(name))
        written.append(path)
    written += write_posters(doc, dest)
    return written


def write_frames(doc: Document, dest: Path) -> None:
    """The first frame of each served video with no `Warning:`:
    what the page, the PDF, and the Markdown show of it until it plays.

    Made from the video on disk, so offline as well, and again only when the video is newer.
    A video not on disk has no frame, and its PDF is not built, as for a missing picture.
    """
    for embed in doc.embeds:
        file = doc.served_video(embed)
        if file is None or embed.warning:
            continue
        video = dest / VIDEO_DIR / file
        frame = dest / IMAGE_DIR / video_frame_name(file)
        if not video.exists() or (
            frame.exists() and frame.stat().st_mtime >= video.stat().st_mtime
        ):
            continue
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            doc.warn(
                "{} is not on PATH, so {} has no frame for the PDF", Shown("ffmpeg"), Shown(file)
            )
            return
        frame.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(frame),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            doc.warn(
                "{} could not take a frame from {}: {}",
                Shown("ffmpeg"),
                Shown(file),
                result.stderr.strip(),
            )


def write_posters(doc: Document, dest: Path) -> list[Path]:
    """What each kind of warning this publication's videos carry shows before its video does.

    Made from the logo rather than kept, so an edit to the logo reaches them.
    Into the site's assets for the page, and beside the print copies for the PDF,
    which can only read what is under the publication.
    """
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for kind in sorted({embed.warning_kind for embed in doc.embeds if embed.warning}):
        path = dest / warning_poster_name(kind)
        path.write_text(warning_poster(LOGO.read_text(), kind))
        written.append(path)
    return written


def asset_base(path: str) -> str:
    """`ASSET_DIR` as seen from a publication at `path`, which says how deep it is.

    Relative rather than rooted at `/`, because the site is served from
    wherever Pages puts it and a publication's own `URL:` decides its depth.
    """
    return "/".join([".."] * len(PurePosixPath(path).parts) + [ASSET_DIR])


UNWARNED = "published"
"""What names a live publication's outputs as `site/published/` takes them,
as `report.published.html`: linking the published host, and without the warnings."""


def pdf_name(stem: str) -> str:
    """What `typst` compiles `<kind>.typ` to, beside it, for the outputs named `stem`.

    The preview's name for the published copies too: `report.published.pdf`
    is served in `site/published/` as the `report.pdf` its page links.
    """
    return f"{stem.partition('.')[0]}.pdf"


def media_base(path: str, site_url: str) -> str:
    """Where the site serves the images of the publication at `path`, as a URL."""
    return f"{site_url}/{path}/{IMAGE_DIR}"


def emit(
    doc: Document,
    outdir: Path,
    assets: str = ASSET_DIR,
    images: str = IMAGE_DIR,
    linked: str = "",
    pdf: str = "",
    cards: str = "",
    url: str = "",
    source_brackets: bool = False,
    stem: str = "report",
    page_url: str = "",
    *,
    site_url: str,
) -> dict[str, Path]:
    """Run each emitter,
    reporting the ones not yet implemented rather than failing the whole build for them.

    `pdf` is where `report.html` links the PDF: the site's copy, since the fragment
    is pasted into Squarespace, which does not serve it. `index.html` links its neighbor.
    `cards` is where the site serves the images, for the share card's absolute URL,
    and `url` is where it serves this publication, for `og:url`.
    `page_url` is the live page, for the PDF to link its videos' figures on.
    A `stem` that is more than the kind, `report.published`,
    writes only the files `site/published/` takes, so not `index.html`, which is the preview.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    emitters = {
        f"{stem}.html": fragment_emitter(images, linked, pdf, source_brackets, site_url=site_url),
        f"{stem}.md": MarkdownEmitter(),
        f"{stem}.typ": TypstEmitter(site_url=site_url, page_url=page_url),
    }
    written: dict[str, Path] = {}
    if "." in stem:
        return _emit_each(doc, outdir, emitters, written)
    # `index.html`, so a publication directory is a page at its own URL:
    # `/reports/<slug>/` serves the publication rather than a listing of files.
    # `report.html` or `statement.html` beside it is the fragment,
    # a piece of a page rather than one.
    page = outdir / "index.html"
    page.write_text(
        publication_page(
            doc,
            asset_base=assets,
            pdf_href=pdf_name(stem),
            card_base=cards,
            page_url=url,
            source_brackets=source_brackets,
            site_url=site_url,
        )
    )
    written[page.name] = page
    return _emit_each(doc, outdir, emitters, written)


def _emit_each(
    doc: Document,
    outdir: Path,
    emitters: dict[str, HtmlEmitter | MarkdownEmitter | TypstEmitter],
    written: dict[str, Path],
) -> dict[str, Path]:
    """Run each emitter into `outdir`, adding what it wrote to `written`."""
    for name, emitter in emitters.items():
        try:
            source = emitter.emit(doc)
        except NotImplementedError as e:
            console.write(console.note("skipped {}: not implemented ({})", Shown(name), str(e)))
            continue
        dest = outdir / name
        dest.write_text(source)
        written[name] = dest
    return written


ANONYMOUS_WARNED = threading.Event()
"""Set once the run has said it is capturing anonymously, to say it again at the end."""


def anonymous_warning() -> RenderableType:
    """What capturing without keys costs, and how not to."""
    return console.alarm(
        "Capturing sources WITHOUT archive.org keys",
        "No archive.org keys were found, so new captures are asked for anonymously:\n"
        "  • slow: one every {} seconds, so a dozen new sources is minutes\n"
        "  • rate-limited much harder: builds stop more often and need rerunning\n"
        "  • vaguer: a failed capture says less about why\n"
        "  • never done in CI, where those sources stay unarchived\n"
        "\n"
        "To use an account, set {} and {} from {},\n"
        "or run {} (or point {} at its {}).",
        str(int(ANONYMOUS_EVERY.total_seconds())),
        Shown(f"${ACCESS_KEY}"),
        Shown(f"${SECRET_KEY}"),
        console.Linked(KEYS_PAGE),
        Shown("ia configure"),
        Shown(f"${IA_CONFIG}"),
        Shown("ia.ini"),
    )


def warn_anonymous() -> None:
    """Say, once a run however many publications it builds, what capturing without keys costs.

    Again after the summary, from `__main__`: said while the first publication with a
    new source was building, it scrolls away under every publication after it.
    """
    with _WARNING_ANONYMOUS:
        if ANONYMOUS_WARNED.is_set():
            return
        ANONYMOUS_WARNED.set()
    console.write(anonymous_warning())


_WARNING_ANONYMOUS = threading.Lock()


def counted_pages(doc: Document, only: set[str] | None = None) -> None:
    """Count the pages of the PDFs cited by page, saying which are being downloaded."""
    wanted = [url for url in uncounted(doc) if only is None or url in only]
    if not wanted:
        return
    console.step("counting the pages of cited PDFs")
    with (
        console.progress("counting PDF pages", len(wanted)) as along,
        console.watching() as rows,
    ):
        count_pages(doc, only=set(wanted), rows=rows, along=along)


def archive_sources(doc: Document) -> None:
    """Find or make a capture of every source nothing has one for yet.

    Part of an ordinary build rather than a step somebody remembers to run: a
    source is archived because it was cited, and the moment it was cited is
    this one. Captured later, the snapshot is of whatever the page said later,
    which is not what the publication read.

    Only what is missing, so the cost is a handful of lookups on the build
    after a draft gains a link, and the whole of a publication's sources only on the
    first build that asks.

    Every one of them is asked of the replay, which is half a second and is what
    finds a capture somebody else has just made. What a build without keys skips,
    for a week, is the index query that confirms there is none: that one is slow,
    and nothing is written down for it either way.

    Asking what the Wayback Machine already holds needs no account, and most of
    what these publications cite is already in it. That half runs on every build.
    Asking for a new capture needs keys, and without them the sources nothing
    has captured are left as they are, to be asked for by a build that can.
    """
    wanted = missing(doc)
    if not wanted:
        return
    if not have_keys() and anonymous_allowed():
        warn_anonymous()
    console.write(console.note(f"looking up {plural(len(wanted), 'source')} in the archive"))
    with (
        console.progress("checking the archive", len(wanted)) as along,
        console.watching() as rows,
    ):
        found, submitted = capture(doc, along=along, rows=rows)
    # A list of clauses and the values in them, joined once at the end: a
    # value is handed to the log as the value it is, so a clause is a template
    # and its values rather than a finished string.
    said: list[tuple[str, tuple[Span | console.Linked, ...]]] = [
        (f"{plural(found, 'source')} already archived", ())
    ]
    if submitted:
        said.append((f"{plural(submitted, 'source')} captured", ()))
    left = len(missing(doc))
    if left and not have_keys():
        said.append(
            (
                f"{left} not archived and no keys to ask for a capture; "
                "set {} and {} from {}",
                (Shown(f"${ACCESS_KEY}"), Shown(f"${SECRET_KEY}"), console.Linked(KEYS_PAGE)),
            )
        )
    elif left:
        said.append((f"{left} could not be captured", ()))
    console.write(
        console.note(
            "; ".join(template for template, _ in said),
            *(value for _, values in said for value in values),
        )
    )


def check_code_block_size(doc: Document, publication: Path) -> None:
    """Say something before a paste fails, not after.

    Asked once the tree has been formatted, because that is what the file
    will be when it is pasted: laying it out adds around an eighth to it,
    and a limit checked against the bytes before that is not the limit.
    """
    size = publication.stat().st_size
    if size > CODE_BLOCK_LIMIT:
        doc.warn(
            f"{publication.name} is {size:,} bytes, over Squarespace's "
            f"{CODE_BLOCK_LIMIT:,} byte code block limit; "
            "split it at h2 boundaries with {}",
            Shown("--split"),
        )
    elif size > CODE_BLOCK_WARN:
        doc.warn(
            f"{publication.name} is {size:,} bytes, within Squarespace's "
            f"{CODE_BLOCK_LIMIT:,} byte limit but large enough that the editor "
            "may be slow to save it"
        )


def build_pdf(source: Path, outdir: Path, skipped_images: bool) -> Path | None:
    """Compile the publication PDF, reporting rather than failing the whole build.

    The `.typ` is written either way,
    so a missing `typst` or a compile error costs the PDF and nothing else.
    """
    if skipped_images:
        console.write(
            console.note(
                "skipping the PDF because images were not downloaded; "
                "Typst embeds them from disk, so it needs the real files"
            ),
        )
        return None

    install_template(outdir)
    try:
        return compile_pdf(source)
    except TypstMissing:
        # Said here rather than raised with the exception: the exception is
        # control flow, and a sentence with a command and a URL in it is
        # written where the values in it can be handed over as values.
        console.write(
            console.note(
                "{} is not on PATH, so the PDF was not built. Install it with {} "
                "or from {}, then rerun. The {} source has already been written.",
                Shown("typst"),
                Shown("mise use -g typst"),
                console.Linked("https://typst.app/"),
                Shown(".typ"),
            )
        )
    except RuntimeError as e:
        # `typst`'s own diagnostics, verbatim: what it quotes out of the source
        # it was compiling is not this codebase's prose to pick values out of.
        console.write(console.warning("{}", str(e)))
    return None


def write_outputs(
    doc: Document,
    dest: Path,
    path: str,
    options: BuildOptions,
    site_url: str,
    stem: str,
    skipped_images: bool,
    page_url: str = "",
) -> None:
    """Write the publication's outputs as `stem.*`, linking the site at `site_url`, and its PDF.

    Twice for a publication that is published: as `report.*` for the preview, linking the preview's
    host, and as `report.published.*` for `site/published/`, linking the published host,
    or `statement.*` and `statement.published.*` for a statement,
    and without the warnings, which are for whoever reviews a build and never for a reader.
    """
    images = media_base(path, site_url) if options.hosted_media else IMAGE_DIR
    linked = "" if options.embed_assets else f"{site_url}/{ASSET_DIR}"
    pdf = f"{site_url}/{path}/{pdf_name(stem)}" if options.hosted_media else pdf_name(stem)
    written = emit(
        doc,
        dest,
        asset_base(path),
        images,
        linked,
        pdf,
        media_base(path, site_url),
        f"{site_url}/{path}/",
        options.source_brackets,
        stem=stem,
        site_url=site_url,
        page_url=page_url,
    )
    typ = written.get(f"{stem}.typ")
    if typ is not None:
        console.step("compiling the PDF")
        build_pdf(typ, dest, skipped_images)
    if options.split:
        write_split(
            doc, dest, images, linked, options.source_brackets, stem=stem, site_url=site_url
        )


def build_one(
    ref: str,
    outdir: Path,
    options: BuildOptions,
    verify: Callable[[Document], None] | None = None,
    cached: Path | None = None,
    previous: Path | None = None,
    read_from: Path | None = None,
    publishes: bool = False,
) -> tuple[Document, str]:
    """Build one publication, returning it and the site-relative path it went to.

    `publishes` is a publication out on a live page this build writes,
    which writes its outputs a second time for `site/published/`.

    The whole per-document order of operations lives here, and only here.

    Where a publication goes comes from its own front matter, inside the document,
    so the destination is unknown until the document has been read.
    That is why the response is not written on the way in:
    it is saved into the publication's directory afterwards,
    whether it came from the API or from a previous build.

    `verify` is the caller's chance to say this is not the document it meant,
    given the parsed document and called before anything is written.

    `cached` is the response the last build of this publication saved, if there is one.
    It is not read unless Drive says the document has not been edited since,
    which is a cheaper question than any of the ones it saves asking.

    `previous` is the directory the last build of this publication wrote, if it
    was not this one: what it recorded is carried over before anything reads it.
    Without one, it is the publication's own path under `read_from`, the last site.
    """
    console.step("reading the saved response" if options.offline else "fetching the document")
    document = load(ref, options.suggestions, options.comments, cached)
    console.step("parsing")
    doc = parse(document)
    if verify is not None:
        # Before the first directory is made,
        # so a wrong answer leaves no publication's worth of files behind.
        verify(doc)
    path = publication_path(doc)
    # Refused here as well as checked against an entry:
    # a document named on the command line has no entry to check it.
    kind = publication_kind(doc)
    dest = outdir / path
    if previous is None and read_from is not None:
        previous = read_from / path
    if previous is not None and previous.is_dir():
        carry_over(previous, dest, doc)
    # Only a reused response: a fetched one has the URIs to download from.
    reused = cached is not None and '"contentUri"' not in json.dumps(document)
    # A figure downloaded from its own source is still checked against the document's copy,
    # which only a response with the URIs can download.
    checks_live = any(image.live_uri for image in doc.images)
    if (
        reused
        and options.images
        and not options.offline
        and (checks_live or not has_its_figures(dest, doc))
    ):
        console.step("fetching the document again for its images")
        document = load(ref, options.suggestions, options.comments)
        doc = parse(document)
        if verify is not None:
            verify(doc)
    dest.mkdir(parents=True, exist_ok=True)

    # Before the checks, which warn about what it says,
    # and before the response is written, which is what the next build reads.
    carry_over_review(document, dest / DOC_JSON)
    read_review(doc, document)
    check(doc)
    check_kind(doc)
    style(doc)

    # Sorted, as `images.json` is: this file is committed and compared against
    # a fresh build, so any two runs that agree about the document have to
    # write the same bytes, which insertion order does not promise.
    (dest / DOC_JSON).write_text(
        json.dumps(without_content_uris(document), indent=2, sort_keys=True)
    )

    if doc.images:
        if options.images:
            console.step("reusing the images" if options.offline else "downloading the images")
            written_images = download(doc, dest / IMAGE_DIR, offline=options.offline)
            write_image_index(dest, written_images, doc.unpublished)
            # Not recorded in `images.json`: that file is committed, and a
            # JPEG encoder is not byte-stable between versions, so a Pillow
            # release would break the committed-site check months later
            # over pictures nothing publishes.
            console.step("encoding the images for print")
            write_print_copies(written_images, dest / PRINT_DIR)
            console.step("encoding the images for the page")
            write_web_copies(written_images, dest / IMAGE_DIR)
        else:
            require_image_index(dest, doc)
    read_image_index(dest, doc)
    check_described(doc)

    # Every build, embeds or none, so a publication that loses its last one loses
    # its record too. Only what is missing is asked about, so the cost after
    # the first build is nothing; offline, the record is all there is.
    read_embed_index(dest, doc)
    if not options.offline:
        console.step("looking up embeds")
        look_up(doc)
        if options.images:
            download_embeds(doc, dest)
    write_frames(doc, dest)
    write_captions(doc, dest)
    write_embed_index(dest, doc)
    check_embeds(doc)

    # After the document is parsed, because what it cites is what it cites,
    # and before the emitters, which write the Sources section off it.
    read_archive_index(dest, doc)
    if options.archive and not options.offline:
        # Before the lookups as well as after, because counting is what finds a
        # recorded capture that is not the PDF, and dropping it is what has
        # this build's lookups find one that is.
        tried = set(uncounted(doc))
        counted_pages(doc)
        console.step("checking the archive")
        archive_sources(doc)
        counted_pages(doc, only=set(uncounted(doc)) - tried)
    write_archive_index(dest, doc)
    # After the record is read, because the page counts it checks against are in it.
    check_pages(doc)
    check_pending(doc)

    # Written here rather than once per site, so that building a single
    # publication produces a page with everything it links.
    write_assets(outdir, doc)
    write_posters(doc, dest / PRINT_DIR)
    console.step("writing the outputs")
    skipped_images = not options.images and bool(doc.images)
    write_outputs(doc, dest, path, options, options.unpublished_url, kind, skipped_images)
    for stale in dest.glob(f"{kind}.{UNWARNED}.*"):
        # From a build that published it, which this one may not.
        stale.unlink()
    if publishes:
        console.step("writing the outputs to publish")
        write_outputs(
            replace(doc, warnings=[]),
            dest,
            path,
            options,
            options.published_url,
            f"{kind}.{UNWARNED}",
            skipped_images,
            f"{LIVE_SITE}{doc.slug}" if doc.slug else "",
        )

    return doc, path
