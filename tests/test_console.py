"""What the log looks like, on a terminal and off one.

Two audiences and two answers.
On a terminal a build is being watched by somebody who is going to go and fix
what it names, and the layout is for reading.
Off one it is a file about to be searched, and the layout is one warning per
line with nothing in it that is not a word.
"""

import io
import re
import threading
import time
from pathlib import Path

import pytest
from rich.console import Console, RenderableType

from eta_publish import console as log
from eta_publish.nodes import Cut, Highlighted, Listed, Notice, Quoted, Shown

KEYS = "https://archive.org/account/s3.php"

WARNING = Notice(
    (
        "the ",
        Shown("Header"),
        " section has no ",
        Shown("Short:"),
        " line",
    )
)


def rendered(renderable: RenderableType | None, console: Console) -> str:
    """What that console was given to write."""
    log.write(renderable, console)
    file = console.file
    assert isinstance(file, io.StringIO)
    return file.getvalue()


def _visible(line: str) -> str:
    """`line` with the colour and the links taken back out, for asserting about
    its words. A hyperlink is an escape around the text rather than in it, so
    what is left is what a reader sees either way."""
    words = re.sub(r"\x1b\]8;[^\x1b]*\x1b\\", "", line)
    return re.sub(r"\x1b\[[0-9;]*m", "", words)


def plain() -> Console:
    """A console writing where nothing is watching, at the width one gets."""
    return Console(file=io.StringIO(), highlight=False, width=log.UNWRAPPED)


def terminal(width: int = 60) -> Console:
    """A console that believes it is a terminal, narrow enough to have to wrap."""
    return Console(
        file=io.StringIO(), highlight=False, force_terminal=True, no_color=False, width=width
    )


def test_a_warning_off_a_terminal_is_one_line() -> None:
    """A log is read with `rg`, and half a warning does not match a search for it."""
    written = rendered(log.notice(WARNING, plain()), plain())
    assert written == "  ! the `Header` section has no `Short:` line\n"


def test_a_warning_off_a_terminal_has_no_escape_sequences() -> None:
    """Redirected output is a file, and colour in a file is noise to search past."""
    assert "\x1b" not in rendered(log.built("A report", "reports/a", [WARNING], plain()), plain())


def test_the_shown_values_keep_their_backticks_where_there_is_no_colour() -> None:
    """Colour is what says where a value starts and stops, and it is the only thing:
    without it the backticks are, so they stay."""
    assert "`Short:`" in rendered(log.notice(WARNING, plain()), plain())


def test_the_shown_values_are_coloured_rather_than_quoted_on_a_terminal() -> None:
    """Both at once is one mark too many for a value already picked out in cyan."""
    console = terminal()
    written = rendered(log.notice(WARNING, console), console)
    assert "`" not in written
    assert "\x1b" in written


def test_a_warning_too_long_for_the_terminal_hangs_under_itself() -> None:
    """The continuation is indented past the `!`, so a warning that takes three
    lines still reads as one warning rather than as three."""
    console = terminal(40)
    long = Notice(("a warning long enough that it cannot fit on one line at all",))
    lines = rendered(log.notice(long, console), console).splitlines()
    assert len(lines) > 1
    assert _visible(lines[0]).startswith("  ! a warning")
    assert _visible(lines[1]).startswith("    ")


def test_what_a_warning_sets_apart_is_indented_under_it() -> None:
    """A list of seventeen images at the left margin reads as seventeen warnings."""
    listed = Notice(("unnamed images:", Listed((Shown("img-1"),), (Shown("img-2"),))))
    lines = rendered(log.notice(listed, plain()), plain()).splitlines()
    assert lines == [
        "  ! unnamed images:",
        "      • `img-1`",
        "      • `img-2`",
    ]


def test_a_quoted_value_is_given_its_own_lines() -> None:
    """Long enough to run into the sentence, which is why it was set apart."""
    quoted = Notice(("too long:", Quoted("kept ", Cut("cut"))))
    lines = rendered(log.notice(quoted, plain()), plain()).splitlines()
    assert lines == ["  ! too long:", "      kept ~~cut~~"]


