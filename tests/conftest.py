import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Rich draws errors in a box the width of the terminal
# and breaks anything longer than the box wherever the box ends, mid-word,
# so a test asking whether a message names a file
# would be asking it of `absent.tom` and `l` on separate lines.
# The command line keeps its formatting; only the tests read it plain.
# Set here rather than in a test:
# Typer reads this once, when it is first imported.
os.environ.setdefault("TYPER_USE_RICH", "0")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--regenerate-snapshots",
        action="store_true",
        help="overwrite the committed snapshots with current output",
    )


SITE_BUILD = "built_site"
"""The fixture a test asks for to read the whole site as an offline build writes it."""


class _Build:
    """The offline build of the whole site, started as soon as a test is known to want it.

    A process rather than a thread, so it runs alongside the rest of the suite
    instead of taking turns with it for the interpreter, and so the hundred or
    so warnings it writes go to a file rather than through the test output.

    Without the images, which are not committed and so are not on a fresh
    checkout or in CI: a build without them writes the same committed files,
    since `images.json` says what each one was written as.
    """

    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="eta-publish-site-"))
        self.out = self.dir / "site"
        self.log = (self.dir / "build.log").open("w")
        root = Path(__file__).parent.parent
        self.process = subprocess.Popen(
            [sys.executable, "-m", "eta_publish", "all", "--offline", "--no-images"]
            + ["-o", str(root / "site"), "--into", str(self.out)],
            cwd=root,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )

    def wait(self) -> Path:
        code = self.process.wait()
        self.log.close()
        if code != 0:
            pytest.fail(f"the offline build failed:\n{(self.dir / 'build.log').read_text()}")
        return self.out


_build: _Build | None = None


def pytest_collection_finish(session: pytest.Session) -> None:
    global _build
    if any(SITE_BUILD in getattr(item, "fixturenames", ()) for item in session.items):
        _build = _Build()


def pytest_sessionfinish(session: pytest.Session) -> None:
    if _build is not None:
        _build.process.kill()
        _build.process.wait()
        shutil.rmtree(_build.dir, ignore_errors=True)


@pytest.fixture(scope="session")
def built_site() -> Path:
    """Where the offline build wrote the whole site, waited for."""
    if _build is None:
        pytest.fail(f"`{SITE_BUILD}` was not started; see `pytest_collection_finish`")
    return _build.wait()


@pytest.fixture(scope="session")
def regenerate_snapshots(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--regenerate-snapshots"))


@pytest.fixture(autouse=True)
def _forget_credentials(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_credentials` is worked out once per process, and a test is not a process.

    Two tests that set up different credentials would otherwise get whichever
    ran first, in whichever order the suite happened to run them.

    Opening a browser is then refused outright, for every test but a `network`
    one. `_sign_in` ends at `InstalledAppFlow.run_local_server`, which opens a
    browser and waits for a redirect that is never coming: a test that reaches
    it does not fail, it hangs, and the suite hangs with it. A test reaching
    that is one that missed something it meant to stub, so say which one and
    say it immediately.

    Refused there rather than at `_sign_in`, which has a branch that reads
    credentials the environment names and is worth a test of its own.
    """
    import eta_publish.fetch as fetch

    fetch._sign_in.cache_clear()
    if "network" in request.keywords:
        return

    from google_auth_oauthlib.flow import InstalledAppFlow

    def refused(self: object, *args: object, **kwargs: object) -> object:
        raise AssertionError(
            f"{request.node.name} would open a browser to sign in to Google; "
            "stub what it calls, or mark it `network`"
        )

    monkeypatch.setattr(InstalledAppFlow, "run_local_server", refused)


@pytest.fixture(autouse=True)
def _fresh_lookup_cache(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache of the person's own builds is not a fixture.

    `archive.to_ask` skips a source looked up in the last week and not found, and
    the file saying which those are lives in the person's cache directory. Left
    alone, a suite run after a real build would be told to skip the very lookups
    the test set up an answer for, and would pass or fail depending on what the
    machine happened to have done that week.
    """
    from eta_publish.archive import ARCHIVE_CACHE

    monkeypatch.setenv(ARCHIVE_CACHE, str(tmp_path_factory.mktemp("cache") / "archive.json"))


@pytest.fixture(autouse=True)
def _no_ia_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person's own archive.org keys are not a fixture either.

    `archive._keys` falls back to the file `ia configure` writes, so a suite
    run on a machine with one would ask for captures in every test that set up
    no keys, and the tests of a build without them would test nothing.
    """
    from eta_publish.archive import IA_CONFIG

    monkeypatch.setenv(IA_CONFIG, str(tmp_path_factory.mktemp("ia") / "ia.ini"))


@pytest.fixture(autouse=True)
def _no_anonymous_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """As in CI, so a test without keys is the lookup-only build it was written as.

    Otherwise every one of them would ask Save Page Now for real, thirty seconds
    apart. The tests of anonymous capture unset it themselves.
    """
    from eta_publish.archive import CI

    monkeypatch.setenv(CI, "true")
