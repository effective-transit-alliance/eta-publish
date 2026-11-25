"""Whether what `report.squarespace.html` copies from etany.org is still what etany.org serves.

`squarespace.py` copies, from `SOURCE`, the URLs of the site's script and stylesheets,
`assets/squarespace.js` the two header settings the script reads,
`assets/squarespace-fonts.html` the `<style>` declaring Poppins,
and `assets/squarespace.html` the `<body>`, with its header and footer.
Each goes stale when Squarespace or the site changes,
so an online build reads `SOURCE` once, with `check_copy`, and warns about each difference.

It only says so: whether to copy again is a decision about the page, not the build's to make.
Nor does a page that cannot be read fail the build, any more than an archive that cannot be asked:
it is said, and the build goes on.
"""

import difflib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import override
from urllib.parse import urlsplit

import requests
from rich.text import Text

from . import console
from .console import Linked
from .naming import LIVE_SITE
from .nodes import Shown, Span
from .squarespace import FONTS, SCRIPT_SETUP, SHELL, SITE_SCRIPT, STYLESHEETS, mark_current

SOURCE = f"{LIVE_SITE}/reports/ibx-automation"
"""The live page `report.squarespace.html` is a copy of."""

HEADER_SETTINGS = ("tweak-fixed-header", "tweak-fixed-header-style")
"""The two of the site's settings `assets/squarespace.js` copies, from `tweakJSON`."""

CONTEXT = "Static.SQUARESPACE_CONTEXT = "
"""What a live page's `<script>` assigns its settings with, as JSON."""

FONT_IDS = "data-sqsp-font-ids"
"""The attribute marking the `<style>` a live page declares Poppins in."""

SHELL_PARTS = ("header", "footer")
"""The elements of the `<body>` compared: the site's own, the same on every page."""

LINK_ATTRIBUTES = ("href", "src")
"""Where the copy made a link absolute, and so where a live page's is made absolute to compare."""

SHOWN_DIFFERENCES = 5
"""How many differences in one of `SHELL_PARTS`, or rules in the fonts, are each said,
before the rest are counted."""

SHOWN_LENGTH = 120
"""How much of a tag or text a warning quotes before cutting it short."""

_SHELL_FILE = Shown("eta_publish/assets/squarespace.html")
_PY_FILE = Shown("eta_publish/squarespace.py")
_JS_FILE = Shown("eta_publish/assets/squarespace.js")
_FONTS_FILE = Shown("eta_publish/assets/squarespace-fonts.html")
_PAGE_FILE = Shown("report.squarespace.html")
"""Each copy, as a warning names it, so it can be found to copy again."""


@dataclass(frozen=True)
class Copy:
    """What was copied from `SOURCE`, as `squarespace.py` has it: the defaults."""

    stylesheets: tuple[str, ...] = STYLESHEETS
    site_script: str = SITE_SCRIPT
    script_setup: str = SCRIPT_SETUP
    fonts: str = FONTS
    shell: str = SHELL


type Token = tuple[str, str, tuple[tuple[str, str], ...]]
"""One piece of markup as compared: `("start", name, attrs)`, `("end", name, ())`,
`("text", text, ())`, or `("comment", text, ())`."""


def _collapsed(text: str) -> str:
    return " ".join(text.split())


@dataclass
class Element:
    """An element of a page: its attributes, and the text directly inside it."""

    name: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)


class _Page(HTMLParser):
    """What a page is compared by: its tokens, and its `<link>`, `<script>`, and `<style>` elements.

    Each token is compared as markup means it rather than as it is written,
    since the copy writes again each tag it changed, and leaves out the lines with nothing on them:
    a tag's attributes in any order, a value or text with its whitespace collapsed,
    and text that is only whitespace not there at all.
    """

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[Token] = []
        self.elements: list[Element] = []
        self._raw: Element | None = None
        self.feed(html)
        self.close()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        self.tokens.append(
            ("start", tag, tuple(sorted((n, _collapsed(v)) for n, v in values.items())))
        )
        if tag in ("link", "script", "style"):
            self.elements.append(Element(tag, values))
            self._raw = self.elements[-1] if tag != "link" else None

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    @override
    def handle_endtag(self, tag: str) -> None:
        self.tokens.append(("end", tag, ()))
        self._raw = None

    @override
    def handle_data(self, data: str) -> None:
        if self._raw is not None:
            self._raw.text.append(data)
        if text := _collapsed(data):
            self.tokens.append(("text", text, ()))

    @override
    def handle_comment(self, data: str) -> None:
        self.tokens.append(("comment", _collapsed(data), ()))


