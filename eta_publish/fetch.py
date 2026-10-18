"""Fetch a Google Doc as raw Docs API JSON.

The Docs API rather than Drive's HTML export:
the export is `<span class="c12">` soup with no semantics,
where the API JSON carries real named paragraph styles,
first-class `footnotes`, and `inlineObjects`.

Tabs are the subtle part.
ETA reports live in multi-tab documents,
and by default `documents.get` fills `document.body` from the *first tab only*
and leaves `document.tabs` empty,
so a report drafted in the third tab parses silently into a plausible, wrong document.
So we always request `includeTabsContent` and select a tab explicitly,
honoring the `?tab=` id in the URL handed to us.

Suggestions matter for the same reason.
The default, `DEFAULT_FOR_CURRENT_ACCESS`,
resolves to `SUGGESTIONS_INLINE` for anyone with edit access,
mixing suggested text into the content as though it were part of the document.
ETA reports are drafted with suggestions open,
so we ask for `PREVIEW_WITHOUT_SUGGESTIONS`: what the doc reads as today.
"""

import hashlib
import json
import os
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

lazy import google.auth
lazy from google.auth.credentials import Credentials
lazy from google.auth.exceptions import DefaultCredentialsError, RefreshError
lazy from google.auth.transport.requests import AuthorizedSession, Request
lazy from google.oauth2.credentials import Credentials as UserCredentials
lazy from google_auth_oauthlib.flow import InstalledAppFlow
lazy from googleapiclient.discovery import build
lazy from googleapiclient.errors import HttpError

from . import console
from .docs_json import JsonObject
from .nodes import Shown

SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    # Charts are linked as Drive files rather than embedded, since Docs cannot
    # place an SVG. Downloading one needs Drive read access, and Drive offers
    # nothing narrower for a file this application did not create.
    "https://www.googleapis.com/auth/drive.readonly",
]

# Rejecting is the safe default: it publishes what the document currently says,
# rather than silently adopting whatever anyone has proposed.
SUGGESTIONS = {
    "rejected": "PREVIEW_WITHOUT_SUGGESTIONS",
    "accepted": "PREVIEW_SUGGESTIONS_ACCEPTED",
    # Not a mode the command line offers: it is how suggestions are counted,
    # which is the only way to know there are any.
    "inline": "SUGGESTIONS_INLINE",
}

CLIENT_SECRETS = Path(
    os.environ.get("ETA_CLIENT_SECRETS", Path.home() / ".config/eta-publish/client_secret.json")
)
TOKEN_PATH = Path(os.environ.get("ETA_TOKEN", Path.home() / ".config/eta-publish/token.json"))


class TabNotFound(LookupError):
    pass


class FetchFailed(RuntimeError):
    """A Docs API request failed for a reason the user can act on."""


def _explain(error: object) -> str:
    """Turn a Google API error into something with a next step in it.

    `HttpError`'s own string is a wall of JSON with the useful sentence buried in it,
    and the failures worth naming here have a specific fix.
    """
    if not isinstance(error, HttpError):
        return str(error)

    details = [d for d in (getattr(error, "error_details", None) or []) if isinstance(d, dict)]
    reasons = {str(d.get("reason", "")) for d in details}
    messages = [str(d.get("message", "")) for d in details if d.get("message")]

    # An API not switched on for the project:
    # `SERVICE_DISABLED` from Docs, `accessNotConfigured` from Drive.
    # Both put the console URL in the message, so pass Google's own wording along.
    if reasons & {"SERVICE_DISABLED", "accessNotConfigured"}:
        enable = next((m for m in messages if "has not been used in project" in m), "")
        return enable or "an API this needs is not enabled for the OAuth project."

    status = error.status_code
    if status == 403:
        if "insufficient" in " ".join(messages).lower() or "ACCESS_TOKEN_SCOPE" in str(error):
            return (
                "the saved authorization does not cover this. "
                f"Delete {TOKEN_PATH} and run again to grant it."
            )
        return (
            "access denied. Either the account you authorized cannot open this, "
            f"or an API is not enabled for the OAuth project.\n{error.reason}"
        )
    if status == 404:
        return "not found, or the account you authorized cannot open it."
    if status == 429:
        return "rate limited by the API; wait a minute and try again."
    return f"the API returned {status}: {error.reason}"


