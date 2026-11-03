"""Naming must not move when the document is edited around it.

These tests use headings that genuinely collide,
since the collision branch is the only one that can be positional.
"""

import pytest

from eta_publish.naming import (
    AnchorAllocator,
    image_filename,
    image_filenames,
    slugify,
    url_filename,
)

# Two distinct headings that slugify identically.
COST_COLON = "Cost: Overview"
COST_PLAIN = "Cost Overview"


def test_slugify_strips_punctuation_and_accents():
    assert slugify("The Elephants in the Room") == "the-elephants-in-the-room"
    assert slugify("Cost: $7.7B!") == "cost-77b"
    assert slugify("") == "section"


def test_the_common_case_gets_a_clean_anchor():
    a = AnchorAllocator(["The Elephants in the Room", "Station Depth"])
    assert a.allocate("Station Depth") == "station-depth"


def test_repeated_heading_text_reuses_its_anchor():
    a = AnchorAllocator(["Overview", "Overview"])
    assert a.allocate("Overview") == a.allocate("Overview") == "overview"


def test_colliding_anchors_survive_reordering():
    """The bug this guards:
    giving the bare slug to whichever heading claims it first is still positional,
    so swapping two colliding headings moves both of their anchors."""
    first = AnchorAllocator([COST_COLON, COST_PLAIN])
    second = AnchorAllocator([COST_PLAIN, COST_COLON])
    assert first.allocate(COST_COLON) == second.allocate(COST_COLON)
    assert first.allocate(COST_PLAIN) == second.allocate(COST_PLAIN)
    assert first.allocate(COST_COLON) != first.allocate(COST_PLAIN)


def test_colliding_anchors_survive_an_unrelated_insertion():
    before = AnchorAllocator([COST_COLON, COST_PLAIN])
    after = AnchorAllocator([COST_COLON, "Station Depth", COST_PLAIN])
    assert before.allocate(COST_PLAIN) == after.allocate(COST_PLAIN)


def test_an_override_wins_and_is_not_treated_as_a_collision():
    a = AnchorAllocator([COST_COLON, COST_PLAIN], overrides={COST_COLON: "elephants"})
    assert a.allocate(COST_COLON) == "elephants"
    # With the override removed from contention, nothing collides any more.
    assert a.allocate(COST_PLAIN) == "cost-overview"


def test_image_names_depend_only_on_the_docs_object_id():
    assert image_filename("io.7", ".png") == image_filename("io.7", ".png")
    assert image_filename("io.7", ".png") != image_filename("io.8", ".png")


def test_an_anchor_is_slugged_the_way_markdown_slugs_one():
    """The same publication goes out as HTML and as Markdown,
    so a link to a section has to mean the same thing in both.
    GitHub's slugger keeps `-` and `_`, drops the rest of the punctuation,
    and writes one hyphen per space.
    The rule is imported rather than reimplemented; this says what was imported."""
    assert slugify("The Stations: Too Big and Too Deep") == "the-stations-too-big-and-too-deep"
    assert slugify("project_cost_comparison") == "project_cost_comparison"
    assert slugify("SAS West - Tunnel Profile") == "sas-west---tunnel-profile"
    # A letter is a letter whether or not it is ASCII,
    # which is where a rule written here to look like GitHub's stopped looking like it.
    assert slugify("Café Society") == "café-society"


def test_a_heading_of_nothing_sluggable_still_has_an_anchor():
    """An id is what the emitter writes into `id=`,
    so it cannot be empty however little of the heading survives the rule."""
    assert slugify("!?") == "section"
    assert slugify("") == "section"


def test_an_image_is_named_after_the_file_its_source_line_names():
    assert image_filename("io.7", ".png", name="sas-west-036.jpg") == "sas-west-036.png"
    # The underscore is the name's own, and a legal character in a URL.
    assert image_filename("io.7", ".png", name="96st_station") == "96st_station.png"


def test_a_filename_is_the_name_that_was_written_and_not_a_slug_of_it():
    """Only what cannot appear in a name changes, one underscore for each.
    Runs stay runs, capitals stay capitals,
    and a dot is a legal part of a filename rather than punctuation to be dropped."""
    assert (
        image_filename("io.7", ".png", name="SAS West - Tunnel Profile - pg 18.screenshot.png")
        == "SAS_West_-_Tunnel_Profile_-_pg_18.screenshot.png"
    )


def test_the_extension_a_source_line_writes_is_not_the_published_one():
    """`Source: chart.png` is the file that was exported,
    and the published file is whatever the download turns out to fetch."""
    assert image_filename("io.7", ".jpg", name="chart.png") == "chart.jpg"


def test_a_source_line_that_names_no_file_leaves_the_hashed_name():
    assert image_filename("io.7", ".png", name="   ") == image_filename("io.7", ".png")
    assert image_filename("io.7", ".png", name="!?").startswith("img-")


def test_a_cropped_image_is_not_named_the_same_as_its_original():
    """The crop is part of the file:
    recropping publishes a different picture,
    and it must not keep the old name and the old cached file."""
    cropped = image_filename("io.7", ".png", crop_key="0.1,0,0,0", name="96st_station.png")
    assert cropped.startswith("96st_station-")
    assert cropped != image_filename("io.7", ".png", name="96st_station.png")


def test_two_images_naming_one_file_are_both_told_apart_by_hash():
    """Not the first one wins:
    which came first is position, and reordering the publication would move a published URL."""
    names = image_filenames([("io.7", "", "plan.jpg"), ("io.8", "", "plan.jpg")])
    assert names["io.7"] != names["io.8"]
    assert all(n.startswith("plan-") for n in names.values())
    # And the one that was alone in claiming its name keeps it whole.
    alone = image_filenames([("io.7", "", "plan.jpg"), ("io.8", "", "section.jpg")])
    assert alone["io.7"] == "plan"


def test_a_name_a_reordered_document_still_gives_the_same_image():
    claims = [("io.7", "", "plan.jpg"), ("io.8", "", "plan.jpg"), ("io.9", "", "")]
    assert image_filenames(claims) == image_filenames(list(reversed(claims)))


def test_a_heading_cannot_take_an_id_the_emitter_reserves():
    """The HTML emitter writes `<h2 id="footnotes">` for its own section,
    so a heading titled `Footnotes` would produce a duplicate id."""
    a = AnchorAllocator(["Footnotes"], reserved={"footnotes"})
    assert a.allocate("Footnotes") != "footnotes"
    assert a.allocate("Footnotes").startswith("footnotes-")


def test_reserving_does_not_disturb_other_headings():
    a = AnchorAllocator(["Footnotes", "Station Depth"], reserved={"footnotes"})
    assert a.allocate("Station Depth") == "station-depth"


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("https://upload.wikimedia.org/wikipedia/commons/d/d9/W125irtjeh.JPG", "W125irtjeh.JPG"),
        ("https://www.theurbanist.org/content/images/2026/03/image-9.png?w=2", "image-9.png"),
        # The original's URL, escaped into the CDN's.
        (
            "https://substackcdn.com/image/fetch/$s_!EoCi!,f_auto/"
            "https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fab_650x862.png",
            "ab_650x862.png",
        ),
        ("https://www.flickr.com/photo_download.gne?id=8475914281", ""),
        ("https://mmbiz.qpic.cn/mmbiz_jpg/R3QIfMDE0S8gZD/", ""),
        ("https://example.com/", ""),
    ],
)
def test_a_url_names_the_image_file_its_path_ends_in(url: str, name: str) -> None:
    assert url_filename(url) == name
