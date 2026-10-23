"""What a saved `doc.json` keeps, and what it deliberately drops.

A `contentUri` is a signed URL that expires within the hour.
Saving one commits a value that is dead on arrival and that changes on every fetch,
so a re-publish of an unedited document showed up as a diff.
They are dropped on the way to disk,
which makes a re-fetch of an unchanged document a byte-identical file.

Everything but the download has to keep working from a response with no URIs in it,
because that is the only kind of response the repository holds.
"""

import json
from pathlib import Path
from typing import Any, NoReturn, override

import pytest
import requests

from eta_publish.build import without_content_uris
from eta_publish.docs_json import JsonObject
from eta_publish.images import download
from eta_publish.parse import parse

DOCUMENT: JsonObject = {
    "title": "A publication",
    "body": {
        "content": [
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "TITLE"},
                    "elements": [{"textRun": {"content": "A publication\n"}}],
                }
            },
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [{"inlineObjectElement": {"inlineObjectId": "io.1"}}],
                }
            },
        ]
    },
    "footnotes": {},
    "lists": {},
    "inlineObjects": {
        "io.1": {
            "inlineObjectProperties": {
                "embeddedObject": {
                    "description": "A map.",
                    "imageProperties": {
                        "contentUri": "https://lh7-rt.googleusercontent.com/docsz/AD_4nX",
                        "cropProperties": {},
                    },
                }
            }
        }
    },
}


@pytest.fixture
def saved() -> JsonObject:
    return without_content_uris(DOCUMENT)


def test_the_uri_is_dropped(saved: JsonObject) -> None:
    embedded = saved["inlineObjects"]["io.1"]["inlineObjectProperties"]["embeddedObject"]
    assert "contentUri" not in embedded["imageProperties"]
    assert "cropProperties" in embedded["imageProperties"]
    assert embedded["description"] == "A map."


def test_the_response_it_was_taken_from_is_untouched() -> None:
    """The download still needs the URIs; only the file on disk goes without."""
    without_content_uris(DOCUMENT)
    embedded = DOCUMENT["inlineObjects"]["io.1"]["inlineObjectProperties"]["embeddedObject"]
    assert embedded["imageProperties"]["contentUri"].startswith("https://")


def test_dropping_a_uri_leaves_the_document_unchanged_otherwise(saved: JsonObject) -> None:
    """The whole point: an unedited document re-fetches to the same file."""
    once = json.dumps(without_content_uris(DOCUMENT), indent=2)
    assert once == json.dumps(saved, indent=2)


def test_an_image_is_still_an_image_without_its_uri(saved: JsonObject) -> None:
    """`contentUri` says where to fetch an image, not whether it is one."""
    doc = parse(saved)
    assert [image.object_id for image in doc.images] == ["io.1"]
    assert doc.images[0].alt == "A map."
    assert doc.images[0].source_uri is None
    assert not [w for w in map(str, doc.warnings) if "image" in w], (
        "a URI-less image is not a defect"
    )


def test_a_download_from_a_saved_response_says_to_re_fetch(
    saved: JsonObject, tmp_path: Path
) -> None:
    doc = parse(saved)
    session = _offline()

    assert download(doc, tmp_path, session=session) == {}
    about_images = [w for w in map(str, doc.warnings) if "image" in w]
    assert about_images == [
        "this response carries no image URIs, because they expire and are "
        "not saved; re-fetch the document to download its images"
    ], "said once, not once per image"


def test_images_already_downloaded_are_still_found(saved: JsonObject, tmp_path: Path) -> None:
    """A rebuild beside an `images/` directory uses what is there."""
    doc = parse(saved)
    (tmp_path / f"{doc.images[0].filename}.png").write_bytes(b"")
    session = _offline()

    written = download(doc, tmp_path, session=session)
    assert list(written) == ["io.1"]
    assert doc.image_files["io.1"].endswith(".png")


def _offline() -> requests.Session:
    """A session that fails the test rather than the request.

    A saved response has nothing to fetch from,
    so reaching the network at all is the defect being guarded against,
    not a condition to handle.
    """

    class Offline(requests.Session):
        @override
        def get(self, *args: Any, **kwargs: Any) -> NoReturn:
            raise AssertionError("a saved response has nothing to fetch from")

    return Offline()


def test_a_run_that_cannot_read_the_review_keeps_the_last_answer(tmp_path: Path) -> None:
    """CI rebuilds with a service account, which may read neither suggestions nor comments.
    Writing a page that says nothing is open would differ from the committed one
    and fail the check that the two match, over something no document changed."""
    from eta_publish.build import carry_over_review

    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({"openSuggestions": 17, "openComments": 3}))
    fresh: dict[str, object] = {"body": {}}
    carry_over_review(fresh, saved)
    assert fresh == {"body": {}, "openSuggestions": 17, "openComments": 3}


def test_a_run_that_could_read_the_review_keeps_what_it_read(tmp_path: Path) -> None:
    from eta_publish.build import carry_over_review

    saved = tmp_path / "doc.json"
    saved.write_text(json.dumps({"openSuggestions": 17, "openComments": 3}))
    fresh: dict[str, object] = {"openSuggestions": 0, "openComments": 0}
    carry_over_review(fresh, saved)
    assert fresh["openSuggestions"] == 0
    assert fresh["openComments"] == 0


def test_a_first_build_has_no_last_answer_to_keep(tmp_path: Path) -> None:
    from eta_publish.build import carry_over_review

    fresh: dict[str, object] = {"body": {}}
    carry_over_review(fresh, tmp_path / "absent.json")
    assert fresh == {"body": {}}


def test_two_builds_that_agree_write_the_same_bytes(tmp_path: Path) -> None:
    """One build reads the counts and another carries them over,
    so they land in different places in the dictionary.
    The file is sorted, so that is not a difference anybody has to keep in step."""
    from eta_publish.build import DOC_JSON, carry_over_review, without_content_uris

    saved = tmp_path / DOC_JSON
    saved.write_text(json.dumps({"openSuggestions": 17, "openComments": 3}))

    read_for_itself: dict[str, object] = {"body": {}, "openComments": 3, "openSuggestions": 17}
    carried_over: dict[str, object] = {"body": {}}
    carry_over_review(read_for_itself, saved)
    carry_over_review(carried_over, saved)

    assert list(read_for_itself) != list(carried_over), "the orders really do differ"
    assert json.dumps(
        without_content_uris(read_for_itself), indent=2, sort_keys=True
    ) == json.dumps(without_content_uris(carried_over), indent=2, sort_keys=True)
