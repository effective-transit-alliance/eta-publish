"""The command line itself, apart from what any one command does."""

import pytest
from typer.testing import CliRunner

from eta_publish.__main__ import app


@pytest.mark.parametrize(
    ("args", "usage"),
    [
        ([], "Usage: eta-publish [OPTIONS] COMMAND"),
        (["drafts"], "Usage: eta-publish drafts [OPTIONS] COMMAND"),
        (["one"], "Usage: eta-publish one [OPTIONS] {DOC}"),
        (["add"], "Usage: eta-publish add [OPTIONS] {URL}"),
        (["drafts", "site"], "Usage: eta-publish drafts site [OPTIONS] {DIR}"),
    ],
)
def test_with_nothing_to_do_it_prints_its_help(args: list[str], usage: str) -> None:
    """A command group has no action of its own, and nor does a command missing a required
    argument, so each says what it takes rather than only that something is missing."""
    result = CliRunner().invoke(app, args, prog_name="eta-publish")

    assert usage in result.output
    assert "Missing" not in result.output
    # Help, as `-h` prints it, which is more than the usage line an error shows.
    assert "-h, --help" in result.output