def test_the_cut_part_keeps_its_marks_on_a_terminal_too() -> None:
    """Struck-through text is not drawn by every terminal,
    and a warning about where a sentence stops cannot rely on one that does."""
    console = terminal(200)
    quoted = Notice(("too long:", Quoted("kept ", Cut("cut"))))
    assert "~~cut~~" in _visible(rendered(log.notice(quoted, console), console))


def test_a_failure_says_its_reason_where_it_says_the_name() -> None:
    """One failure named twice, once with the reason and once without,
    is the same failure read twice."""
    written = rendered(log.failed("A report", "the tab is named ``"), plain())
    assert written.splitlines() == ["✗ A report", "  the tab is named ``"]


def test_a_report_that_built_is_counted_by_its_warnings() -> None:
    written = rendered(log.built("A report", "reports/a", [WARNING, WARNING], plain()), plain())
    assert written.startswith("✓ reports/a · A report · 2 warnings")


def test_a_report_with_nothing_to_fix_says_nothing_about_warnings() -> None:
    assert (
        rendered(log.built("A report", "reports/a", [], plain()), plain())
        == "✓ reports/a · A report\n"
    )


def test_what_squarespace_is_given_by_hand_is_under_the_heading() -> None:
    """A field the document leaves blank is not a line to paste."""
    paste = [("Excerpt", "The preview."), ("SEO description", "")]
    assert (
        rendered(log.built("A report", "reports/a", [], plain(), paste), plain())
        == "✓ reports/a · A report\n  Excerpt: The preview.\n"
    )


@pytest.mark.parametrize(
    ("built", "failed", "warnings", "expected"),
    [
        (3, 0, 27, "3 built · 27 warnings"),
        (3, 0, 0, "3 built"),
        (2, 1, 1, "2 built · 1 warning · 1 failed"),
    ],
)
def test_the_summary_counts_only_what_is_there(
    built: int, failed: int, warnings: int, expected: str
) -> None:
    """`0 failed` after every successful build teaches people to skip the line
    that says a build failed."""
    assert rendered(log.summary(built, failed, warnings), plain()) == f"{expected}\n"


def test_a_note_is_marked_apart_from_a_warning() -> None:
    """A missing `typst` is not something to go and fix in a document,
    and a reader scanning for what needs attention should be able to tell."""
    assert rendered(log.note("typst is not installed"), plain()) == "· typst is not installed\n"
    assert rendered(log.warning("biome lint failed"), plain()) == "! biome lint failed\n"


def test_the_report_a_note_is_about_is_marked_as_the_value_it_is() -> None:
    """`added` marks the same name, read off the same list, the same way: a name
    inside a sentence runs into the words around it unless it is picked out."""
    with log.about("IBX Automation"):
        written = rendered(log.note("looking up 3 sources in the archive"), plain())
    assert written == "· `IBX Automation`: looking up 3 sources in the archive\n"


def test_a_note_outside_a_build_names_no_report() -> None:
    """One document fetched on its own is the only document there is,
    and naming it says nothing the caller did not type."""
    assert rendered(log.note("nothing to archive"), plain()) == "· nothing to archive\n"


def test_a_note_keeps_its_values_marked_off_a_terminal() -> None:
    """The same rule a warning's values follow: off a terminal the backticks are
    the only thing saying where a command stops, so they stay."""
    written = rendered(log.note("install it with {}", Shown("mise use -g typst")), plain())
    assert written == "· install it with `mise use -g typst`\n"


def test_a_note_colours_its_values_on_a_terminal() -> None:
    """A command in a note is a value to go and use, marked the way the values
    in a warning are, and marked once rather than in colour and quotes both."""
    console = terminal(width=log.UNWRAPPED)
    said = log.note("install it with {}", Shown("mise use -g typst"), console=console)
    written = rendered(said, console)
    assert "`" not in written
    assert _visible(written) == "· install it with mise use -g typst\n"
    # The value is the colour a value is, not a dim version of it.
    assert "\x1b[36m" in written


