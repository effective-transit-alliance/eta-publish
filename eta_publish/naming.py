"""Deterministic names for things that become published URLs.

Heading anchors and image filenames both end up in URLs
that outlive any one regeneration.
If either moves because something unrelated changed elsewhere,
links from outside rot and the committed Markdown fills with diff noise.

So both derive from the content they name, never from position.
"""

import hashlib
import os
import re
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pymdownx.slugs import slugify as _slugify

ASSET_DIR = "assets"
"""The directory the shared stylesheets and script go in, at the site root.

Every report page links one copy rather than carrying its own.
"""

SITE = "https://kkysen.github.io/eta-publish"
"""Where the built site is served, with no trailing slash.

Only the PDF needs this. Every other output links within itself
and so says nothing about where it is hosted,
but a PDF is read away from the site it came from:
a link in it has to name the host or name nothing.

One constant rather than an option, because `report.typ` is committed
and `check-committed-site.sh` refuses a build that differs from it:
a base that varied per run would make the committed file depend on
who ran the build. This is the preview host, and it changes when the
reports are published somewhere else.
"""

IMAGE_DIR = "images"
"""The directory a build writes images into, relative to the report.

Serving them from somewhere else is an emitter's `image_base`,
which is a decision about hosting rather than about a build.
"""

VIDEO_DIR = "videos"
"""The directory a build writes the videos it serves itself into, beside `IMAGE_DIR`.

Separate because a video is a different order of size,
and a glance at the directory should say where the space went.
"""

PRINT_DIR = "print"
"""The directory the PDF's copies of the images go in, beside `IMAGE_DIR`.

Two copies rather than one because they answer different questions.
`images/` is the picture as the document holds it, which is what the page
serves and what the PDF links out to. `print/` is that picture re-encoded to
fit in a PDF a host will accept, which costs resolution and costs detail,
and is not a thing to serve as the image.

Kept rather than built in a temporary directory,
so the `report.typ` published beside the PDF compiles as it stands:
it names these files, and serving source that cannot compile
is the thing the workflow keeps `template.typ` around to avoid.
"""


def print_href(href: str) -> str:
    """What `href` is called in `PRINT_DIR`.

    A raster becomes a JPEG and says so, because Typst reads the format off
    the extension: a JPEG called `.png` is a compile error, not a picture.

    A vector is copied under its own name. There is nothing to re-encode,
    it is already the smallest it can be, and rasterizing a diagram to save
    bytes would cost the one format that stays sharp at any size.

    Safe against collision because the extension is not part of what makes a
    name unique: `image_filenames` allocates over names with the extension
    stripped, and the real one is appended once the download settles it,
    so two images cannot differ only in extension.
    """
    stem, _, extension = href.rpartition(".")
    return href if extension.lower() == "svg" else f"{stem}.jpg"


# GitHub's rule for a heading anchor, from `pymdown-extensions` rather than
# rewritten here: a second copy agrees until a heading has an accent in it,
# and then whichever copy is wrong is wrong in published URLs.
#
# `github-slugger`, the dedicated PyPI port, cannot be imported on a current Python:
# it carries the JavaScript regex as lone surrogates, a `UnicodeEncodeError` on import.
_github_slug = _slugify(case="lower")


def slugify(text: str) -> str:
    """`text` as a heading anchor, by the rule Markdown uses for one.

    The same report publishes as HTML and as Markdown,
    and a link to a section must mean the same in both,
    so the rule is not ours to choose:
    lowercase, punctuation dropped, `-` and `_` kept, one hyphen per space,
    non-ASCII letters left alone. That is what GitHub renders an anchor as.

    Not the rule a filename gets:
    a heading is a sentence, and a filename is a name somebody chose,
    which `_ascii_name` keeps.
    """
    return _github_slug(text, "-") or "section"


# What a filename may keep: a dot is as much a part of a name as a letter,
# and `-` and `_` are what people join names with.
_NON_FILENAME = re.compile(r"[^\w.-]")
# A source line's extension names the format rather than the picture,
# and the one that publishes is whatever the download fetches,
# so it is dropped and the real one appended.
_ASSET_EXTENSIONS = frozenset(
    {"jpg", "jpeg", "png", "gif", "webp", "svg", "pdf", "tif", "tiff", "heic"}
)


def _ascii_name(name: str) -> str:
    """A filename as close to `name` as a URL can carry it.

    Every character that cannot appear becomes one underscore, and nothing else moves:
    runs are not collapsed, case is not folded, and a dot stays where it was.
    `SAS West - Tunnel Profile - pg 18.screenshot`
    publishes under a name its author would recognize,
    which is the whole reason for reading the source line.
    """
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode().strip()
    stem, dot, extension = name.rpartition(".")
    if dot and extension.lower() in _ASSET_EXTENSIONS:
        name = stem
    return _NON_FILENAME.sub("_", name)


