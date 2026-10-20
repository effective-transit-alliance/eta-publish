"""What a report's embedded videos and posts look like before anyone plays them.

A page shows a card for each: who posted it, what it says, and a thumbnail.
The platform's own player is loaded only when the reader asks for it,
so reading the report asks nothing of YouTube, X, or Bluesky.

The card is looked up once and recorded in `embeds.json`, which is committed:
an offline build writes the same card, and a post deleted since keeps the one
it had. The thumbnail and a Drive video are files, rebuilt like the images.
"""

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
lazy from yt_dlp import YoutubeDL

from .docs_json import JsonObject
from .naming import CAPTIONS_LANGUAGE, IMAGE_DIR, VIDEO_DIR, media_stem, replace_bytes
from .nodes import VIDEO_TYPES, Captions, Card, Cue, Document, Embed, Platform, Shown
lazy from .fetch import download_drive_file, drive_file_type

EMBEDS_JSON = "embeds.json"

TIMEOUT = 30

THUMBNAIL_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

GONE = frozenset({403, 404, 410})
"""What a platform answers about a post that is not there to be shown:
deleted, never was, or made private."""

PAGES_FILE_LIMIT = 100_000_000
"""The largest file GitHub Pages will publish."""

_RECORDED = frozenset({"file", "captions", "captions_automatic"})
"""What `embeds.json` records about an embed beside its card."""


def read_embed_index(dest: Path, doc: Document) -> None:
    """Tell `doc` what every embed's platform said about it, as last recorded."""
    index = dest / EMBEDS_JSON
    if not index.exists():
        return
    for url, entry in json.loads(index.read_text()).items():
        card = {k: v for k, v in entry.items() if k not in _RECORDED}
        doc.cards.setdefault(url, Card(**card))
        if entry.get("file"):
            doc.media_files.setdefault(url, entry["file"])
        if entry.get("captions"):
            captions = Captions(entry["captions"], bool(entry.get("captions_automatic")))
            doc.media_captions.setdefault(url, captions)