def test_a_note_says_a_whole_message_with_no_values() -> None:
    """The text of somebody else's exception is one value and no template,
    and a brace in it is a brace: nothing here formats a string."""
    written = rendered(log.warning("{}", "typst compile failed: a { b"), plain())
    assert written == "! typst compile failed: a { b\n"


def test_a_url_in_a_note_is_left_alone_off_a_terminal() -> None:
    """A URL is already the thing it names: nothing to add and nothing to take
    out, and a log searched for one holds exactly what was written."""
    written = rendered(log.note("set them from {}", log.Linked(KEYS)), plain())
    assert written == f"· set them from {KEYS}\n"


def test_a_url_on_a_terminal_is_underlined_and_made_a_link() -> None:
    """Underlined rather than coloured, because what a reader does with a URL is
    open it rather than go and find it, and told to the terminal as a link so it
    can be clicked instead of retyped."""
    console = terminal(width=log.UNWRAPPED)
    written = rendered(log.note("set them from {}", log.Linked(KEYS), console=console), console)
    assert "\x1b[4m" in written
    assert f"{KEYS}\x1b\\" in written
    assert _visible(written) == f"· set them from {KEYS}\n"


def test_what_was_added_is_read_back() -> None:
    """Both values were read off the document rather than typed,
    so reading them back is the only way anybody sees what they are."""
    written = rendered(
        log.added(Path("reports.toml"), "IBX Automation", "Draft 2", plain()), plain()
    )
    assert written == "✓ reports.toml: added `IBX Automation`, tab `Draft 2`\n"


def test_a_heading_holds_its_fields_apart_without_colour() -> None:
    """Piped into a file there is no colour saying where one field stops,
    and three fields with two spaces between them are one field."""
    written = rendered(log.built("A report", "reports/a", [WARNING], plain()), plain())
    assert written.splitlines()[0] == "✓ reports/a · A report · 1 warning"


def test_a_title_is_a_title_and_not_markup() -> None:
    """`rich` reads square brackets as styles and colons as emoji,
    and a document is named by whoever named it rather than by this."""
    written = rendered(log.built("A [bold]Draft[/] :construction:", "b/x", [], plain()), plain())
    assert "A [bold]Draft[/] :construction:" in written


GAPPED = Notice((Highlighted("It is deep.", "\u00b7\u00b7", "It is expensive."),))


def test_the_marked_part_is_drawn_on_a_terminal_too() -> None:
    """The highlight says which characters, and the dots say what they are:
    a highlighted space is a space, and it is spaces that are being warned about."""
    console = terminal(width=log.UNWRAPPED)
    written = _visible(rendered(log.notice(GAPPED, console), console))
    assert "It is deep.\u00b7\u00b7It is expensive." in written


def test_the_marked_part_is_highlighted_rather_than_reversed() -> None:
    """Reverse video is whatever the terminal's foreground happens to be,
    which is white on a white-on-black theme and no mark at all."""
    console = terminal(width=log.UNWRAPPED)
    written = rendered(log.notice(GAPPED, console), console)
    assert "\x1b[30;43m\u00b7\u00b7\x1b[0m" in written


def test_a_marked_value_is_one_quoted_value_off_a_terminal() -> None:
    """Nothing in a file can carry a highlight,
    and three backticked pieces of one excerpt read as three values."""
    assert "`It is deep.\u00b7\u00b7It is expensive.`" in rendered(
        log.notice(GAPPED, plain()), plain()
    )


def _written(console: Console) -> str:
    """Everything that console was given, with the colour taken back out."""
    file = console.file
    assert isinstance(file, io.StringIO)
    return _visible(file.getvalue())


