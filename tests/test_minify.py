"""The `.min` copies: smaller, linking each other, and with maps naming what they came from."""

import json
from pathlib import Path

import pytest

from eta_publish import minify

BASE = "https://example.com/assets"

PAGE = f"""<link rel="stylesheet" href="{BASE}/publication.css" />
<script src="{BASE}/publication.js" defer></script>
<div class="eta-report">
  <p>
    A <a href="#a">link</a> and a word.
  </p>
</div>
"""


WHOLE_PAGE = (
    '<!doctype html>\n<html>\n<head>\n<link rel="stylesheet" href="../assets/page.css" />\n'
    '<link rel="stylesheet" href="../assets/publication.css" />\n'
    '<script src="../assets/publication.js" defer></script>\n</head>\n<body>\n<p>A page.</p>\n'
    "</body>\n</html>\n"
)
"""A publication's `index.html`, which links the page's stylesheet too, and relatively."""


@pytest.mark.parametrize(
    ("name", "text", "base", "linked", "assets", "body"),
    [
        (
            "report.html",
            PAGE,
            BASE,
            None,
            ["publication.min.css", "publication.min.js"],
            # The spaces around the link draw, so they stay.
            "A <a href=#a>link</a> and a word.",
        ),
        (
            "index.html",
            WHOLE_PAGE,
            "../assets",
            minify.PAGE_ASSETS,
            ["page.min.css", "publication.min.css", "publication.min.js"],
            "<p>A page.</p>",
        ),
    ],
)
def test_the_page_links_the_minified_assets(
    tmp_path: Path,
    name: str,
    text: str,
    base: str,
    linked: tuple[str, ...] | None,
    assets: list[str],
    body: str,
) -> None:
    source = tmp_path / name
    source.write_text(text)
    if linked is None:
        written = minify.page(source, base)
    else:
        written = minify.page(source, base, linked=linked)
    assert written == tmp_path / name.replace(".html", ".min.html")
    html = written.read_text()
    for asset in assets:
        assert f"{base}/{asset}" in html
        assert asset.replace(".min", "") not in html.replace(asset, "")
    assert body in html
    assert len(html) < len(text)


def test_a_page_not_linking_the_assets_there_is_refused(tmp_path: Path) -> None:
    """Rather than a minified page still linking the unminified assets."""
    source = tmp_path / "report.html"
    source.write_text(PAGE)
    with pytest.raises(RuntimeError, match="0 times rather than once"):
        minify.page(source, "https://elsewhere.example/assets")
    assert not (tmp_path / "report.min.html").exists()


def test_the_assets_are_minified_with_maps_of_what_they_came_from(tmp_path: Path) -> None:
    css = ".a {\n  /* why */\n  color: red;\n}\n"
    js = "(() => {\n  // why\n  const long = 1;\n  console.log(long);\n})();\n"
    (tmp_path / "publication.css").write_text(css)
    (tmp_path / "publication.js").write_text(js)
    (tmp_path / "page.css").write_text("p {\n  margin: 0;\n}\n")
    written = minify.assets(tmp_path)
    assert {p.name for p in written} == {
        "page.min.css",
        "page.min.css.map",
        "publication.min.css",
        "publication.min.css.map",
        "publication.min.js",
        "publication.min.js.map",
    }
    for name, source in (("publication.min.css", css), ("publication.min.js", js)):
        code = (tmp_path / name).read_text()
        assert "why" not in code
        assert f"sourceMappingURL={name}.map" in code
        # Named as they sit beside it, not by where the build ran,
        # and carrying them, so nothing else has to be served.
        sourcemap = json.loads((tmp_path / f"{name}.map").read_text())
        assert sourcemap["sources"] == [name.replace(".min", "")]
        assert sourcemap["sourcesContent"] == [source]


def test_the_assets_are_found_in_a_relative_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As the drafts hook's `--into .drafts-check-*/site` gives it:
    the script runs inside the directory, so it can't be handed the same relative path."""
    assets = tmp_path / "site" / "assets"
    assets.mkdir(parents=True)
    for name in minify.PAGE_ASSETS:
        (assets / name).write_text("p {\n  margin: 0;\n}\n" if name.endswith(".css") else "1;\n")
    monkeypatch.chdir(tmp_path)
    written = minify.assets(Path("site/assets"))
    assert all((tmp_path / path).exists() for path in written)
