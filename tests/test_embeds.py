"""Videos and posts, from a paragraph that is nothing but a link to one."""

import hashlib
import io
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast, override

import pytest
import requests
from paths import HOST
from test_conventions import build, field, image, para

from eta_publish.build import write_frames
from eta_publish.docs_json import JsonObject
from eta_publish.embeds import (
    _stems,
    check_embeds,
    download,
    look_up,
    read_embed_index,
    srt_to_vtt,
    to_vtt,
    unrolled,
    write_captions,
    write_embed_index,
)
from eta_publish.emit.html import HtmlEmitter, publication_page
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.emit.typst import TypstEmitter
from eta_publish.naming import IMAGE_DIR, VIDEO_DIR
from eta_publish.nodes import (
    Captions,
    Card,
    Cue,
    Document,
    Embed,
    Figure,
    Inline,
    Paragraph,
    Platform,
    Text,
)


def linked(*runs: tuple[str, str | None], underline: str = "") -> JsonObject:
    """A paragraph of runs, each linked to its href or to nothing."""
    elements: list[JsonObject] = []
    if underline:
        elements.append({"textRun": {"content": underline, "textStyle": {"underline": True}}})
    for text, href in runs:
        style: JsonObject = {"link": {"url": href}} if href else {}
        elements.append({"textRun": {"content": text, "textStyle": style}})
    elements[-1]["textRun"]["content"] += "\n"
    return {
        "paragraph": {"paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}, "elements": elements}
    }


def video(url: str) -> JsonObject:
    """A `Video:` line, as the documents write one."""
    return linked((": ", None), (url, url), underline="Video")


def warning(text: str) -> JsonObject:
    """A `Warning:` line."""
    return linked((f": {text}", None), underline="Warning")


def copied(url: str) -> JsonObject:
    """A `Video (Copy):` line."""
    return linked((": ", None), (url, url), underline="Video (Copy)")


def graphic(url: str) -> list[JsonObject]:
    """A `Video (Copy):` line with a `Warning: Graphic Content` under it."""
    return [copied(url), warning("Graphic Content")]


def _text(content: list[Inline]) -> str:
    return "".join(i.text for i in content if isinstance(i, Text))


def _x(n: int) -> str:
    return f"https://x.com/someone/status/{n}"


def test_video_lines_parse_the_way_the_writer_meant() -> None:
    drive = "https://drive.google.com/file/d/1abc/view?usp=drive_link"
    credited = "https://www.youtube.com/live/syjWBXSAbyM?t=2940s"
    doc = build(
        [
            para("Headline", "TITLE"),
            # What a link is a link to, by platform.
            video("https://www.youtube.com/watch?v=KDaRRmUWUZI"),
            video("https://www.youtube.com/live/HEfH7R6j6QY?t=911s"),
            video("https://youtu.be/h6-MVzb58E4?si=rJ&t=137"),
            video("https://www.youtube.com/watch?v=abc&t=1h2m3s"),
            video("https://x.com/ThoughtPolic3HQ/status/1874861375857541619/video/1"),
            video("https://twitter.com/someone/status/123"),
            video("https://bsky.app/profile/bsky.app/post/3l6oveex3ii2l"),
            video(drive),
            # Too Damn Loud's video, which Docs shows by its title rather than its address.
            linked(
                (": ", None),
                ("Too Damn Loud", "https://youtube.com/shorts/o90JQBWdgTI?is=I4"),
                underline="Video",
            ),
            # Links to a channel, a profile, and a document are not videos.
            video("https://www.youtube.com/@MrRailfan"),
            video("https://x.com/ThoughtPolic3HQ"),
            video("https://www.mta.info/document/196361"),
            # Without the label a pasted link is a link, and so is one in a sentence.
            linked((_x(9), _x(9))),
            linked(
                ("The MTA ", None),
                ("announced", "https://www.youtube.com/watch?v=HEfH7R6j6QY"),
                (" it.", None),
            ),
            # A video line right under a figure is not its caption.
            image(),
            video("https://www.youtube.com/watch?v=fig"),
            # A credit linked to a video stays a credit.
            image(),
            para("The tail tracks the MTA proposed."),
            linked((": MTA", credited), underline="Credit"),
            # The stop ends the caption, but is not part of the file's name.
            linked(
                (": ", None), ("Hit by the train", _x(124)), (".", None), underline="Video (Copy)"
            ),
            linked((": ", None), (_x(125), _x(125)), underline="Video (copy, Grafic)"),
            linked((": coming soon", None), underline="Video"),
            video("https://www.youtube.com/watch?v=w1"),
            warning("Graphic Content"),
            video("https://www.youtube.com/watch?v=w2"),
            warning("Graphic Content: a man is hit"),
            video("https://www.youtube.com/watch?v=w3"),
            warning(""),
        ]
    )

    def youtube(
        key: str,
        url: str = "",
        start: int = 0,
        vertical: bool = False,
        title: str = "",
        warning_kind: str = "",
    ) -> Embed:
        return Embed(
            url=url or f"https://www.youtube.com/watch?v={key}",
            platform=Platform.YOUTUBE,
            key=key,
            start=start,
            vertical=vertical,
            warning_kind=warning_kind,
            title=title,
            name=title,
        )

    shapes = [
        replace(b, warning=[]) if isinstance(b, Embed) else type(b).__name__ for b in doc.blocks
    ]
    assert shapes == [
        youtube("KDaRRmUWUZI"),
        youtube("HEfH7R6j6QY", url="https://www.youtube.com/live/HEfH7R6j6QY?t=911s", start=911),
        youtube("h6-MVzb58E4", url="https://youtu.be/h6-MVzb58E4?si=rJ&t=137", start=137),
        youtube("abc", url="https://www.youtube.com/watch?v=abc&t=1h2m3s", start=3723),
        Embed(
            url="https://x.com/ThoughtPolic3HQ/status/1874861375857541619/video/1",
            platform=Platform.X,
            key="1874861375857541619",
        ),
        Embed(url="https://twitter.com/someone/status/123", platform=Platform.X, key="123"),
        Embed(
            url="https://bsky.app/profile/bsky.app/post/3l6oveex3ii2l",
            platform=Platform.BLUESKY,
            key="bsky.app/3l6oveex3ii2l",
        ),
        Embed(url=drive, platform=Platform.DRIVE, key="1abc"),
        youtube(
            "o90JQBWdgTI",
            url="https://youtube.com/shorts/o90JQBWdgTI?is=I4",
            vertical=True,
            title="Too Damn Loud",
        ),
        "Paragraph",
        "Paragraph",
        "Paragraph",
        "Paragraph",
        "Paragraph",
        "Figure",
        youtube("fig"),
        "Figure",
        Embed(
            url=_x(124),
            platform=Platform.X,
            key="124",
            copy=True,
            title="Hit by the train.",
            name="Hit by the train",
        ),
        Embed(url=_x(125), platform=Platform.X, key="125", copy=True),
        "Paragraph",
        youtube("w1", warning_kind="Graphic Content"),
        youtube("w2", warning_kind="Graphic Content"),
        youtube("w3"),
    ]

    first_figure, second_figure = [b for b in doc.blocks if isinstance(b, Figure)]
    assert not first_figure.caption
    assert second_figure.credit
    assert credited not in [e.url for e in doc.embeds]
    assert [_text(b.warning) for b in doc.blocks if isinstance(b, Embed) and b.warning] == [
        "Warning: Graphic Content",
        "Warning: Graphic Content: a man is hit",
    ]
    video_line = (
        "a `Video:` line has to be followed by one link to a YouTube video, "
        "an X or Bluesky post, or a video in Drive; publishing it as text: "
    )
    assert [str(w) for w in doc.warnings][1:] == [
        f"{video_line}`Video: https://www.youtube.com/@MrRailfan`",
        f"{video_line}`Video: https://x.com/ThoughtPolic3HQ`",
        f"{video_line}`Video: https://www.mta.info/document/196361`",
        "`Grafic` is not a modifier `Video:` takes; ignoring it: "
        f"`Video (copy, Grafic): {_x(125)}`",
        f"{video_line}`Video: coming soon`",
        "a `Warning:` line has to say what it warns of, "
        "as in `Warning: Graphic Content`; ignoring it",
    ]


def _between(text: str, start: str, end: str) -> str:
    """The part of `text` from `start` through the next `end`."""
    first = text.index(start)
    return text[first : text.index(end, first) + len(end)]


def test_every_kind_of_embed_renders_in_every_format() -> None:
    bluesky = "https://bsky.app/profile/bsky.app/post/3l6oveex3ii2l"
    drive = "https://drive.google.com/file/d/1abc/view"
    picture = "https://drive.google.com/file/d/2def/view"
    doc = build(
        [
            para("Headline", "TITLE"),
            video(bluesky),
            video(_x(101)),
            video(_x(102)),
            video(drive),
            video(picture),
            *graphic(_x(103)),
            copied(_x(104)),
            linked((": ", None), ("Hit by the 1 train", _x(105)), underline="Video (Copy)"),
            warning("Graphic Content: a man is hit"),
            field("Credit: ETA (Khyber Sen)"),
            copied(_x(106)),
        ]
    )
    doc.meta["URL"] = "/reports/someone"
    cards = doc.cards
    cards[bluesky] = Card(author="Bluesky (@bsky.app)", text="Hello", did="did:plc:z72")
    cards[_x(101)] = Card(author="Someone", text="Hi")
    cards[_x(102)] = Card(error="404")
    cards[drive] = Card(mime="video/mp4")
    cards[picture] = Card(mime="image/png")
    for n in (103, 104, 105, 106):
        cards[_x(n)] = Card(author="someone", text="a post")
    doc.media_files.update(
        {
            bluesky: "embed-1.jpg",
            _x(101): "embed-2.jpg",
            _x(102): "embed-3.jpg",
            drive: "embed-4.mp4",
            _x(103): "embed-5.mp4",
            _x(104): "embed-6.mp4",
            _x(105): "Hit_by_the_1_train.mp4",
            # A copy that failed to download, so its card is all that is shown.
            _x(106): "embed-8.jpg",
        }
    )
    doc.media_captions[_x(104)] = Captions("embed-6.vtt", automatic=True)
    assert [str(w) for w in doc.warnings][1:] == []

    html = HtmlEmitter(image_base="images", site_url=HOST).emit(doc)
    markdown = MarkdownEmitter().emit(doc)

    # A card loads nothing until it is clicked.
    card = _between(html, '<figure id="embed-bluesky-', "</figure>")
    player = "https://embed.bsky.app/embed/did:plc:z72/app.bsky.feed.post/3l6oveex3ii2l"
    assert f'data-player="{player}"' in card
    assert f'class="embed-card" href="{bluesky}"' in card
    assert 'src="images/embed-1.jpg"' in card
    assert "<iframe" not in html
    assert "[Bluesky (@bsky.app) on Bluesky: “Hello”]" in markdown
    # An embed's source has a box on hover: the script hangs it off a `cited`.
    assert '<span class="cited"><sup class="source-ref"' in _between(
        html, '<figure id="embed-x-101"', "</figure>"
    )
    # An embed nothing could describe is the link it was.
    assert f'class="embed-card" href="{_x(102)}"' not in html
    assert f"[{_x(102)}](<{_x(102)}>)" in markdown
    # A Drive video plays from the site; a Drive file that is not a video is a link.
    assert '<video src="videos/embed-4.mp4" controls preload="metadata"' in _between(
        html, '<figure id="embed-4"', "</figure>"
    )
    assert f'<a href="{picture}">{picture}</a>' in html
    assert f'class="embed-card" href="{picture}"' not in html

    # A copy plays from the site, and opens on its warning card rather than its first frame.
    graphic_copy = _between(html, '<figure id="embed-5"', "</figure>")
    assert '<video src="videos/embed-5.mp4" controls preload="metadata"' in graphic_copy
    assert f'poster="{HOST}/assets/warning-Graphic_Content.svg"' in graphic_copy
    # Its lightbox is opened by a link of its own, which works without the script;
    # in the box the warning still comes first, and nothing is fetched until it plays.
    assert '<a class="lightbox-open" href="#/media/File:embed-5.mp4"' in graphic_copy
    box = _between(html, '<dialog class="lightbox" id="/media/File:embed-5.mp4"', "</dialog>")
    assert 'class="lightbox-close" href="#embed-5"' in box
    assert box.index('class="embed-warning"') < box.index("<video")
    assert 'preload="none"' in box
    # A copy offers its captions.
    assert (
        '<track kind="captions" src="videos/embed-6.vtt" srclang="en" label="English (automatic)">'
        in _between(html, '<figure id="embed-6"', "</figure>")
    )

    # A copy is a figure like an image: named and captioned as one, with nothing of its post.
    titled = _between(html, '<figure id="Hit_by_the_1_train">', "</figure>")
    assert (
        '<p class="embed-warning" role="note">Warning: Graphic Content: a man is hit</p>' in titled
    )
    assert '<a class="link-mark"' in titled
    assert '<figcaption class="figure-caption">Hit by the 1 train</figcaption>' in titled
    assert '<figcaption class="figure-credit">Credit: ETA (Khyber Sen)</figcaption>' in titled
    assert "embed" not in titled.replace("embed-warning", "")
    assert _x(105) not in html
    link = "[Hit by the 1 train](<videos/Hit_by_the_1_train.mp4>)"
    warning_card = "[![WARNING: Graphic Content](../../assets/warning-Graphic_Content.svg)]"
    assert f"> ⚠ **Warning: Graphic Content: a man is hit**\n\n{warning_card}" in markdown
    assert f"(<videos/Hit_by_the_1_train.mp4>)\\\n{link}\\\nCredit: ETA (Khyber Sen)" in markdown

    # A copy that failed shows its card.
    failed = _between(html, '<figure id="embed-x-106"', "</figure>")
    assert "<video " not in failed
    assert 'src="images/embed-8.jpg"' in failed

    # The warning card is linked where the site is served, and beside a preview page.
    elsewhere = HtmlEmitter(image_base="images", site_url="https://reports.example.org").emit(doc)
    assert 'poster="https://reports.example.org/assets/warning-Graphic_Content.svg"' in elsewhere
    page = publication_page(doc, asset_base="../../assets", site_url=HOST)
    assert 'poster="../../assets/warning-Graphic_Content.svg"' in page

    # The PDF opens a video in its lightbox, where its warning and captions come first,
    # and shows a graphic video as its warning card and any other as its first frame.
    where = "https://www.etany.org/reports/someone"
    typst = TypstEmitter(page_url=where, site_url=HOST).emit(doc)
    assert f'#link("{where}#/media/File:embed-5.mp4")' in typst
    poster = (
        f'link("{where}#/media/File:embed-5.mp4")[#capped_image("print/warning-Graphic_Content.svg"'
    )
    assert typst.index("#video_warning[Warning: Graphic Content]") < typst.index(poster)
    assert 'capped_image("images/embed-6.frame.jpg", alt: "Video")' in typst
    assert typst.count("video_warning[") == 2
    preview = TypstEmitter(site_url=HOST).emit(doc)
    assert f'#link("{HOST}/reports/someone/#/media/File:embed-5.mp4")' in preview


def test_a_video_is_named_after_its_link_text() -> None:
    url = "https://x.com/someone/status/123"
    doc = build(
        [
            para("Headline", "TITLE"),
            linked((": ", None), ("Hit by the 1 train", url), underline="Video"),
        ]
    )
    assert [b.title for b in doc.blocks if isinstance(b, Embed)] == ["Hit by the 1 train"]
    assert _stems(doc.embeds) == {url: "Hit_by_the_1_train"}


def test_two_videos_whose_links_read_alike_both_carry_a_hash() -> None:
    first = Embed(url="https://x.com/a/status/1", platform=Platform.X, key="1", name="clip")
    second = Embed(url="https://x.com/b/status/2", platform=Platform.X, key="2", name="clip")
    alone = Embed(url="https://x.com/c/status/3", platform=Platform.X, key="3", name="other")
    stems = _stems([first, second, alone])
    assert stems[first.url].startswith("clip-")
    assert stems[second.url].startswith("clip-")
    assert stems[first.url] != stems[second.url]
    assert stems[alone.url] == "other"


class Answering:
    """A session that answers every request with one status."""

    def __init__(self, status: int) -> None:
        self.status = status

    def get(self, url: str, timeout: int) -> requests.Response:
        response = requests.Response()
        response.status_code = self.status
        response.url = url
        return response


@pytest.mark.parametrize(("status", "recorded"), [(404, True), (429, False), (503, False)])
def test_only_an_answer_about_the_post_is_recorded(status: int, recorded: bool) -> None:
    """A deleted post stays a link; a busy platform is asked again next build."""
    url = "https://www.youtube.com/watch?v=abc"
    doc = build([para("Headline", "TITLE"), video(url)])
    look_up(doc, cast(requests.Session, Answering(status)))
    assert (url in doc.cards) is recorded


def indented(text: str) -> JsonObject:
    """A paragraph indented with Tab, as Docs records it."""
    paragraph = para(text)
    paragraph["paragraph"]["paragraphStyle"]["indentStart"] = {"magnitude": 36, "unit": "PT"}
    return paragraph


def captions(*lines: str) -> list[JsonObject]:
    """A `Captions:` line, and its captions after it indented a paragraph each."""
    return [linked((":", None), underline="Captions"), *map(indented, lines)]


def test_captions_are_read_warned_about_and_served(tmp_path: Path) -> None:
    youtube = "https://www.youtube.com/watch?v=abc"
    bare = "https://www.youtube.com/watch?v=def"
    doc = build(
        [
            para("Headline", "TITLE"),
            # A copy with no `Captions:` line at all.
            copied(_x(1)),
            # The Lynskey video in IBX: train noise and a radio, nothing a reader needs to read.
            copied(_x(2)),
            *captions(),
            # Written captions, the first on the `Captions:` line itself.
            copied(_x(3)),
            linked((": 0:01-0:02 Hi", None), underline="Captions"),
            indented("0:04\u20130:04.7 Jesus"),
            indented("0:05.2-0:06 Look out!"),
            indented("1:02:03 --> 1:02:04.25 <loud> & clear"),
            indented("Jesus"),
            indented("0:04 Jesus"),
            indented("0:04-0:04.7: Jesus"),
            indented("0:05-0:04 Jesus"),
            # The first line not indented ends the captions, however much it looks like one.
            para("0:02-0:03 Hm"),
            video(youtube),
            *captions("0:01-0:02 Hi"),
            # YouTube's own player shows YouTube's captions.
            video(bare),
        ]
    )
    embeds = [b for b in doc.blocks if isinstance(b, Embed)]
    assert [e.captions for e in embeds] == [
        None,
        [],
        [
            Cue(1000, 2000, "Hi"),
            Cue(4000, 4700, "Jesus"),
            Cue(5200, 6000, "Look out!"),
            Cue(3723000, 3724250, "<loud> & clear"),
        ],
        [Cue(1000, 2000, "Hi")],
        None,
    ]
    assert embeds[1].uncaptioned
    assert [_text(b.content) for b in doc.blocks if isinstance(b, Paragraph)] == ["0:02-0:03 Hm"]
    assert to_vtt(embeds[2].captions or []) == (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.000\nHi\n\n"
        "00:00:04.000 --> 00:00:04.700\nJesus\n\n"
        "00:00:05.200 --> 00:00:06.000\nLook out!\n\n"
        "01:02:03.000 --> 01:02:04.250\n&lt;loud&gt; &amp; clear\n"
    )
    parsed = [str(w) for w in doc.warnings][1:]
    shape = (
        "a caption has to be a time range and what is said in it, as in `0:04\u20130:04.7 Jesus`"
    )
    assert parsed == [
        f"{shape}; leaving it out: `Jesus`",
        f"{shape}; leaving it out: `0:04 Jesus`",
        f"{shape}; leaving it out: `0:04-0:04.7: Jesus`",
        "a caption ends before it starts; leaving it out: `0:05-0:04 Jesus`",
    ]

    # What the build then serves: the written captions go beside the video as a `.vtt`,
    # replacing the automatic ones a download left in their place.
    for n in (1, 2, 3):
        doc.cards[_x(n)] = Card(author="someone", text="a post")
        doc.media_files[_x(n)] = f"embed-{n}.mp4"
    doc.cards[youtube] = Card(author="someone", text="a video")
    doc.cards[bare] = Card(author="someone", text="a video")
    doc.media_captions[_x(3)] = Captions("embed-3.vtt", automatic=True)
    write_captions(doc, tmp_path)
    assert list(doc.media_captions) == [_x(3)]
    served = doc.media_captions[_x(3)]
    assert not served.automatic
    assert (tmp_path / "videos" / served.file).read_text().startswith("WEBVTT")

    check_embeds(doc)
    assert [str(w) for w in doc.warnings][1 + len(parsed) :] == [
        f"the video `{_x(1)}` has no captions; write them after a `Captions:` line under it, "
        "each on a line of its own indented like `0:04\u20130:04.7 Jesus`, "
        "or leave `Captions:` empty if nothing said in it matters",
        f"the video `{youtube}` plays in its platform's player, "
        "which shows none of the `Captions:` under it; "
        "add `Copy` to its line for the site to serve it with them",
    ]


def test_a_downloaded_video_is_recorded_with_its_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The video is not committed, so its hash is what says it has changed."""
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")

    def written(embed: Embed, stem: str, outdir: Path, doc: object) -> str:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "embed-1.mp4").write_bytes(b"video")
        return "embed-1.mp4"

    monkeypatch.setattr("eta_publish.embeds._copied", written)
    download(doc, tmp_path)
    write_embed_index(tmp_path, doc)
    again = build([para("Headline", "TITLE"), copied(url)])
    read_embed_index(tmp_path, again)
    assert again.media_hashes[url] == hashlib.sha256(b"video").hexdigest()


def _unavailable(*args: object) -> str:
    raise ValueError("Video #1 is unavailable")


def _recorded_video(url: str) -> Document:
    """A document whose one copied video `embeds.json` records as `embed-1.mp4`, holding `video`."""
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    doc.media_hashes[url] = hashlib.sha256(b"video").hexdigest()
    return doc


def test_a_video_that_will_not_download_keeps_the_last_builds_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A platform refusing the file today is not the video gone from the page."""
    url = "https://x.com/someone/status/123"
    doc = _recorded_video(url)
    (tmp_path / VIDEO_DIR).mkdir()
    (tmp_path / VIDEO_DIR / "embed-1.mp4").write_bytes(b"video")
    monkeypatch.setattr("eta_publish.embeds._copied", _unavailable)
    download(doc, tmp_path)
    assert doc.media_files[url] == "embed-1.mp4"
    assert not [w for w in map(str, doc.warnings) if "could not download" in w]


def test_a_kept_copy_that_is_not_the_recorded_one_is_warned_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://x.com/someone/status/123"
    doc = _recorded_video(url)
    (tmp_path / VIDEO_DIR).mkdir()
    (tmp_path / VIDEO_DIR / "embed-1.mp4").write_bytes(b"another video")
    monkeypatch.setattr("eta_publish.embeds._copied", _unavailable)
    download(doc, tmp_path)
    [warning] = [w for w in map(str, doc.warnings) if "could not download" in w]
    assert "Video #1 is unavailable" in warning


def test_a_video_that_will_not_download_with_no_copy_is_warned_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://x.com/someone/status/123"
    doc = _recorded_video(url)
    monkeypatch.setattr("eta_publish.embeds._copied", _unavailable)
    download(doc, tmp_path)
    [warning] = [w for w in map(str, doc.warnings) if "could not download" in w]
    assert "Video #1 is unavailable" in warning


class _Site(requests.Session):
    """A site that serves `files`, by URL, and answers 404 for anything else."""

    def __init__(self, files: dict[str, bytes]) -> None:
        super().__init__()
        self.files = files

    @override
    def get(self, url: str | bytes, **kwargs: object) -> requests.Response:  # type: ignore[override]
        response = requests.Response()
        response.url = str(url)
        response.status_code = 200 if url in self.files else 404
        response.raw = io.BytesIO(self.files.get(str(url), b""))
        return response


SERVED = "https://site.invalid/reports/a/videos/embed-1.mp4"


def test_a_video_with_no_copy_on_disk_is_fetched_from_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh checkout has none of the videos, but the site still serves the last one pushed."""
    url = "https://x.com/someone/status/123"
    doc = _recorded_video(url)
    monkeypatch.setattr("eta_publish.embeds._copied", _unavailable)
    download(doc, tmp_path, _Site({SERVED: b"video"}), hosted="https://site.invalid/reports/a")
    assert (tmp_path / VIDEO_DIR / "embed-1.mp4").read_bytes() == b"video"
    assert not [w for w in map(str, doc.warnings) if "could not download" in w]


@pytest.mark.parametrize("served", [{}, {SERVED: b"another video"}])
def test_a_video_the_site_does_not_serve_as_recorded_is_warned_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: dict[str, bytes]
) -> None:
    url = "https://x.com/someone/status/123"
    doc = _recorded_video(url)
    monkeypatch.setattr("eta_publish.embeds._copied", _unavailable)
    download(doc, tmp_path, _Site(served), hosted="https://site.invalid/reports/a")
    assert not list((tmp_path / VIDEO_DIR).iterdir())
    [warning] = [w for w in map(str, doc.warnings) if "could not download" in w]
    assert "Video #1 is unavailable" in warning


ROLLING = """WEBVTT
Kind: captions
Language: en

00:00:02.880 --> 00:00:05.030 align:start position:0%
\x20
Hello<00:00:03.200><c> everyone.</c><00:00:03.840><c> The</c>

00:00:05.030 --> 00:00:05.040 align:start position:0%
Hello everyone. The
\x20

00:00:05.040 --> 00:00:07.190 align:start position:0%
Hello everyone. The
Department<00:00:05.680><c> would</c>
"""


SRT = "1\r\n00:00:01,000 --> 00:00:02,500\r\nHello\r\n"


@pytest.mark.parametrize(
    ("convert", "source", "expected"),
    [
        # Too Damn Loud's, as YouTube recognized them.
        (
            unrolled,
            ROLLING,
            "WEBVTT\n\n"
            "00:00:02.880 --> 00:00:05.030\nHello everyone. The\n\n"
            "00:00:05.040 --> 00:00:07.190\nDepartment would\n",
        ),
        (srt_to_vtt, SRT, "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nHello\n"),
    ],
    ids=["rolling", "subrip"],
)
def test_a_platforms_captions_become_webvtt_showing_each_line_once(
    convert: Callable[[str], str], source: str, expected: str
) -> None:
    assert convert(source) == expected


def test_captions_are_recorded_for_an_offline_build(tmp_path: Path) -> None:
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    doc.media_captions[url] = Captions("embed-1.vtt", automatic=True)
    write_embed_index(tmp_path, doc)
    again = build([para("Headline", "TITLE"), copied(url)])
    read_embed_index(tmp_path, again)
    assert again.media_captions == {url: Captions("embed-1.vtt", automatic=True)}
    assert again.cards[url] == Card(author="someone", text="a post")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs `ffmpeg`")
def test_a_video_with_no_warning_gets_its_first_frame(tmp_path: Path) -> None:
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.media_files[url] = "embed-1.mp4"
    (tmp_path / VIDEO_DIR).mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=64x36:d=1",
            str(tmp_path / VIDEO_DIR / "embed-1.mp4"),
        ],
        check=True,
    )
    write_frames(doc, tmp_path)
    assert (tmp_path / IMAGE_DIR / "embed-1.frame.jpg").stat().st_size > 0