def parse_ref(ref: str) -> tuple[str, str | None]:
    """Split a Docs URL into its document id and its `?tab=` id, if any.

    A bare document id is accepted unchanged.
    """
    if "docs.google.com" not in ref:
        return ref, None
    url = urlparse(ref)
    doc_id = url.path.split("/d/", 1)[1].split("/", 1)[0]
    tab_id = parse_qs(url.query).get("tab", [None])[0]
    return doc_id, tab_id


# ---- tabs ----------------------------------------------------------


def iter_tabs(tabs: list[JsonObject], depth: int = 0) -> Iterator[tuple[int, JsonObject]]:
    """Yield `(depth, tab)` for every tab, descending into child tabs."""
    for tab in tabs:
        yield depth, tab
        yield from iter_tabs(tab.get("childTabs", []), depth + 1)


def tab_title(tab: JsonObject) -> str:
    return tab.get("tabProperties", {}).get("title", "(untitled)")


def tab_id(tab: JsonObject) -> str:
    return tab.get("tabProperties", {}).get("tabId", "")


def describe_tabs(document: JsonObject) -> str:
    return "\n".join(
        f"  {'  ' * depth}{tab_id(tab)}  {tab_title(tab)}"
        for depth, tab in iter_tabs(document.get("tabs", []))
    )


TAB_CONTENT_KEYS = (
    "body",
    "documentStyle",
    "footers",
    "footnotes",
    "headers",
    "inlineObjects",
    "lists",
    "namedRanges",
    "namedStyles",
    "positionedObjects",
)
"""Everything a `documentTab` holds, kept whether or not anything reads it yet.

The parser reads four of these. The rest are saved because a response is
the document as it was, and a build that wants one of them later should not
need the document re-fetched to find out what it said: `positionedObjects`
is the floating image an inline one is not, `headers` and `footers` are the
page furniture, and `namedStyles` is what the style names on each paragraph
are defined as.

Written with an empty default rather than left out where a document has none,
so every saved response is the same shape and `RESPONSE_FORMAT` means something.
"""

RESPONSE_KEYS = (
    *TAB_CONTENT_KEYS,
    "documentId",
    "tabId",
    "tabTitle",
    "title",
    "url",
)
"""Every key `select_tab` writes, which is what a saved response is made of.

Kept here rather than read off one, because the point is to notice
when it changes: `test_a_saved_response_says_what_shape_it_is`
fails the moment `select_tab` writes a key this does not list,
and updating this is what invalidates the responses saved in the old shape.

Not the keys added afterwards. `modifiedTime`, `suggestions`, `openComments`,
and `openSuggestions` are written by `fetch` and some of them only sometimes,
so a `--no-comments` run would otherwise look like a different shape.
"""

RESPONSE_FORMAT = hashlib.sha256(",".join(RESPONSE_KEYS).encode()).hexdigest()[:8]
"""What the shape above comes to, recorded in every response written in it.

A saved response in an older shape is missing whatever was added since,
and reusing it publishes a report built from half a document.
That is not something Drive can be asked about: the document did not change,
the code did. So the response says which shape it is,
and a build reuses only what it would have written itself.
"""


def document_url(doc_id: str, tab: str = "") -> str:
    """The URL of a document, or of one of its tabs, spelled one way.

    Built from the ids rather than kept from whatever was passed in,
    which can be a bare document id, a local path to a saved response,
    or a URL spelled `/edit`, `/view`, or however it was copied.

    Not what a saved response is matched by, which is the pair of ids:
    this is for whoever opens `doc.json` and wants the document it came from.
    """
    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return f"{url}?tab={tab}" if tab else url