def _absolute(url: str) -> str:
    """`url` as the copy writes it.

    A root-relative link on `LIVE_SITE`, a scheme-relative one on `https:`.
    """
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{LIVE_SITE}{url}"
    return url


def _as_copied(token: Token) -> Token:
    """A live page's `token` with its links absolute, as the copy has them."""
    if token[0] != "start":
        return token
    kind, name, attrs = token
    return (kind, name, tuple((n, _absolute(v) if n in LINK_ATTRIBUTES else v) for n, v in attrs))


def _part(tokens: list[Token], name: str) -> list[Token] | None:
    """The tokens of the first `name` element, from its start tag to its end, if there is one."""
    start = next((i for i, t in enumerate(tokens) if t[:2] == ("start", name)), None)
    if start is None:
        return None
    depth = 0
    for i in range(start, len(tokens)):
        if tokens[i][:2] == ("start", name):
            depth += 1
        elif tokens[i][:2] == ("end", name):
            depth -= 1
            if depth == 0:
                return tokens[start : i + 1]
    return tokens[start:]


def _quoted(token: Token) -> str:
    """`token` as markup, cut short at `SHOWN_LENGTH`."""
    kind, value, attrs = token
    if kind == "start":
        written = "".join(f' {n}="{escape(v)}"' for n, v in attrs)
        text = f"<{value}{written}>"
    elif kind == "end":
        text = f"</{value}>"
    elif kind == "comment":
        text = f"<!--{value}-->"
    else:
        text = value
    return text if len(text) <= SHOWN_LENGTH else f"{text[: SHOWN_LENGTH - 1]}…"


def _pieces(tokens: list[Token]) -> str:
    if not tokens:
        return "nothing"
    more = len(tokens) - 1
    return _quoted(tokens[0]) + (f" and {more} more" if more else "")


type Warn = Callable[..., None]
"""Says one difference: a `console.warning` template and its values."""


def _shell(live: list[Token], copied: list[Token], warn: Warn) -> None:
    for name in SHELL_PARTS:
        here = _part(live, name)
        there = _part(copied, name)
        if here is None:
            warn("{} has no {}, which {} copies", Linked(SOURCE), Shown(f"<{name}>"), _SHELL_FILE)
            continue
        assert there is not None, f"`squarespace.html` has no <{name}>"
        changes = [
            op
            for op in difflib.SequenceMatcher(None, here, there, autojunk=False).get_opcodes()
            if op[0] != "equal"
        ]
        for _, i1, i2, j1, j2 in changes[:SHOWN_DIFFERENCES]:
            # Where the copy and the page part, the page's element just before, to find it by.
            after = next((t for t in reversed(here[:i1]) if t[0] == "start"), here[0])
            warn(
                "{}'s {} has {} where {} has {}, after {}",
                Linked(SOURCE),
                Shown(f"<{name}>"),
                Shown(_pieces(here[i1:i2])),
                _SHELL_FILE,
                Shown(_pieces(there[j1:j2])),
                Shown(_quoted(after)),
            )
        if len(changes) > SHOWN_DIFFERENCES:
            warn(
                "{}'s {} has {} more differences from {}",
                Linked(SOURCE),
                Shown(f"<{name}>"),
                str(len(changes) - SHOWN_DIFFERENCES),
                _SHELL_FILE,
            )


