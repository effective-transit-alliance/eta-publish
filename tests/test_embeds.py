"""Videos and posts, from a paragraph that is nothing but a link to one."""

from pathlib import Path
from typing import cast

import pytest
import requests
from test_conventions import build, field, image, para

from eta_publish.docs_json import JsonObject
from eta_publish.embeds import (
    _stems,
    check_embeds,
    look_up,
    read_embed_index,
    srt_to_vtt,
    unrolled,
    write_embed_index,
)
from eta_publish.emit.html import GRAPHIC_POSTER, HtmlEmitter
from eta_publish.emit.markdown import MarkdownEmitter
from eta_publish.nodes import Captions, Card, Embed, Figure, Paragraph, Platform, Text
from eta_publish.parse import embedded


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


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("https://www.youtube.com/watch?v=KDaRRmUWUZI", (Platform.YOUTUBE, "KDaRRmUWUZI", 0)),
        ("https://www.youtube.com/live/HEfH7R6j6QY?t=911s", (Platform.YOUTUBE, "HEfH7R6j6QY", 911)),
        ("https://youtu.be/h6-MVzb58E4?si=rJ&t=137", (Platform.YOUTUBE, "h6-MVzb58E4", 137)),
        ("https://youtube.com/shorts/o90JQBWdgTI?is=I4", (Platform.YOUTUBE, "o90JQBWdgTI", 0)),
        ("https://www.youtube.com/watch?v=abc&t=1h2m3s", (Platform.YOUTUBE, "abc", 3723)),
        (
            "https://x.com/ThoughtPolic3HQ/status/1874861375857541619/video/1",
            (Platform.X, "1874861375857541619", 0),
        ),
        ("https://twitter.com/someone/status/123", (Platform.X, "123", 0)),
        (
            "https://bsky.app/profile/bsky.app/post/3l6oveex3ii2l",
            (Platform.BLUESKY, "bsky.app/3l6oveex3ii2l", 0),
        ),
        ("https://drive.google.com/file/d/1abc/view?usp=drive_link", (Platform.DRIVE, "1abc", 0)),
        ("https://www.youtube.com/@MrRailfan", None),
        ("https://x.com/ThoughtPolic3HQ", None),
        ("https://www.mta.info/document/196361", None),
    ],
)
def test_what_a_link_is_a_link_to(href: str, expected: tuple[Platform, str, int] | None) -> None:
    assert embedded(href) == expected


def test_a_video_line_is_embedded() -> None:
    url = "https://x.com/ThoughtPolic3HQ/status/1874861375857541619/video/1"
    doc = build([para("Headline", "TITLE"), linked((": ", None), (url, url), underline="Video")])
    assert doc.blocks == [Embed(url=url, platform=Platform.X, key="1874861375857541619")]


def test_a_graphic_video_line_is_embedded_with_a_warning() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    doc = build(
        [
            para("Headline", "TITLE"),
            linked((": ", None), (url, url), underline="Video (Graphic Warning)"),
        ]
    )
    assert doc.blocks == [Embed(url=url, platform=Platform.YOUTUBE, key="abc", graphic=True)]


def test_a_video_line_ended_with_a_full_stop_is_still_a_video() -> None:
    """The stop is not part of the link: it ends the caption, as it ends others,
    but not the file's name, which is the linked words alone."""
    url = "https://x.com/someone/status/123"
    doc = build(
        [
            para("Headline", "TITLE"),
            linked((": ", None), ("Hit by the train", url), (".", None), underline="Video (Copy)"),
        ]
    )
    assert doc.blocks == [
        Embed(
            url=url,
            platform=Platform.X,
            key="123",
            copy=True,
            title="Hit by the train.",
            name="Hit by the train",
        )
    ]


def test_an_unknown_modifier_is_warned_about_and_ignored() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    doc = build(
        [
            para("Headline", "TITLE"),
            linked((": ", None), (url, url), underline="Video (graphic warning, Grafic)"),
        ]
    )
    assert doc.blocks == [Embed(url=url, platform=Platform.YOUTUBE, key="abc", graphic=True)]
    warnings = [str(w) for w in doc.warnings if "not a modifier" in str(w)]
    assert len(warnings) == 1
    assert "Grafic" in warnings[0]


def test_a_titled_link_is_embedded() -> None:
    """Too Damn Loud's video, which Docs shows by its title rather than its address."""
    url = "https://youtube.com/shorts/o90JQBWdgTI?is=I4"
    doc = build(
        [para("Headline", "TITLE"), linked((": ", None), ("Too Damn Loud", url), underline="Video")]
    )
    embed = doc.blocks[0]
    assert isinstance(embed, Embed)
    assert embed.vertical


def test_a_video_line_right_under_a_figure_is_not_its_caption() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    doc = build(
        [para("Headline", "TITLE"), image(), linked((": ", None), (url, url), underline="Video")]
    )
    assert isinstance(doc.blocks[0], Figure)
    assert not doc.blocks[0].caption
    assert doc.blocks[1] == Embed(url=url, platform=Platform.YOUTUBE, key="abc")