def select_tab(document: JsonObject, wanted: str | None) -> JsonObject:
    """Return one tab's content, shaped like a single-tab document.

    The parser only sees `body`, `footnotes`, `inlineObjects`, and `lists`,
    so a tab and a document are interchangeable to it.
    Every other `documentTab` key is saved alongside them even though
    nothing reads it yet: see `TAB_CONTENT_KEYS`.

    What is left behind is the document around the tab rather than the tab:
    the other tabs, `revisionId`, which is for writing and this never writes,
    and `suggestionsViewMode`, which the response records as `suggestions`
    in the terms this build asked in.
    """
    tabs = list(iter_tabs(document.get("tabs", [])))
    if not tabs:
        # A document with no tabs at all still populates `body` directly.
        return document

    if wanted is None:
        if len(tabs) > 1:
            raise TabNotFound(
                f"this document has {len(tabs)} tabs; pass the URL including "
                f"the `?tab=` id of the one to publish:\n{describe_tabs(document)}"
            )
        chosen = tabs[0][1]
    else:
        matches = [tab for _, tab in tabs if tab_id(tab) == wanted]
        if not matches:
            raise TabNotFound(
                f"no tab `{wanted}` in this document; available tabs:\n{describe_tabs(document)}"
            )
        chosen = matches[0]

    content = chosen.get("documentTab", {})
    doc_id = str(document.get("documentId", ""))
    return {
        # Which shape this is, so a build that writes a different one
        # fetches rather than reusing a response missing what it now needs.
        "format": RESPONSE_FORMAT,
        # Which document and which tab this was, so a saved response says what
        # it is. Nothing else does: the outputs beside it are named after the
        # report's own `URL:` line, which is a path and not an id.
        "documentId": doc_id,
        "tabId": tab_id(chosen),
        # The same two, as the link that opens them.
        "url": document_url(doc_id, tab_id(chosen)),
        "title": document.get("title", ""),
        "tabTitle": tab_title(chosen),
        **{key: content.get(key, {}) for key in TAB_CONTENT_KEYS},
    }


# ---- api -----------------------------------------------------------


_SIGNING_IN = Lock()
"""Held while the answer is being worked out, and not while it is being used.

Reports are built in parallel, and the cache alone does not stop two threads
that both miss it from both running the flow: on a machine with no saved token
that is two browser windows asking for the same consent, and the second
overwrites what the first wrote.
"""


def _credentials() -> Credentials:
    """The credentials to call the API with, worked out once per process."""
    with _SIGNING_IN:
        return _sign_in()