def test_a_long_job_draws_a_bar_on_a_terminal() -> None:
    """A build that says nothing for two minutes is one somebody kills."""
    console = terminal()
    with log.progress("checking the archive", 4, console) as along:
        for _ in range(4):
            along()
        bar = log._BAR
        assert bar is not None
        (row,) = bar.tasks
        assert (row.description, row.completed, row.total) == ("checking the archive", 4, 4)
    assert "checking the archive" in _written(console)


def test_every_report_shares_the_one_bar() -> None:
    """Two displays cannot both have the bottom of the screen,
    and a second one opening its own is what pushes the first one around."""
    console = terminal()
    with log.progress("checking the archive", 2, console):
        first = log._BAR
        assert first is not None
        with log.progress("checking the archive", 3, console):
            assert log._BAR is first
            assert len(first.tasks) == 2
        assert len(first.tasks) == 1
    assert log._BAR is None


def test_a_long_job_says_where_it_is_in_a_file() -> None:
    """A redirected log has no in place to redraw,
    so it gets a line at every tenth instead of a hundred and nine of them."""
    console = plain()
    with log.progress("checking the archive", 20, console) as along:
        for _ in range(20):
            along()
    lines = _written(console).splitlines()
    assert lines[0] == "· checking the archive: 2 of 20"
    assert lines[-1] == "· checking the archive: 20 of 20"
    assert len(lines) == 10


def test_a_bar_leaves_nothing_behind_to_read() -> None:
    """The line after it says the same thing in the past tense."""
    console = terminal()
    with log.progress("checking the archive", 2, console) as along:
        along()
        along()
    assert "checking the archive" not in _written(console).splitlines()[-1]


def test_the_clock_keeps_moving_while_nothing_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The elapsed time is the half of the row that says a slow answer is
    still an answer, and a row that redraws only when something completes
    stops for exactly as long as the thing worth watching takes.

    On a clock and a tick both twenty times faster,
    so the seconds the row shows pass without the suite waiting for them.
    """
    monkeypatch.setattr(log, "TICK", log.TICK / 20)
    console = terminal()
    console.get_time = lambda: time.monotonic() * 20
    with log.progress("checking the archive", 3, console) as along:
        along()
        time.sleep((log.TICK * 6).total_seconds())
    drawn = set(re.findall(r"0:00:0\d", _written(console)))
    assert len(drawn) > 1


def test_the_clock_is_not_something_a_build_waits_on() -> None:
    """A build that is stopping has better things to join than a timer."""
    console = terminal()
    with log.progress("checking the archive", 1, console):
        ticking = [t for t in threading.enumerate() if t.name == log.TICKER]
        assert ticking and all(t.daemon for t in ticking)


def test_a_source_being_waited_on_has_a_line_saying_what_it_waits_on() -> None:
    """Which one is holding the build up, and what for, rather than only how many are left."""
    console = terminal(width=100)
    with log.progress("checking the archive", 2, console), log.watching(console) as rows:
        rows.show("https://data.ny.gov/d/kcjb-nf3e", "index")
        drawn = _written(console)
    assert "index · data.ny.gov/d/kcjb-nf3e" in drawn


def test_a_source_answered_takes_its_line_with_it() -> None:
    console = terminal(width=100)
    with log.progress("checking the archive", 2, console), log.watching(console) as rows:
        rows.show("https://a.example/1", "replay")
        rows.drop("https://a.example/1")
        assert rows.tasks == {}


def test_off_a_terminal_only_a_slow_source_is_said(monkeypatch: pytest.MonkeyPatch) -> None:
    """A log has no line to redraw, so it hears about a source once, and only if it was slow."""
    console = plain()
    now = iter([0.0, 0.0, 30.0])
    monkeypatch.setattr(log.time, "monotonic", lambda: next(now))
    with log.watching(console) as rows:
        rows.show("https://a.example/1", "replay")
        rows.show("https://a.example/1", "capture pending")
        rows.drop("https://a.example/1")
    assert "https://a.example/1" in _written(console)
    assert "took 30s, last capture pending" in _written(console)
