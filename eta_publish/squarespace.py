"""A publication as etany.org shows it: `report.squarespace.html`.

`report.html` is a page of our own, styled by `page.css`.
What goes out is the fragment pasted into a Squarespace Embed block,
which inherits the site's stylesheets, fonts, header, and footer,
so this is that fragment in that page:
the `<body>` of a live publication page, `assets/squarespace.html`,
with the fragment in its Embed block, under the site's own stylesheets.

The stylesheets are linked where Squarespace serves them, not copied,
so the page shows the site's styles as they are today rather than as they were.
The `<body>`, with the header and footer, is copied, so a build needs no network
and writes the same page every time from the same document.
It was taken from `/reports/ibx-automation`, and changed only where that page is itself
or where it would not work from another host:
the fragment pasted there is `<!-- publication -->`,
the navigation marks no page as the current one, which `mark_current` puts back for each,
root-relative links name `https://www.etany.org`, and scheme-relative ones `https:`,
the `<body>` has no `id` or class naming that page's collection,
and the desktop grid has one row rather than the 590 the editor gave that publication,
so a publication of any length fills it as it is.
The site's own script, which opens the menu on a phone, is not linked,
so the header is what it is before anything is clicked.
"""

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import override

from .assets import read

SHELL = read("squarespace.html")
"""The `<body>` of a live publication page, from `<body>` to `</body>`."""

PUBLICATION = "<!-- publication -->"
"""Where in `SHELL` the fragment goes: inside the Embed block, where it is pasted."""

SITE_NAME = "Effective Transit Alliance New York"
"""What Squarespace puts after a page's title in the window's title."""

STYLESHEETS = (
    "https://definitions.sqspcdn.com/website-component-definition/static-assets/website.components.embed/d35130ff-2453-47a4-ae7e-04e216687bcc_825/website.components.embed.styles.css",
    "https://static1.squarespace.com/static/versioned-site-css/6172f286c4e030728d09f143/77/5c5a519771c10ba3470d8101/6172f287c4e030728d09f15c/1858/site.css?nocustom=true",
    "https://static1.squarespace.com/static/vta/5c5a519771c10ba3470d8101/versioned-assets/1795537239873-O0102358Z9KFIY0MJ4HS/static.css",
    "https://static1.squarespace.com/static/custom-css/6172f286c4e030728d09f143/6172f287c4e030728d09f15c/11/custom.css",
    # The site's Custom CSS sets every block of text in Yaldevi,
    # which Squarespace's own page imports from Google Fonts.
    "https://fonts.googleapis.com/css2?family=Yaldevi:wght@300;500;600&display=swap",
)
"""What a live page links to style itself, in the order it links them:
the Embed block's, the site's, the template's, the site's Custom CSS, and its font.
Not the Typekit fonts the template loads, which the Custom CSS overrides everywhere."""

FAVICON = "https://images.squarespace-cdn.com/content/v1/6172f286c4e030728d09f143/a643aa12-98e2-4680-a9d2-d25975375c0a/favicon.ico"
"""The site's icon, as its pages link it."""

ITEM_CLASSES = ("header-nav-item", "header-nav-folder-item", "header-menu-nav-item")
"""What the navigation calls an entry, in the header, in a folder's list, and in the phone's menu:
the current page's gets the class with `--active` after it."""

VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
    | {"track", "wbr"}
)
"""The elements with no end tag, so never anything's parent."""


@dataclass(eq=False)
class StartTag:
    """A start tag in `SHELL`: where it is, what it says, and what it is inside."""

    name: str
    attrs: list[tuple[str, str | None]]
    start: int
    end: int
    parents: list[StartTag]

    changed: bool = field(default=False)

    def get(self, name: str) -> str | None:
        return dict(self.attrs).get(name)

    def classes(self) -> list[str]:
        value = self.get("class")
        return [] if value is None else value.split()

    def set(self, name: str, value: str) -> None:
        self.attrs = [(n, v) for n, v in self.attrs if n != name] + [(name, value)]
        self.changed = True

    def add_class(self, name: str) -> None:
        if name not in self.classes():
            self.set("class", " ".join([*self.classes(), name]))

    def markup(self) -> str:
        attrs = (n if v is None else f'{n}="{escape(v)}"' for n, v in self.attrs)
        return f"<{' '.join([self.name, *attrs])}>"