@cache
def _sign_in() -> Credentials:
    """Whatever this machine has to offer, interactive or not.

    Cached because nothing about it can change while a build runs,
    where a build of two reports otherwise re-reads and re-checks the token
    six times. `cache_clear` is what a test uses to be given a different answer.

    On a person's machine, the installed-app flow: a browser opens once, the token caches.
    Unattended, notably CI, there is no browser to open and no one to click,
    so a service account is used through `google.auth.default`.

    Those are checked first, because a machine that has them has them deliberately:
    they are set by an environment variable naming a key file, not found by accident.
    """
    ambient = _ambient_credentials()
    if ambient is not None:
        return ambient

    creds = None
    if TOKEN_PATH.exists() and _granted_scopes() >= set(SCOPES):
        creds = UserCredentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            # A revoked or expired refresh token is exactly the case consent
            # has to be given again, so fall through to the flow below.
            reason = e.args[0] if e.args else e
            console.write(
                console.note(
                    f"the saved sign-in is no longer valid ({reason}); asking for it again"
                ),
            )
            creds = None
    if not creds or not creds.valid:
        missing = set(SCOPES) - _granted_scopes()
        if TOKEN_PATH.exists() and missing:
            console.write(
                console.note(
                    "asking for access again, because this now needs {}",
                    Shown(", ".join(sorted(missing))),
                ),
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
        # It prints the link to sign in at itself, which a bar would draw over.
        with console.paused():
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def _ambient_credentials() -> Credentials | None:
    """Service account credentials, when the environment supplies them.

    `None` when it does not,
    so the interactive flow stays the default for someone running this by hand.

    A service account reaches only what has been shared with it,
    which is why CI can be given one.
    """
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return None

    try:
        creds, _ = google.auth.default(scopes=SCOPES)
    except DefaultCredentialsError as e:
        raise FetchFailed(
            "$GOOGLE_APPLICATION_CREDENTIALS is set but the credentials it "
            f"names could not be loaded: {e}"
        ) from e
    return creds


def _granted_scopes() -> set[str]:
    """What the saved token was actually granted.

    From the file rather than from `Credentials`,
    whose `scopes` are whatever was passed to the loader, not what was consented to.
    Adding a scope must trigger a new consent, and the object would always answer yes.
    """
    try:
        return set(json.loads(TOKEN_PATH.read_text()).get("scopes") or ())
    except OSError, ValueError:
        return set()


def fetch_document(doc_id: str, suggestions: str = "rejected") -> JsonObject:
    """The whole document, every tab included, suggestions resolved."""
    service = build("docs", "v1", credentials=_credentials())
    # `build` returns a `Resource` whose methods are generated at runtime
    # from the API's discovery document, so no static type knows about `documents`.
    documents = service.documents()  # pyrefly: ignore[missing-attribute]
    request = documents.get(
        documentId=doc_id,
        includeTabsContent=True,
        suggestionsViewMode=SUGGESTIONS[suggestions],
    )
    try:
        return request.execute()
    except Exception as e:
        raise FetchFailed(_explain(e)) from e


SUGGESTION_KEYS = (
    "suggestedInsertionIds",
    "suggestedDeletionIds",
    "suggestedTextStyleChanges",
    "suggestedParagraphStyleChanges",
    "suggestedBulletChanges",
    "suggestedPositionedObjectPropertiesChanges",
    "suggestedInlineObjectPropertiesChanges",
)
"""Where a suggestion leaves its id, whatever kind of change it is.

The insertion and deletion keys hold a list of ids;
the rest hold an object keyed by id.
Both are read for their ids and not for what they say,
because the question is how many suggestions are open rather than what they propose.
"""


def open_suggestions(doc_id: str, tab: str | None = None) -> int | None:
    """How many suggestions are still open on `tab`.

    A second request, because the first cannot answer it:
    the build asks for `PREVIEW_WITHOUT_SUGGESTIONS`, which resolves them away
    and leaves nothing behind to count.

    Counted by id rather than by occurrence.
    One suggestion touching a sentence marks every run in it,
    which is 240 insertion marks for a document with far fewer suggestions in it.

    Reading them needs more than reading the document does:
    an account with view access, which is what CI's service account is,
    is told it does not have permission.
    That is a question this cannot answer rather than a build that cannot run,
    so it is `None` and the caller keeps whatever the last answer was.
    """
    try:
        document = fetch_document(doc_id, suggestions="inline")
    except FetchFailed:
        return None
    return len(_suggestion_ids(select_tab(document, tab)))


def _suggestion_ids(node: object) -> set[str]:
    """Every suggestion id anywhere under `node`."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key not in SUGGESTION_KEYS:
                found |= _suggestion_ids(value)
            elif isinstance(value, (list, dict)):
                # A list of ids, or an object keyed by them:
                # iterating either yields the ids, which is all that is wanted.
                found.update(str(i) for i in value)
    elif isinstance(node, list):
        for item in node:
            found |= _suggestion_ids(item)
    return found


EXPORT_ATTEMPTS = 3
"""How many times to ask for a tab's text before giving up on it.

The export answers an ordinary request with a sign-in page often enough
that one failure says nothing about the next.
"""


def open_comments_on_tab(doc_id: str, tab: str | None) -> int | None:
    """How many comment threads are open on `tab`, or `None` if that cannot be read.

    Neither API carries this.
    Drive holds the comments but knows nothing about tabs,
    and its anchors are opaque ids that appear nowhere in the Docs response,
    so there is nothing to join the two on.
    The document's own text export takes a `tab` parameter and lists,
    after the text, the comments left on that tab, which is the answer.

    It is not an API, and it does not always answer:
    often enough it returns a sign-in page instead, with a 200 beside it,
    and a run that took that at its word would report a document under review
    as clean. Hence the shape check, the retries,
    and `None` rather than a zero this cannot stand behind.
    """
    session = AuthorizedSession(_credentials())
    url = f"https://docs.google.com/document/d/{doc_id}/export"
    params = {"format": "txt"}
    if tab:
        params["tab"] = tab

    for _ in range(EXPORT_ATTEMPTS):
        response = session.get(url, params=params, timeout=180)
        text = response.text
        # The export writes a byte order mark and then the document.
        # Anything else is not the document, whatever the status says.
        if response.status_code == 200 and text.startswith("\ufeff"):
            # Each comment on the tab is listed after the text as `[a] what it says`.
            return len(re.findall(r"^\[[a-z]+\]", text, re.MULTILINE))
    return None


def modified_time(doc_id: str) -> str | None:
    """When Drive last saw this document edited, or `None` if it will not say.

    The cheapest question there is about a document: half a second,
    against two for the document itself and another two for its suggestions.
    Proposing, accepting, or rejecting a suggestion is editing, so a document
    that has not moved has the same text and suggestions as the last build saw.

    Comments are not editing, and do not move it. They are counted every time.

    `None` rather than a raised error: not knowing whether a document changed
    is a reason to fetch it, which is what this was trying to avoid
    and not something it may decide against.
    """
    try:
        service = build("drive", "v3", credentials=_credentials())
        files = service.files()  # pyrefly: ignore[missing-attribute]
        return files.get(fileId=doc_id, fields="modifiedTime").execute().get("modifiedTime")
    except Exception:
        # Broad on purpose, and building the client is inside it:
        # every way of not getting an answer is the same answer here,
        # which is that this build does not know and will fetch.
        return None


def unchanged(doc_id: str, cached: Path, suggestions: str) -> JsonObject | None:
    """The saved response, if it is of this document as this build wants it.

    Three questions, and a no to any of them is a fetch.
    Whether the document has been edited since, which Drive answers.
    Whether it was saved with the suggestions resolved the way this run
    resolves them, which `modifiedTime` cannot see and the response itself says.
    And whether it is the shape a build writes today,
    because a response saved before a key was added is missing that key,
    and no amount of asking Drive would turn that up.

    `None` for a saved response that is missing, unreadable, or was written
    before a build recorded what it is of: all reasons to fetch.
    """
    try:
        document = json.loads(cached.read_text())
    except OSError, ValueError:
        return None
    if not isinstance(document, dict):
        return None
    was = document.get("modifiedTime")
    if not was or document.get("suggestions") != suggestions:
        return None
    if document.get("format") != RESPONSE_FORMAT:
        # Written by an older version of this code, in a shape it no longer
        # writes. The document did not change; what a build makes of it did.
        return None
    return document if was == modified_time(doc_id) else None


def fetch(
    ref: str,
    tab: str | None = None,
    suggestions: str = "rejected",
    comments: bool = True,
    cached: Path | None = None,
) -> JsonObject:
    doc_id, url_tab = parse_ref(ref)
    wanted = tab or url_tab
    ambient = _ambient_credentials() is not None
    # The questions about a document overlap, because none of them waits on
    # another's answer and each is most of a second to Google and back.
    # Two workers: the comments and the suggestions, alongside the document
    # this thread asks for itself.
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Not asked when the caller said not to, and a key left out is a key
        # `carry_over_review` fills in from the last build that did ask,
        # which is the same shape as being unable to ask.
        counting = (
            pool.submit(open_comments_on_tab, doc_id, wanted) if comments and not ambient else None
        )
        document = unchanged(doc_id, cached, suggestions) if cached is not None else None
        # Not asked again about a document that has not been edited:
        # proposing, accepting, or rejecting a suggestion is editing it,
        # so the count in the response being reused is still the count.
        suggesting = None
        if document is None:
            if not ambient:
                suggesting = pool.submit(open_suggestions, doc_id, wanted)
            document = select_tab(fetch_document(doc_id, suggestions), wanted)
            # What this response is of, so the next build can tell whether it is
            # the one it wants. Read after the fetch, so a document edited while
            # it was in flight reads as changed next time rather than as current.
            document["suggestions"] = suggestions
            current = modified_time(doc_id)
            if current:
                document["modifiedTime"] = current
        # Recorded into the response rather than warned about here, so a build from
        # a saved response writes the same page as the build that fetched it.
        # Only what could actually be read: a key left out is one the last answer
        # stands for, which `build_one` carries over from the saved response.
        if ambient:
            # A service account is refused the suggestions outright, and for
            # comments the export answers with a document it cannot see any in,
            # which is a confident nought no retry would catch.
            #
            # Said out loud, because `google.auth.default` finds
            # `gcloud auth application-default login` as well as a key named by
            # the environment, so a machine that acquires one would otherwise stop
            # counting these silently.
            console.write(
                console.note(
                    "not asking about suggestions or comments: this is a service account, "
                    "which cannot see either; keeping the counts from the last build that could"
                ),
            )
            return document
        if suggesting is not None:
            suggested = suggesting.result()
            if suggested is not None:
                document["openSuggestions"] = suggested
        if counting is not None:
            open_threads = counting.result()
            if open_threads is not None:
                document["openComments"] = open_threads
    return document


def download_drive_file(file_id: str) -> bytes:
    """The raw bytes of a Drive file, for vectors the document links."""
    service = build("drive", "v3", credentials=_credentials())
    files = service.files()  # pyrefly: ignore[missing-attribute]
    try:
        return files.get_media(fileId=file_id).execute()
    except Exception as e:
        raise FetchFailed(_explain(e)) from e


def drive_file_type(file_id: str) -> str:
    """What kind of file a Drive file is, as its MIME type.

    A Drive link says nothing about what it links: an embed needs to know it
    is a video before it can play one.
    """
    service = build("drive", "v3", credentials=_credentials())
    files = service.files()  # pyrefly: ignore[missing-attribute]
    try:
        return files.get(fileId=file_id, fields="mimeType").execute()["mimeType"]
    except Exception as e:
        raise FetchFailed(_explain(e)) from e