def test_a_link_on_a_line_of_its_own_is_a_citation() -> None:
    """Without the label, a pasted link is a link: nothing says it is meant to play."""
    url = "https://x.com/ThoughtPolic3HQ/status/1874861375857541619/video/1"
    doc = build([para("Headline", "TITLE"), linked((url, url))])
    assert isinstance(doc.blocks[0], Paragraph)


def test_a_video_line_without_a_video_is_text_and_said() -> None:
    doc = build([para("Headline", "TITLE"), linked((": coming soon", None), underline="Video")])
    assert isinstance(doc.blocks[0], Paragraph)
    assert any("Video:" in str(w) for w in doc.warnings)


def test_a_link_in_a_sentence_is_a_citation() -> None:
    """IBX cites the same press conference three times, on the words of a sentence."""
    url = "https://www.youtube.com/watch?v=HEfH7R6j6QY"
    doc = build(
        [para("Headline", "TITLE"), linked(("The MTA ", None), ("announced", url), (" it.", None))]
    )
    assert isinstance(doc.blocks[0], Paragraph)


def test_a_credit_linked_to_a_video_stays_a_credit() -> None:
    """SAS West credits a still to the board meeting it was taken from,
    with the whole `Credit: MTA` linked to the video."""
    url = "https://www.youtube.com/live/syjWBXSAbyM?t=2940s"
    doc = build(
        [
            para("Headline", "TITLE"),
            image(),
            para("The tail tracks the MTA proposed."),
            linked((": MTA", url), underline="Credit"),
        ]
    )
    figure = doc.blocks[0]
    assert isinstance(figure, Figure)
    assert figure.credit
    assert not doc.embeds


def card_page(platform: Platform, url: str, key: str, card: Card | None) -> tuple[str, str]:
    doc = build([para("Headline", "TITLE"), video(url)])
    assert doc.embeds == [Embed(url=url, platform=platform, key=key)]
    if card is not None:
        doc.cards[url] = card
    doc.media_files[url] = "embed-1.jpg"
    return HtmlEmitter(image_base="images").emit(doc), MarkdownEmitter().emit(doc)


def test_a_card_loads_nothing_until_clicked() -> None:
    url = "https://bsky.app/profile/bsky.app/post/3l6oveex3ii2l"
    html, markdown = card_page(
        Platform.BLUESKY,
        url,
        "bsky.app/3l6oveex3ii2l",
        Card(author="Bluesky (@bsky.app)", text="Hello", did="did:plc:z72"),
    )
    assert (
        'data-player="https://embed.bsky.app/embed/did:plc:z72/app.bsky.feed.post/3l6oveex3ii2l"'
        in html
    )
    assert f'class="embed-card" href="{url}"' in html
    assert 'src="images/embed-1.jpg"' in html
    assert "<iframe" not in html
    assert "[Bluesky (@bsky.app) on Bluesky: “Hello”]" in markdown


def test_an_embeds_source_has_a_box_on_hover() -> None:
    """The script hangs a source's box off a `cited`,
    and IBX's X post's `[39]` had none to hang it off."""
    html, _ = card_page(
        Platform.X, "https://x.com/someone/status/123", "123", Card(author="Someone", text="Hi")
    )
    assert '<span class="cited"><sup class="source-ref"' in html


def test_an_embed_nothing_could_describe_is_the_link_it_was() -> None:
    url = "https://x.com/someone/status/123"
    html, markdown = card_page(Platform.X, url, "123", Card(error="404"))
    assert 'class="embed-card"' not in html
    assert f"[{url}](<{url}>)" in markdown


def test_a_drive_video_plays_from_the_site() -> None:
    url = "https://drive.google.com/file/d/1abc/view"
    doc = build([para("Headline", "TITLE"), video(url)])
    doc.cards[url] = Card(mime="video/mp4")
    doc.media_files[url] = "embed-1.mp4"
    html = HtmlEmitter(image_base="images").emit(doc)
    assert '<video src="videos/embed-1.mp4" controls preload="metadata"' in html


def copied(url: str) -> JsonObject:
    """A `Video (Graphic Warning, Copy):` line."""
    return linked((": ", None), (url, url), underline="Video (Graphic Warning, Copy)")


def test_a_copied_video_plays_from_the_site() -> None:
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    assert doc.blocks == [Embed(url=url, platform=Platform.X, key="123", graphic=True, copy=True)]
    assert not [w for w in doc.warnings if "not a modifier" in str(w)]
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    html = HtmlEmitter(image_base="images").emit(doc)
    assert '<video src="videos/embed-1.mp4" controls preload="metadata"' in html


def test_a_graphic_video_opens_on_the_warning_card() -> None:
    """Rather than on its first frame, which may be the very thing warned of."""
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    html = HtmlEmitter(image_base="images").emit(doc)
    assert f'poster="{GRAPHIC_POSTER}"' in html


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


