"""Where the two test corpora live.

Both are publish directories of the same shape,
so a test says which document it wants rather than how that document is stored:

    tests/fixture/reports/<slug>/doc.json   hand-written, small, fast
    site/unpublished/reports/<slug>/doc.json  a real `documents.get` response

The real one is not under `tests/` at all:
it is the published site, at the top level, and the tests read it there.
It is a corpus because it is the real thing, not the other way around.

Each holds its emitted output beside its `doc.json`,
so a corpus can be rebuilt from what it already contains.
Only the image filenames need the network:
their extensions come from fetching, which is why `images.json` records them,
and why a test that emits a page has to stand in for the download.
"""

from pathlib import Path

from eta_publish.naming import UNPUBLISHED_DIR
from eta_publish.nodes import Document

TESTS = Path(__file__).parent
ROOT = TESTS.parent
SLUG = "reports/digging-out-deep-hole-sas-west"

FIXTURE = TESTS / "fixture"
FIXTURE_DIR = FIXTURE / SLUG

SITE = ROOT / "site"
UNPUBLISHED = SITE / UNPUBLISHED_DIR
REAL_DIR = UNPUBLISHED / SLUG


def named_images(doc: Document) -> Document:
    """Name `doc`'s images the way a build does, and hand it back.

    An extension is learned by fetching, so nothing about a parsed document
    says what its pictures were written as, and `image_href` refuses to guess.
    A test that emits a page is a test of the page rather than of the download,
    so this stands in for the download and says which file each one is.
    """
    for image in doc.images:
        doc.image_files.setdefault(image.object_id, f"{image.filename}.png")
    return doc
