"""The logo a chart carries is what `svgo` makes of the logo as drawn."""

from pathlib import Path

import pytest

from eta_publish import logo
from eta_publish.logo import LOGO, SOURCE, write_logo


def test_the_committed_logo_is_what_svgo_writes(tmp_path: Path) -> None:
    """An edit to the source committed without the logo it makes fails here."""
    written = tmp_path / "logo.svg"
    write_logo(SOURCE, written, cache=tmp_path / "cache.json")
    assert written.read_text() == LOGO.read_text()


def test_an_unchanged_source_is_not_minified_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "logo.src.svg"
    source.write_text(SOURCE.read_text())
    written = tmp_path / "logo.svg"
    cache = tmp_path / "cache.json"
    assert write_logo(source, written, cache)

    def unasked(path: Path) -> str:
        raise AssertionError("ran svgo for an answer it had")

    monkeypatch.setattr(logo, "minify", unasked)
    assert not write_logo(source, written, cache)
    written.unlink()
    assert write_logo(source, written, cache)
    assert written.read_text() == LOGO.read_text()

    source.write_text(SOURCE.read_text().replace("#0032d4", "#0032d5"))
    with pytest.raises(AssertionError, match="ran svgo"):
        write_logo(source, written, cache)