def test_a_copied_video_is_a_figure_like_an_image() -> None:
    """Named and captioned as an image is, with nothing of the post it came from:
    its anchor is its file's name, its `#` is on the figure,
    and the warning is a notice of its own."""
    url = "https://x.com/someone/status/123"
    line = linked(
        (": ", None), ("Hit by the 1 train", url), underline="Video (Graphic Warning, Copy)"
    )
    doc = build([para("Headline", "TITLE"), line])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "Hit_by_the_1_train.mp4"
    html = HtmlEmitter(image_base="images").emit(doc)
    assert '<p class="embed-warning" role="note">Warning, graphic video</p>' in html
    assert '<figure id="Hit_by_the_1_train"><a class="link-mark"' in html
    assert '<figcaption class="figure-caption">Hit by the 1 train</figcaption>' in html
    assert "embed" not in html[html.index("<figure") : html.index("</figure>")].replace(
        "embed-warning", ""
    )
    assert "x.com" not in html
    markdown = MarkdownEmitter().emit(doc)
    # Ours, so named as the document names it and linked to our copy.
    link = "[Hit by the 1 train](<videos/Hit_by_the_1_train.mp4>)"
    assert f"**Warning, graphic video**\n\n{link}" in markdown


def test_a_video_takes_a_credit_line_as_a_figure_does() -> None:
    url = "https://x.com/someone/status/123"
    line = linked((": ", None), ("Hit by the 1 train", url), underline="Video (Copy)")
    doc = build([para("Headline", "TITLE"), line, field("Credit: ETA (Khyber Sen)")])
    (embed,) = doc.blocks
    assert isinstance(embed, Embed)
    assert (
        "".join(i.text for i in embed.credit if isinstance(i, Text)) == "Credit: ETA (Khyber Sen)"
    )
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "Hit_by_the_1_train.mp4"
    html = HtmlEmitter(image_base="images").emit(doc)
    assert '<figcaption class="figure-credit">Credit: ETA (Khyber Sen)</figcaption>' in html
    assert "Credit: ETA (Khyber Sen)" in MarkdownEmitter().emit(doc)


def test_a_copy_that_failed_shows_its_card() -> None:
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.jpg"
    html = HtmlEmitter(image_base="images").emit(doc)
    assert "<video " not in html
    assert 'src="images/embed-1.jpg"' in html


def test_a_drive_file_that_is_not_a_video_is_a_link() -> None:
    url = "https://drive.google.com/file/d/1abc/view"
    doc = build([para("Headline", "TITLE"), video(url)])
    doc.cards[url] = Card(mime="image/png")
    assert "<video " not in HtmlEmitter(image_base="images").emit(doc)


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


def test_a_served_video_with_no_captions_is_warned_about() -> None:
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    check_embeds(doc)
    [warning] = [w for w in map(str, doc.warnings) if "no captions" in w]
    assert "`Video (Copy, No Captions):`" in warning


def test_a_video_marked_no_captions_is_not_warned_about() -> None:
    """The Lynskey video in IBX: train noise and a radio, nothing a reader needs to read."""
    url = "https://x.com/someone/status/123"
    line = linked((": ", None), (url, url), underline="Video (Graphic Warning, Copy, No Captions)")
    doc = build([para("Headline", "TITLE"), line])
    assert not [w for w in doc.warnings if "not a modifier" in str(w)]
    (embed,) = doc.blocks
    assert isinstance(embed, Embed) and embed.uncaptioned
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    check_embeds(doc)
    assert not [w for w in map(str, doc.warnings) if "no captions" in w]


def test_a_platform_player_is_not_warned_about_captions() -> None:
    """YouTube's own player shows YouTube's captions."""
    url = "https://www.youtube.com/watch?v=abc"
    doc = build([para("Headline", "TITLE"), linked((": ", None), (url, url), underline="Video")])
    doc.cards[url] = Card(author="someone", text="a video")
    check_embeds(doc)
    assert not [w for w in map(str, doc.warnings) if "no captions" in w]


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


def test_rolling_captions_show_each_line_once() -> None:
    """Too Damn Loud's, as YouTube recognized them."""
    assert unrolled(ROLLING) == (
        "WEBVTT\n\n"
        "00:00:02.880 --> 00:00:05.030\nHello everyone. The\n\n"
        "00:00:05.040 --> 00:00:07.190\nDepartment would\n"
    )


def test_subrip_captions_become_webvtt() -> None:
    srt = "1\r\n00:00:01,000 --> 00:00:02,500\r\nHello\r\n"
    assert srt_to_vtt(srt) == "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nHello\n"


def test_a_copy_offers_its_captions() -> None:
    url = "https://x.com/someone/status/123"
    doc = build([para("Headline", "TITLE"), copied(url)])
    doc.cards[url] = Card(author="someone", text="a post")
    doc.media_files[url] = "embed-1.mp4"
    doc.media_captions[url] = Captions("embed-1.vtt", automatic=True)
    html = HtmlEmitter(image_base="images").emit(doc)
    assert (
        '<track kind="captions" src="videos/embed-1.vtt" srclang="en" label="English (automatic)">'
        in html
    )
    check_embeds(doc)
    assert not [w for w in map(str, doc.warnings) if "no captions" in w]


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