class _Tags(HTMLParser):
    """Every start tag in some HTML, in order, with the elements it is inside."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.lines = [0]
        for line in html.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.tags: list[StartTag] = []
        self.open: list[StartTag] = []
        self.feed(html)
        self.close()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, column = self.getpos()
        start = self.lines[line - 1] + column
        text = self.get_starttag_text() or ""
        found = StartTag(tag, attrs, start, start + len(text), list(self.open))
        self.tags.append(found)
        if tag not in VOID:
            self.open.append(found)

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.open.pop()

    @override
    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i].name == tag:
                del self.open[i:]
                break


def _item(anchor: StartTag) -> tuple[StartTag, str] | None:
    """The navigation entry `anchor` is the link of, and which kind of entry it is."""
    for parent in reversed(anchor.parents):
        for kind in ITEM_CLASSES:
            if kind in parent.classes():
                return parent, kind
    return None


def _current(anchor: StartTag, page_url: str) -> bool:
    """Whether `anchor` is a link in the navigation to the page at `page_url`.

    The page itself, or the collection it is an item of:
    a statement is a post in the blog at `/statements`,
    and Squarespace marks that link as the page a post is on.
    """
    href = anchor.get("href")
    if href is None or anchor.get("data-folder-id") is not None:
        return False
    if href == page_url:
        return True
    found = _item(anchor)
    if found is None:
        return False
    item, kind = found
    return f"{kind}--collection" in item.classes() and page_url.startswith(f"{href}/")


def mark_current(html: str, page_url: str) -> str:
    """`html` with the navigation marking the page at `page_url` as Squarespace marks it.

    Its own entry, `--active` and `aria-current="page"`,
    and the folder holding it, if any, `--active` and `aria-current="true"`:
    in the header, the folder's entry around it,
    and in the phone's menu, where a folder's list is beside its entry rather than in it,
    the entry whose link opens that list.
    A page the navigation does not list, like a draft, marks nothing.
    """
    tags = _Tags(html).tags
    for anchor in tags:
        if anchor.name != "a" or not _current(anchor, page_url):
            continue
        found = _item(anchor)
        if found is None:
            continue
        item, kind = found
        anchor.set("aria-current", "page")
        item.add_class(f"{kind}--active")
        for parent in anchor.parents:
            if "header-nav-item--folder" in parent.classes():
                parent.add_class("header-nav-item--active")
                for title in tags:
                    inside = any(p is parent for p in title.parents)
                    if inside and "header-nav-folder-title" in title.classes():
                        title.set("aria-current", "true")
            folder = parent.get("data-folder")
            if folder is None:
                continue
            for opener in tags:
                if opener.name == "a" and opener.get("data-folder-id") == folder:
                    opener.set("aria-current", "true")
                    opened = _item(opener)
                    if opened is not None:
                        opened[0].add_class(f"{opened[1]}--active")
    out: list[str] = []
    at = 0
    for changed in (t for t in tags if t.changed):
        out += [html[at : changed.start], changed.markup()]
        at = changed.end
    return "".join([*out, html[at:]])


def squarespace_page(fragment: str, title: str, page_url: str) -> str:
    """The page `fragment` is pasted into, titled `title`, as etany.org shows it at `page_url`.

    Marked `noindex`, as `report.html` is, for the same reason:
    a preview is not the publication, and a search engine should not offer it as one.
    """
    if SHELL.count(PUBLICATION) != 1:
        raise RuntimeError(f"`squarespace.html` has {SHELL.count(PUBLICATION)} places for it")
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',
        # `&mdash;`, as Squarespace writes it.
        f"<title>{escape(title)} &mdash; {escape(SITE_NAME)}</title>",
        f'<link rel="icon" type="image/x-icon" href="{escape(FAVICON)}">',
        *(f'<link rel="stylesheet" href="{escape(href)}">' for href in STYLESHEETS),
    ]
    body = mark_current(SHELL, page_url).replace(PUBLICATION, fragment.strip())
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en-US">',
            "<head>",
            *head,
            "</head>",
            body.strip(),
            "</html>",
            "",
        ]
    )