def _imports(css: str) -> list[str]:
    """The URLs `css` imports with `@import`, each as `url(...)` or a quoted string.

    Read with string methods rather than a CSS parser, which only the tests have:
    this is the one rule wanted, and the `<style>` it is in is the site's own few lines.
    """
    found: list[str] = []
    at = css.find("@import")
    while at != -1:
        rest = css[at + len("@import") :].lstrip()
        if rest.startswith("url("):
            rest = rest[len("url(") :].partition(")")[0].strip()
        if rest[:1] in ("'", '"'):
            rest = rest[1:].partition(rest[0])[0]
        found.append(rest.strip())
        at = css.find("@import", at + 1)
    return found


def _file(url: str) -> str:
    """What a versioned URL is a version of.

    Its last path segment, and for Google Fonts, whose path is always `css2`, its query too.
    """
    parts = urlsplit(url)
    name = parts.path.rpartition("/")[2]
    return f"{name}?{parts.query}" if parts.netloc == "fonts.googleapis.com" else name


def _assets(page: _Page, copy: Copy, warn: Warn) -> None:
    linked = [
        _absolute(e.attrs["href"])
        for e in page.elements
        if e.name == "link" and "stylesheet" in e.attrs.get("rel", "").split() and "href" in e.attrs
    ]
    imported = [
        _absolute(url)
        for e in page.elements
        if e.name == "style"
        for url in _imports("".join(e.text))
    ]
    styles = linked + imported
    for href in copy.stylesheets:
        if href in styles:
            continue
        instead = [s for s in styles if _file(s) == _file(href)]
        if instead:
            warn(
                "{} links {} where {} links {}",
                Linked(SOURCE),
                Linked(instead[0]),
                _PY_FILE,
                Linked(href),
            )
        else:
            warn("{} no longer links {}, which {} links", Linked(SOURCE), Linked(href), _PY_FILE)

    scripts = [
        _absolute(e.attrs["src"]) for e in page.elements if e.name == "script" and "src" in e.attrs
    ]
    bundles = [s for s in scripts if _file(s).startswith("site-bundle.")]
    if copy.site_script in scripts:
        return
    if bundles:
        warn(
            "{} links the site's script as {} where {} links {}",
            Linked(SOURCE),
            Linked(bundles[0]),
            _PY_FILE,
            Linked(copy.site_script),
        )
    else:
        warn(
            "{} links no site script, {}, where {} links {}",
            Linked(SOURCE),
            Shown("site-bundle.js"),
            _PY_FILE,
            Linked(copy.site_script),
        )


def _copied_setting(setup: str, name: str) -> str:
    """What `setup`, `assets/squarespace.js`, sets the setting `name` to.

    Its value is a JSON string where the object literal gives it, so it is read as one.
    """
    key = f"{json.dumps(name)}:"
    at = setup.find(key)
    if at == -1:
        raise RuntimeError(f"`squarespace.js` sets no {name}")
    value, _ = json.JSONDecoder().raw_decode(setup[at + len(key) :].lstrip())
    return str(value)


def _settings(page: _Page, copy: Copy, warn: Warn) -> None:
    scripts = ["".join(e.text) for e in page.elements if e.name == "script"]
    found = next((s for s in scripts if CONTEXT in s), None)
    if found is None:
        warn(
            "{} sets no {}, which {} copies its header settings from",
            Linked(SOURCE),
            Shown(CONTEXT.split(" ")[0]),
            _JS_FILE,
        )
        return
    context, _ = json.JSONDecoder().raw_decode(found.partition(CONTEXT)[2])
    tweaks = context.get("tweakJSON", {})
    for name in HEADER_SETTINGS:
        copied = _copied_setting(copy.script_setup, name)
        if name not in tweaks:
            warn(
                "{} no longer sets {}, which {} sets to {}",
                Linked(SOURCE),
                Shown(name),
                _JS_FILE,
                Shown(copied),
            )
        elif str(tweaks[name]) != copied:
            warn(
                "{} sets {} to {} where {} sets it to {}",
                Linked(SOURCE),
                Shown(name),
                Shown(str(tweaks[name])),
                _JS_FILE,
                Shown(copied),
            )


