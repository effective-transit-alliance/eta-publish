"""What a build makes from the pictures and a later one reuses, kept by what it is made from.

What the image index finds in each picture, each picture's copies for the page and for the PDF,
and the PDFs, in the `CacheKind` folders under `build_cache_dir`:
one file each, named by a hash of everything it is made from,
its sources' bytes and what made it (the versions of Pillow and the libraries it encodes with,
or of `typst`, what it is encoded at, and a hash of the code that makes it).
So a file found under the name a build would give it is what that build would make,
whichever build made it: this one's last, another publication's, or the drafts'.

A build links each into its own directory, or copies it across filesystems,
and makes only what it finds no file for.
Nothing in here is ever rewritten: every file is put in place whole, as a new file,
so a build reading one while another writes it reads the old file or the new, never half of one,
and a link in a build's directory keeps what it was linked to.

Each file says when it was last used by its modification time,
which every build that uses it sets,
and `prune_build_cache` removes the files no build has used for `UNUSED_LIFETIME`.
Not anything a build didn't use: another build may be using it.

Never committed, and not a record of anything:
a build with none of it makes the same bytes, only more slowly.
"""

from datetime import timedelta
from hashlib import sha256
from os import environ, link, replace, utime
from pathlib import Path
from secrets import token_hex
from time import time
from typing import Literal, get_args

from platformdirs import user_cache_path

from . import PACKAGE_NAME
from .naming import link_or_copy, replace_bytes

BUILD_CACHE = "ETA_BUILD_CACHE"
"""Where `build_cache_dir` is instead, if set: for the tests, which each start with none of it.

It stands in for the whole of `~/.cache/eta-publish`, the folders' parent,
though only the `CacheKind` folders are looked for in it:
not `fonts/`, `archive.json`, or `logo.json`, which are found where they always are,
or for the archive lookups where `archive.ARCHIVE_CACHE` says.
"""

CacheKind = Literal["images/found", "images/web", "images/print", "pdfs"]
"""The folders under `build_cache_dir` the files are kept in, one for each kind of file.

The only folders `prune_build_cache` looks in, since the rest of the cache is not what builds make:
`fonts/`, `archive.json`, and `logo.json` are kept by rules of their own.
"""

UNUSED_LIFETIME = timedelta(days=7)
"""How long a file no build uses is kept.

A week, as the archive lookups' answers are kept,
and as GitHub keeps a cache no run restores, so CI never keeps one longer.
Every build uses all of what its publications make, so this is only what a build no longer makes:
a picture replaced or taken out, a PDF compiled from what changed since,
and what a branch made that nothing has built for a week.
"""


def build_cache_dir() -> Path:
    """Where the `CacheKind` folders are: the cache, as `fonts.font_dir` is in it.

    Read on each call rather than resolved once, so a test can point it somewhere else.
    """
    override = environ.get(BUILD_CACHE)
    if override:
        return Path(override)
    return user_cache_path(PACKAGE_NAME)


def cached_path(kind: CacheKind, key: str, suffix: str) -> Path:
    """Where the file of `kind` made from what `key` says is kept, ending in `suffix`.

    `key` is everything it is made from, so two files with the same key are interchangeable.
    """
    return build_cache_dir() / kind / f"{sha256(key.encode()).hexdigest()}{suffix}"


def link_cached(kept: Path, dest: Path) -> bool:
    """Link `kept` at `dest`, saying it was used, if it is there; whether it was.

    Not there because nothing made it yet, or because `prune_build_cache` removed it just now.
    """
    try:
        utime(kept)
        dest.parent.mkdir(parents=True, exist_ok=True)
        link_or_copy(kept, dest)
    except FileNotFoundError:
        return False
    return True


def read_cached(kept: Path) -> bytes | None:
    """What `kept` holds, saying it was used, or `None` if it is not there."""
    try:
        utime(kept)
        return kept.read_bytes()
    except FileNotFoundError:
        return None


def cache_bytes(kept: Path, data: bytes) -> None:
    """Keep `data` as `kept`, for every build after."""
    replace_bytes(kept, data)


def cache_file(kept: Path, source: Path) -> None:
    """Keep `source` as `kept`, linked rather than copied where it can be.

    So `source` must never be rewritten either, only replaced, as everything a build writes is.
    """
    kept.parent.mkdir(parents=True, exist_ok=True)
    # Linked at a name of its own first, then put in place, as `replace_bytes` puts a file.
    temporary = kept.with_name(f".{kept.name}.{token_hex(8)}")
    try:
        link(source, temporary)
    except OSError:
        replace_bytes(kept, source.read_bytes())
        return
    try:
        replace(temporary, kept)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def prune_build_cache() -> None:
    """Remove every file in the `CacheKind` folders no build has used for `UNUSED_LIFETIME`.

    Also what a build stopped partway left of a file it was putting in place.
    A file removed as a build reaches for it is one that build makes again.
    Nothing else in the cache, though it is the same directory.
    """
    cutoff = time() - UNUSED_LIFETIME.total_seconds()
    for kind in get_args(CacheKind):
        folder = build_cache_dir() / kind
        if not folder.is_dir():
            continue
        for kept in folder.iterdir():
            try:
                if kept.stat().st_mtime < cutoff:
                    kept.unlink()
            except FileNotFoundError:
                continue