def write_embed_index(dest: Path, doc: Document) -> None:
    """Record the cards of the embeds the document has, and no others.

    An embed taken out of the document leaves the record with it, the way it
    leaves the page; nothing would ever read its card again.
    """
    index = dest / EMBEDS_JSON
    entries = {}
    for embed in doc.embeds:
        card = doc.cards.get(embed.url)
        if card is None:
            continue
        entry = {k: v for k, v in card.__dict__.items() if v}
        if embed.url in doc.media_files:
            entry["file"] = doc.media_files[embed.url]
        if captions := doc.media_captions.get(embed.url):
            entry["captions"] = captions.file
            if captions.automatic:
                entry["captions_automatic"] = True
        entries[embed.url] = entry
    if not entries:
        index.unlink(missing_ok=True)
        return
    index.write_text(json.dumps(entries, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def look_up(doc: Document, http: requests.Session | None = None) -> None:
    """Ask each platform about the embeds nothing has recorded a card for.

    A failure is recorded rather than raised, as the archive's are:
    X in particular answers when it feels like it, and a report is not held
    back over a thumbnail. The card falls back to the link it was.
    """
    http = http or requests.Session()
    for embed in doc.embeds:
        if embed.url in doc.cards:
            continue
        try:
            card = _describe(embed, http)
        except requests.RequestException as e:
            # Only an answer about the post is recorded. A timeout, a 429, or
            # a 5xx is about the moment, and recorded it would make the post
            # a plain link for good over one bad minute; unrecorded, the next
            # build asks again.
            status = e.response.status_code if e.response is not None else None
            if status not in GONE:
                continue
            card = Card(error=str(e))
        # Broad, because Drive's errors are its client library's own
        # and a malformed answer is a `KeyError` as often as anything.
        except Exception as e:
            card = Card(error=str(e) or type(e).__name__)
        doc.cards[embed.url] = card


def check_embeds(doc: Document) -> None:
    """Say which embeds publish as a plain link, on every build rather than the first.

    The page carries its warnings, so one said only by the build that asked
    would vanish from it on the next.
    """
    for embed in doc.embeds:
        card = doc.cards.get(embed.url)
        if card is None:
            doc.warn("nothing has looked up the embed {}; it shows as a link", Shown(embed.url))
        elif card.error:
            doc.warn(
                "could not look up the embed {} ({}); it shows as a link",
                Shown(embed.url),
                card.error,
            )
        elif embed.platform is Platform.DRIVE and not is_video(card):
            doc.warn(
                "{} is a Drive file of type {}, not a video this can play; it shows as a link",
                Shown(embed.url),
                Shown(card.mime or "unknown"),
            )
        elif not doc.served_video(embed):
            # A platform's own player shows the platform's captions, and only those.
            if embed.captions:
                doc.warn(
                    "the video {} plays in its platform's player, which shows none of "
                    "the {} under it; add {} to its line for the site to serve it with them",
                    Shown(embed.url),
                    Shown("Captions:"),
                    Shown("Copy"),
                )
        elif embed.url not in doc.media_captions and not embed.uncaptioned:
            doc.warn(
                "the video {} has no captions; write them under it after {}, "
                "a line each like {}, or leave {} empty if nothing said in it matters",
                Shown(embed.url),
                Shown("Captions:"),
                Shown("0:04\u20130:04.7 Jesus"),
                Shown("Captions:"),
            )


def _describe(embed: Embed, http: requests.Session) -> Card:
    match embed.platform:
        case Platform.YOUTUBE:
            # oEmbed rather than the Data API, which wants a key.
            found = _json(
                http,
                "https://www.youtube.com/oembed?format=json&url="
                + quote(f"https://www.youtube.com/watch?v={embed.key}", safe=""),
            )
            return Card(
                author=found["author_name"], text=found["title"], thumbnail=found["thumbnail_url"]
            )
        case Platform.X:
            # What X's own embed reads, and the one way left to read a post
            # without an account: its oEmbed answers with an empty body.
            # The token is checked for being present and nothing else.
            found = _json(
                http, f"https://cdn.syndication.twimg.com/tweet-result?id={embed.key}&token=0"
            )
            media = found.get("mediaDetails") or [{}]
            start, end = found.get("display_text_range") or (0, len(found["text"]))
            text = found["text"][start:end].strip()
            # A long post comes back cut short, with its full text somewhere
            # this cannot read, so the card says it stops rather than ending
            # mid-sentence as if that were all.
            if "note_tweet" in found:
                text += "\u2026"
            return Card(
                author=f"{found['user']['name']} (@{found['user']['screen_name']})",
                text=text,
                thumbnail=media[0].get("media_url_https", ""),
            )
        case Platform.BLUESKY:
            handle, rkey = embed.key.split("/", 1)
            did = handle
            if not did.startswith("did:"):
                did = _json(
                    http,
                    "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle="
                    + quote(handle),
                )["did"]
            uri = f"at://{did}/app.bsky.feed.post/{rkey}"
            posts = _json(
                http,
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts?uris="
                + quote(uri, safe=""),
            )["posts"]
            if not posts:
                raise ValueError("no such post")
            post = posts[0]
            author = post["author"]
            return Card(
                author=f"{author.get('displayName') or author['handle']} (@{author['handle']})",
                text=post["record"].get("text", ""),
                thumbnail=_bluesky_thumbnail(post.get("embed") or {}),
                did=did,
            )
        case Platform.DRIVE:
            return Card(mime=drive_file_type(embed.key))


def _bluesky_thumbnail(embed: JsonObject) -> str:
    """The picture a Bluesky post shows first, wherever in the embed it is kept."""
    if embed.get("thumbnail"):
        return embed["thumbnail"]
    for image in embed.get("images") or []:
        return image.get("thumb", "")
    if "media" in embed:
        return _bluesky_thumbnail(embed["media"])
    external = embed.get("external") or {}
    return external.get("thumb", "")


def _json(http: requests.Session, url: str) -> JsonObject:
    response = http.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def is_video(card: Card | None) -> bool:
    """Whether a Drive link's card says it is a video this can play."""
    return card is not None and card.mime in VIDEO_TYPES


def download(doc: Document, dest: Path, http: requests.Session | None = None) -> None:
    """Write each embed's thumbnail, and each Drive or copied video, beside the images.

    Fetched every build, as the images are, because nothing is committed to
    tell a changed file from an unchanged one. A failure warns and the card
    goes without its picture.
    """
    http = http or requests.Session()
    stems = _stems(doc.embeds)
    for embed in doc.embeds:
        card = doc.cards.get(embed.url)
        if card is None or card.error:
            continue
        stem = stems[embed.url]
        try:
            if embed.copy and embed.platform is not Platform.DRIVE:
                doc.media_files[embed.url] = _copied(embed, stem, dest / VIDEO_DIR, doc)
            elif embed.platform is Platform.DRIVE:
                if is_video(card):
                    doc.media_files[embed.url] = _video(embed, card, stem, dest / VIDEO_DIR, doc)
            elif card.thumbnail:
                doc.media_files[embed.url] = _thumbnail(card, stem, dest / IMAGE_DIR, http)
        except Exception as e:
            doc.warn("could not download what {} shows ({})", Shown(embed.url), str(e))


def write_captions(doc: Document, dest: Path) -> None:
    """Write the captions each served video has under its `Video:` line, as WebVTT beside it.

    Every build, offline too, since the doc is where they come from.
    They stand in for any the platform has: somebody wrote these for this report.
    A `Captions:` line with nothing after it takes the platform's away as well.
    """
    stems = _stems(doc.embeds)
    for embed in doc.embeds:
        if embed.captions is None or not doc.served_video(embed):
            continue
        name = f"{stems[embed.url]}.vtt"
        if not embed.captions:
            doc.media_captions.pop(embed.url, None)
            (dest / VIDEO_DIR / name).unlink(missing_ok=True)
            continue
        replace_bytes(dest / VIDEO_DIR / name, to_vtt(embed.captions).encode())
        doc.media_captions[embed.url] = Captions(name)


def to_vtt(cues: list[Cue]) -> str:
    """Written captions as a WebVTT file."""
    blocks = [f"{_timestamp(c.start)} --> {_timestamp(c.end)}\n{_vtt_text(c.text)}" for c in cues]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def _timestamp(milliseconds: int) -> str:
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def _vtt_text(text: str) -> str:
    """`text` as a cue shows it: WebVTT reads `<` as a tag and `&` as an entity."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stems(embeds: list[Embed]) -> dict[str, str]:
    """A file stem for each embed: its `Video:` link's text, or a hash of its URL.

    Two embeds whose links read alike both carry the hash too,
    decided knowing all of them, so which comes first renames neither.
    """
    names = {embed.url: media_stem(embed.name) for embed in embeds}
    claimants: dict[str, set[str]] = defaultdict(set)
    for url, name in names.items():
        if name:
            claimants[name].add(url)
    stems: dict[str, str] = {}
    for embed in embeds:
        name = names[embed.url]
        short = hashlib.sha256(embed.url.encode()).hexdigest()[:8]
        if not name:
            stems[embed.url] = f"embed-{short}"
        elif len(claimants[name]) > 1:
            stems[embed.url] = f"{name}-{short}"
        else:
            stems[embed.url] = name
    return stems


def _thumbnail(card: Card, stem: str, outdir: Path, http: requests.Session) -> str:
    response = http.get(card.thumbnail, timeout=TIMEOUT)
    response.raise_for_status()
    kind = response.headers.get("content-type", "").split(";")[0].strip()
    extension = THUMBNAIL_TYPES.get(kind)
    if extension is None:
        raise ValueError(f"the thumbnail came back as {kind or 'nothing'}")
    outdir.mkdir(parents=True, exist_ok=True)
    replace_bytes(outdir / f"{stem}{extension}", response.content)
    return f"{stem}{extension}"


def _video(embed: Embed, card: Card, stem: str, outdir: Path, doc: Document) -> str:
    data = download_drive_file(embed.key)
    _check_size(embed, len(data), doc)
    name = f"{stem}{VIDEO_TYPES[card.mime]}"
    outdir.mkdir(parents=True, exist_ok=True)
    replace_bytes(outdir / name, data)
    return name


def _copied(embed: Embed, stem: str, outdir: Path, doc: Document) -> str:
    """Download the video a `Video (Copy):` post or link plays, with `yt-dlp`.

    MP4 where the platform has it, since that is what every browser plays,
    and H.264 in it before anything newer: YouTube's best MP4 is often AV1,
    which an older iPhone does not play. Joining a separate video and audio
    stream into one takes `ffmpeg`.

    Its captions come with it where the platform has any, for the page to offer:
    `yt-dlp` finds them the same way on every site it reads.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    options = {
        "format": (
            "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]"
            "/bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(outdir / f"{stem}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "overwrites": True,
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(embed.url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
        if not path.exists():
            raise ValueError(f"{path.name} was not written")
        _check_size(embed, path.stat().st_size, doc)
        if embed.captions is not None:
            # Written in the doc, or said to be none: `write_captions` has them.
            return path.name
        doc.media_captions.pop(embed.url, None)
        (outdir / f"{stem}.vtt").unlink(missing_ok=True)
        try:
            captions = _captions(ydl, info, outdir, stem)
        except Exception as e:
            doc.warn("could not download the captions of {} ({})", Shown(embed.url), str(e))
        else:
            if captions is not None:
                doc.media_captions[embed.url] = captions
    return path.name


def _captions(ydl: YoutubeDL, info: Mapping[str, Any], outdir: Path, stem: str) -> Captions | None:
    """Write the video's captions as `<stem>.vtt`, if the platform has any in the reports' language.

    Captions somebody wrote before any the platform recognized from the speech.
    Of those, the `-orig` track is the speech as recognized,
    where a bare language can be a translation of a track in another.
    """
    for automatic, key in ((False, "subtitles"), (True, "automatic_captions")):
        tracks: dict[str, list[dict[str, Any]]] = info.get(key) or {}
        languages = [
            language
            for language in tracks
            if language == CAPTIONS_LANGUAGE or language.startswith(f"{CAPTIONS_LANGUAGE}-")
        ]
        languages.sort(key=lambda language: (not language.endswith("-orig"), language))
        for language in languages:
            formats = {track.get("ext"): track for track in tracks[language] if track.get("url")}
            if "vtt" in formats:
                text = ydl.urlopen(formats["vtt"]["url"]).read().decode("utf-8-sig")
            elif "srt" in formats:
                text = srt_to_vtt(ydl.urlopen(formats["srt"]["url"]).read().decode("utf-8-sig"))
            else:
                continue
            if not text.lstrip().startswith("WEBVTT"):
                continue
            name = f"{stem}.vtt"
            # Only recognized captions roll; written ones are kept as written.
            replace_bytes(outdir / name, (unrolled(text) if automatic else text).encode())
            return Captions(name, automatic)
    return None


def srt_to_vtt(srt: str) -> str:
    """SubRip as WebVTT, which differs in its header and its decimal comma."""
    body = re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", srt.replace("\r\n", "\n"))
    return f"WEBVTT\n\n{body.strip()}\n"


_TIMING = re.compile(r"^(\S+ --> \S+)")
_TAG = re.compile(r"<[^>]*>")


def _seconds(timestamp: str) -> float:
    parts = [float(part) for part in timestamp.split(":")]
    return sum(part * 60**power for power, part in enumerate(reversed(parts)))


def unrolled(vtt: str) -> str:
    """Captions with one cue a line, from YouTube's rolling ones.

    YouTube's recognized captions scroll: each cue repeats the line before it
    over the one being spoken, timed word by word, with a cue a hundredth of a second long
    between each pair to hold the finished line. Played in a browser, every line shows twice.
    Each cue here is only what it adds, with the word timings dropped.
    Captions that do not roll come through with only their cue settings dropped.
    """
    cues: list[tuple[str, list[str]]] = []
    # Split only at an empty line: YouTube's rolling cues open with a line of one space.
    for block in re.split(r"\n\n+", vtt.replace("\r\n", "\n")):
        lines = block.strip("\n").split("\n")
        timed = next((n for n, line in enumerate(lines) if "-->" in line), None)
        if timed is None:
            continue
        timing = _TIMING.match(lines[timed])
        if timing is None:
            continue
        start, _, end = timing.group(1).partition(" --> ")
        if _seconds(end) - _seconds(start) < 0.05:
            continue
        text = [_TAG.sub("", line).strip() for line in lines[timed + 1 :]]
        text = [line for line in text if line]
        if cues and len(text) > 1 and text[0] == cues[-1][1][-1]:
            text = text[1:]
        if text:
            cues.append((timing.group(1), text))
    body = "\n\n".join("\n".join([timing, *text]) for timing, text in cues)
    return f"WEBVTT\n\n{body}\n"


def _check_size(embed: Embed, size: int, doc: Document) -> None:
    if size > PAGES_FILE_LIMIT:
        doc.warn(
            f"the video {{}} is {size:,} bytes, over the {PAGES_FILE_LIMIT:,} bytes "
            "GitHub Pages will publish; the deploy will fail until it is smaller",
            Shown(embed.url),
        )