def _fonts(page: _Page, copy: Copy, warn: Warn) -> None:
    copied = next(e for e in _Page(copy.fonts).elements if e.name == "style")
    live = next((e for e in page.elements if e.name == "style" and FONT_IDS in e.attrs), None)
    if live is None:
        warn(
            "{} has no {}, which {} copies",
            Linked(SOURCE),
            Shown(f"<style {FONT_IDS}>"),
            _FONTS_FILE,
        )
        return
    if live.attrs != copied.attrs:
        warn(
            "{}'s fonts {} is {} where {} has {}",
            Linked(SOURCE),
            Shown("<style>"),
            Shown(_quoted(("start", "style", tuple(live.attrs.items())))),
            _FONTS_FILE,
            Shown(_quoted(("start", "style", tuple(copied.attrs.items())))),
        )
    here = _rules("".join(live.text))
    there = _rules("".join(copied.text))
    added = [rule for rule in here if rule not in there]
    removed = [rule for rule in there if rule not in here]
    for rule in added[:SHOWN_DIFFERENCES]:
        warn(
            "{}'s {} has {}, which {} does not",
            Linked(SOURCE),
            Shown(f"<style {FONT_IDS}>"),
            Shown(rule),
            _FONTS_FILE,
        )
    for rule in removed[:SHOWN_DIFFERENCES]:
        warn(
            "{}'s {} no longer has {}, which {} does",
            Linked(SOURCE),
            Shown(f"<style {FONT_IDS}>"),
            Shown(rule),
            _FONTS_FILE,
        )
    more = max(len(added) - SHOWN_DIFFERENCES, 0) + max(len(removed) - SHOWN_DIFFERENCES, 0)
    if more:
        warn(
            "{}'s {} has {} more rules changed from {}",
            Linked(SOURCE),
            Shown(f"<style {FONT_IDS}>"),
            str(more),
            _FONTS_FILE,
        )


def _rules(css: str) -> list[str]:
    """The rules of `css`, each with its whitespace collapsed, without its comments.

    Compared as rules rather than as lines, and in any order:
    two fetches of the same page on the same day have given the same `@font-face` rules
    in different orders, and each says which characters it is for,
    so which comes first makes no difference to what a page shows.
    Read with string methods rather than a CSS parser, which only the tests have:
    the block is `@font-face` rules and comments only, and a declaration holds no braces.
    """
    bare: list[str] = []
    at = 0
    while (opened := css.find("/*", at)) != -1:
        bare.append(css[at:opened])
        closed = css.find("*/", opened + 2)
        at = len(css) if closed == -1 else closed + 2
    bare.append(css[at:])
    rules = (_collapsed(rule) for rule in "".join(bare).split("}"))
    return [f"{rule} }}" for rule in rules if rule]


def differences(page: str, copy: Copy | None = None) -> list[Text]:
    """Each way `copy` differs from `page`, the live `SOURCE`, as a warning to write."""
    copy = copy or Copy()
    said: list[Text] = []

    def warn(template: str, *values: Span | Linked) -> None:
        said.append(console.warning(template, *values))

    parsed = _Page(page)
    _assets(parsed, copy, warn)
    _settings(parsed, copy, warn)
    _fonts(parsed, copy, warn)
    live = [_as_copied(t) for t in parsed.tokens]
    _shell(live, _Page(mark_current(copy.shell, SOURCE)).tokens, warn)
    return said


def check_copy(http: requests.Session | None = None, copy: Copy | None = None) -> None:
    """Read `SOURCE` and warn about each way `copy` of it is no longer what it is.

    Never a failure: a page that would not load, or would not read, leaves the copy unchecked,
    and says so.
    """
    try:
        response = (http or requests.Session()).get(SOURCE, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        _unchecked(str(e) or type(e).__name__)
        return
    try:
        found = differences(response.text, copy)
    # Anything: a check that only reports must not be what stops the build.
    except Exception as e:
        _unchecked(f"{type(e).__name__}: {e}")
        return
    for warning in found:
        console.write(warning)


def _unchecked(why: str) -> None:
    console.write(
        console.warning(
            "could not read {} ({}); whether {}'s copy of it is current was not checked",
            Linked(SOURCE),
            why,
            _PAGE_FILE,
        )
    )
