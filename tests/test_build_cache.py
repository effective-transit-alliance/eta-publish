"""What a build makes from the pictures, kept in the cache for every build after."""

from os import utime
from pathlib import Path
from time import time

import pytest

from eta_publish.build import FOUND_KIND
from eta_publish.build_cache import (
    BUILD_CACHE,
    UNUSED_LIFETIME,
    build_cache_dir,
    cache_bytes,
    cache_file,
    cached_path,
    link_cached,
    prune_build_cache,
)
from eta_publish.images import PRINT_KIND, WEB_KIND
from eta_publish.pdf import PDF_KIND

LONG_AGO = time() - UNUSED_LIFETIME.total_seconds() - 60


def test_a_file_is_kept_by_its_key_and_kind() -> None:
    assert cached_path(WEB_KIND, "a key", ".avif") == cached_path(WEB_KIND, "a key", ".avif")
    assert cached_path(WEB_KIND, "a key", ".avif") != cached_path(WEB_KIND, "another key", ".avif")
    assert cached_path(WEB_KIND, "a key", ".avif").parent == build_cache_dir() / "images" / "web"


def test_using_a_file_links_it_and_says_it_was_used(tmp_path: Path) -> None:
    kept = cached_path(WEB_KIND, "a key", ".avif")
    cache_bytes(kept, b"encoded")
    utime(kept, (LONG_AGO, LONG_AGO))
    dest = tmp_path / "images" / "web" / "photo-800w.avif"

    assert link_cached(kept, dest)

    assert dest.stat().st_ino == kept.stat().st_ino
    assert kept.stat().st_mtime > LONG_AGO + 60


def test_a_file_not_kept_is_not_used(tmp_path: Path) -> None:
    dest = tmp_path / "photo-800w.avif"
    assert not link_cached(cached_path(WEB_KIND, "never made", ".avif"), dest)
    assert not dest.exists()


def test_keeping_a_file_links_it_and_keeping_another_leaves_the_link_alone(
    tmp_path: Path,
) -> None:
    """Put in place as a new file, so what a build linked keeps what it was."""
    compiled = tmp_path / "report.pdf"
    compiled.write_bytes(b"%PDF the first")
    kept = cached_path(PDF_KIND, "a key", ".pdf")
    cache_file(kept, compiled)
    assert kept.stat().st_ino == compiled.stat().st_ino

    cache_bytes(kept, b"%PDF the second")

    assert compiled.read_bytes() == b"%PDF the first"
    assert kept.read_bytes() == b"%PDF the second"


def test_pruning_removes_only_what_no_build_used_for_the_lifetime() -> None:
    old = cached_path(PRINT_KIND, "old", ".jpg")
    recent = cached_path(PRINT_KIND, "recent", ".jpg")
    stopped = build_cache_dir() / PRINT_KIND / ".abc.jpg.0123456789abcdef"
    for path in (old, recent, stopped):
        cache_bytes(path, b"encoded")
    for path in (old, stopped):
        utime(path, (LONG_AGO, LONG_AGO))

    prune_build_cache()

    assert [p.name for p in (build_cache_dir() / PRINT_KIND).iterdir()] == [recent.name]


def test_pruning_nothing_kept_does_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BUILD_CACHE, str(tmp_path / "absent"))
    prune_build_cache()
    assert not (tmp_path / "absent").exists()


def test_pruning_leaves_the_rest_of_the_cache_alone() -> None:
    """Only the folders builds keep what they make in: the fonts and the lookups are beside them."""
    kinds = (FOUND_KIND, WEB_KIND, PRINT_KIND, PDF_KIND)
    kept = [cached_path(kind, "old", ".bin") for kind in kinds]
    beside = [build_cache_dir() / name for name in ("fonts/x.ttf", "archive.json", "logo.json")]
    for path in (*kept, *beside):
        cache_bytes(path, b"old")
        utime(path, (LONG_AGO, LONG_AGO))

    prune_build_cache()

    assert [path.exists() for path in kept] == [False] * len(kept)
    assert [path.exists() for path in beside] == [True] * len(beside)
