"""The `.min` copies: smaller, linking each other, and with maps naming what they came from."""

import json
from pathlib import Path

import pytest

from eta_publish import minify
from eta_publish.minify import min_name

BASE = "https://example.com/assets"

PAGE = f"""<link rel="stylesheet" href="{BASE}/report.css" />
<script src="{BASE}/report.js" defer></script>
<div class="eta-report">
  <p>
    A <a href="#a">link</a> and a word.
  </p>
</div>
"""


def test_the_minified_name_keeps_the_extension() -> None:
    assert min_name("report.html") == "report.min.html"
    assert min_name("report.published.html") == "report.published.min.html"


def test_the_page_links_the_minified_assets(tmp_path: Path) -> None:
    source = tmp_path / "report.html"
    source.write_text(PAGE)
    written = minify.page(source, BASE)
    assert written == tmp_path / "report.min.html"
    html = written.read_text()
    assert f"{BASE}/report.min.css" in html
    assert f"{BASE}/report.min.js" in html
    assert "report.css" not in html.replace("report.min.css", "")
    # The spaces around the link draw, so they stay.
    assert "A <a href=#a>link</a> and a word." in html
    assert len(html) < len(PAGE)


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
    (tmp_path / "report.css").write_text(css)
    (tmp_path / "report.js").write_text(js)
    written = minify.assets(tmp_path)
    assert {p.name for p in written} == {
        "report.min.css",
        "report.min.css.map",
        "report.min.js",
        "report.min.js.map",
    }
    for name, source in (("report.min.css", css), ("report.min.js", js)):
        code = (tmp_path / name).read_text()
        assert "why" not in code
        assert f"sourceMappingURL={name}.map" in code
        # Named as they sit beside it, not by where the build ran,
        # and carrying them, so nothing else has to be served.
        sourcemap = json.loads((tmp_path / f"{name}.map").read_text())
        assert sourcemap["sources"] == [name.replace(".min", "")]
        assert sourcemap["sourcesContent"] == [source]