class AnchorAllocator:
    """Assigns heading anchors that depend only on the heading's own text.

    Two-pass on purpose.
    Handing the bare slug to whichever heading claims it first and suffixing the rest
    is still positional:
    if two headings slugify alike and their order changes between drafts,
    both anchors move.
    So the constructor takes every heading text up front,
    works out which base slugs more than one distinct heading would claim,
    and suffixes *all* claimants of those.

    `overrides` maps heading text to an explicit anchor,
    for headings whose published URL already exists and must not change.

    `reserved` holds ids the emitters generate themselves, such as `footnotes`,
    which a heading titled "Footnotes" would otherwise collide with.
    """

    def __init__(
        self,
        heading_texts: Iterable[str] = (),
        overrides: dict[str, str] | None = None,
        reserved: Iterable[str] = (),
    ) -> None:
        self.overrides = overrides or {}
        self.reserved = frozenset(reserved)
        claimants: dict[str, set[str]] = defaultdict(set)
        for text in heading_texts:
            if text not in self.overrides:
                claimants[slugify(text)].add(text)
        self._ambiguous = {base for base, texts in claimants.items() if len(texts) > 1}

    def allocate(self, text: str) -> str:
        if text in self.overrides:
            return self.overrides[text]
        base = slugify(text)
        if base in self._ambiguous or base in self.reserved:
            return f"{base}-{_short_hash(text)}"
        return base


def content_anchor(prefix: str, text: str) -> str:
    """An id for a block that has no name of its own, from what it says.

    Hashing what the block says rather than counting where it sits
    is the difference between two failures.
    Numbering means inserting a paragraph
    silently repoints every link after it in that section at the wrong text.
    Hashing means editing a paragraph breaks links to that paragraph,
    loudly, and to nothing else.
    """
    return f"{prefix}-{_short_hash(text)}"


UNNAMED_PREFIX = "img-"
"""What an image is called when the document did not say what it is.

A name of its own comes from a `Source:` line; without one there is nothing
to use but a hash of the object id, and the prefix is what says so.

Not a test for one: a `Source:` line may itself name `img-something.jpg`,
which is a named image whose name happens to start this way.
`names_nothing` is the question worth asking.
"""


def names_nothing(name: str) -> bool:
    """Whether `name` leaves nothing to name a file with.

    The empty string, and anything that survives `_ascii_name` as only
    separators. `Image Source` and `SVG: TODO` are `Source:` lines
    that name no file, and an image under one is as unnamed as an image under none.
    """
    return not _ascii_name(name).strip("_.-")


def url_filename(url: str) -> str:
    """The file a URL names, or nothing if its path ends in no image file.

    The last segment of the path, decoded, and then its last segment again,
    because an image CDN often carries the original's whole URL as that segment:
    Substack's `fetch/.../https%3A%2F%2F...%2Ff4648f0c_650x862.png`.
    Only a segment ending in an image extension is a name:
    `photo_download.gne` is the page Flickr serves a download from,
    and a path of hashes with no extension names nothing anyone wrote.
    """
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if not segments:
        return ""
    name = unquote(segments[-1]).rsplit("/", 1)[-1]
    _, dot, extension = name.rpartition(".")
    return name if dot and extension.lower() in _ASSET_EXTENSIONS else ""


def media_stem(name: str) -> str:
    """A file stem for a video named `name`, or nothing if it names nothing."""
    return "" if names_nothing(name) else _ascii_name(name)


def image_filename(object_id: str, extension: str = "", crop_key: str = "", name: str = "") -> str:
    """Name an image after the file the document says it came from.

    A `Source:` line is the document saying which file this is,
    which makes it usable as a name where a caption is not.
    Editing a source line does move a published URL,
    which is the cost of readable names.

    An image with no source line is named for its Docs object id, hashed,
    which is stable across edits, so inserting an image cannot rename its neighbours.

    A named image that is cropped carries the hash too:
    recropping produces a different published image,
    and it would otherwise keep the old name and the old cached file.
    That is also what tells two crops of one source file apart.

    The extension is filled in once the download settles the real content type.
    """
    base = _ascii_name(name)
    if names_nothing(name):
        return f"{UNNAMED_PREFIX}{_short_hash(object_id + crop_key)}{extension}"
    if crop_key:
        base = f"{base}-{_short_hash(object_id + crop_key)}"
    return f"{base}{extension}"


def image_filenames(claims: Iterable[tuple[str, str, str]]) -> dict[str, str]:
    """A filename for each image, given every claim in the document.

    A claim is an object id, a crop key, and the name the document gave the image,
    empty for the images it named nothing.
    Allocated knowing all of them for the reason `AnchorAllocator` is:
    two images whose source lines name the same file
    would otherwise be told apart by which came first,
    and reordering the report would move a published URL.

    So both keep the name and carry the hash too,
    the same way a crop is told from its original.
    """
    claims = list(claims)
    claimants: dict[str, set[str]] = defaultdict(set)
    for object_id, crop_key, name in claims:
        claimants[image_filename(object_id, crop_key=crop_key, name=name)].add(object_id)
    ambiguous = {base for base, ids in claimants.items() if len(ids) > 1}

    names: dict[str, str] = {}
    for object_id, crop_key, name in claims:
        plain = image_filename(object_id, crop_key=crop_key, name=name)
        # The two images claim to be the same file,
        # so only the hash can tell them apart.
        names[object_id] = (
            image_filename(object_id, crop_key=crop_key or object_id, name=name)
            if plain in ambiguous
            else plain
        )
    return names


def _short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def replace_bytes(path: Path, data: bytes) -> None:
    """Write `data` as `path` by putting a new file in its place, never by rewriting it.

    A build links the last build's images and videos into its own directory
    rather than copying them. Rewritten in place, a linked file would change
    the last build's copy too, which is the committed site when a test builds
    beside it. Replaced, the last build keeps its own.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as written:
            written.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
