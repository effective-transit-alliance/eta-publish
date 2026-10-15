"""How a report is written, as distinct from what it says.

`parse.py` warns about what it could not read and `checks.py` about what a
report has not got. These read prose that parsed cleanly and is complete,
and say it is spelled against the house style: the same sentence,
set the way every other report sets it.

Each is a fix in the document rather than in the build,
so each is a warning on the document like the others,
and none of them rewrites anything on the way out.
Spelling the reports alike is the writer's, so the build says where to look
rather than quietly making the reports agree.
"""

import re
from collections.abc import Iterator

from .nodes import SPACE, Document, Highlighted, Shown, plain_text

CONTEXT = 30
"""How much of the line to show on either side of what is being warned about.

Enough to find the sentence in a document of several thousand words,
and not so much that a warning about two spaces is a paragraph.
"""


def _before(text: str, start: int) -> str:
    """What runs up to `start`, with enough of it to be found by eye."""
    lead = "..." if start > CONTEXT else ""
    return lead + text[max(0, start - CONTEXT) : start]


def _after(text: str, end: int) -> str:
    """What follows `end`, with enough of it to be found by eye."""
    trail = "..." if end + CONTEXT < len(text) else ""
    return text[end : end + CONTEXT] + trail


def _excerpt(text: str, start: int, end: int) -> str:
    """`text[start:end]` with enough either side of it to be found by eye."""
    return f"{_before(text, start)}{text[start:end]}{_after(text, end)}"


PREFIX = "style: "
"""What every warning here opens with.

A document's warnings are one list, and the rest of that list is something
the build could not do: a missing field, an unnamed image, a line nothing
read. These are things it did, correctly, that somebody may still want to
write differently, and a reader sorting the list by what to fix first
should be able to tell the two apart without reading to the end of the line.
"""


def _warn(doc: Document, template: str, *values: Shown | Highlighted) -> None:
    """Warn about how something is written, said as one of these rather than
    as one of the document's other warnings."""
    doc.warn(PREFIX + template, *values)


def _prose(doc: Document) -> Iterator[str]:
    """Every run of the document's own words, as one string each.

    Footnotes included. They carry the report's own prose as often as they
    carry a citation, and a citation copied from where it was published is
    published here too, under this report's name and in its house style.

    The header is read alongside the body rather than left out of this.
    `text_runs` walks the blocks, and the header was consumed before those
    existed, so a `Short:` or `SEO Description:` written against the style
    would otherwise be the one piece of prose nothing here reads,
    and it is the piece that publishes as the standfirst
    and as what a search result shows.
    """
    yield from doc.meta.values()
    for run, _ in doc.text_runs():
        yield plain_text(run)


def style(doc: Document) -> None:
    """Warn about every line written against the house style."""
    for text in _prose(doc):
        _check_spacing(doc, text)
        _check_dash_spacing(doc, text)
        _check_ranges(doc, text)
        _check_apostrophes(doc, text)
        _check_organization_name(doc, text)
        _check_street_names(doc, text)
        _check_units(doc, text)
        _check_hyphenated_units(doc, text)
        _check_spelled_out_symbols(doc, text)


GAP = re.compile(r"(?<=\S)(?P<gap>  +)(?=\S)")
"""Two or more spaces with a word either side of them.

A word either side because a run at the start or the end of a line
is indentation or something left trailing, which is neither of the two
mistakes here and would be described wrongly by both.
"""

ENDS_A_SENTENCE = re.compile(r"""[.!?]["'”’)\]]*$""")
"""What comes before a gap that separates two sentences.

The terminator and whatever closes the quote or bracket around it.
The closers are `sentences.py`'s, because the two are answering the same
question about the same prose: `separately).  This` ends a sentence,
and the paren is not what the spaces come after.
"""


def _check_spacing(doc: Document, text: str) -> None:
    """A gap of more than one space, described by what sits either side of it.

    Between sentences it is the typewriter habit, and mid-clause it is a
    slipped finger: the same characters, but one is how somebody was taught
    to type and the other is a typo, so they are not one warning.

    Neither is visible anywhere somebody would catch it.
    The doc shows one space either way, HTML collapses the run, and
    Squarespace never sees it, so nothing downstream reports either one
    and the Markdown archive keeps both forever.
    """
    for match in GAP.finditer(text):
        gap = match.group("gap")
        start, end = match.span("gap")
        drawn = Highlighted(_before(text, start), SPACE * len(gap), _after(text, end))
        if ENDS_A_SENTENCE.search(text[: match.start("gap")]):
            _warn(doc, f"a sentence should end with 1 space, not {len(gap)}: {{}}", drawn)
        else:
            _warn(doc, f"two words should be separated by 1 space, not {len(gap)}: {{}}", drawn)


DASHES = "—–"
"""The two dashes that set a phrase off, em and en.

Not the hyphen: `pipe-jacking` is one word and `10-15` is somebody
reaching for an en dash, which is a different thing to say about a line.
"""

SPACED_DASH = re.compile(rf"(?: +(?P<before>[{DASHES}]) *|(?P<after>[{DASHES}]) +)")
"""A dash with spaces on one side of it or both, taken as one match with them."""

DASH_NAMES = {"\u2014": "an em dash", "\u2013": "an en dash"}


def _check_dash_spacing(doc: Document, text: str) -> None:
    """A dash with a space on either side of it, where the house style has none.

    The reports already write it closed up, in every one of the fourteen
    dashes SAS West and IBX have between them. A spaced one arrives by pasting
    from somewhere that sets them open, and the one paragraph set the other way
    is visible on the page next to the rest.
    """
    for match in SPACED_DASH.finditer(text):
        dash = match.group("before") or match.group("after")
        start, end = match.span()
        # The spaces drawn, as for a gap: quoted as spaces, they are invisible.
        drawn = match.group().replace(" ", SPACE)
        _warn(
            doc,
            f"{DASH_NAMES[dash]} should not have spaces: {{}}",
            Highlighted(_before(text, start), drawn, _after(text, end)),
        )


RANGE = re.compile(
    r"(?<![\w/.#=\-\u2013])\d+(?:[.,]\d+)?(?P<hyphen>-)\d+(?:[.,]\d+)?(?![\w/\-\u2013])"
)
"""Two numbers joined by a hyphen, which is a range and takes an en dash: `10–15`.

Not where the run goes on, as in a date, `2024-05-01`, or a phone number,
nor inside a URL or a code, which have letters, slashes, or dots at their edges.
"""


def _check_ranges(doc: Document, text: str) -> None:
    """A hyphen between two numbers, where the house style has an en dash.

    Docs does not turn one into the other as it does a quote,
    and the two look alike enough to slip past anyone reading the doc.
    """
    for match in RANGE.finditer(text):
        start, end = match.span("hyphen")
        # A URL or a DOI, whose numbers are an address rather than a range.
        token_start = max(text.rfind(" ", 0, start), text.rfind("\n", 0, start)) + 1
        token_end = min(
            (i for i in (text.find(" ", end), text.find("\n", end)) if i >= 0), default=len(text)
        )
        if "/" in text[token_start:token_end]:
            continue
        _warn(
            doc,
            "a range should use an en dash, {}, not a hyphen: {}",
            Shown("\u2013"),
            Highlighted(_before(text, start), "-", _after(text, end)),
        )


STRAIGHT_APOSTROPHE = re.compile(r"(?<=\w)'(?=\w)")
"""A straight quote inside a word, which can only be an apostrophe.

Only inside one: `riders'` or `'90s` could as well be a quote opening or closing,
and warning about every quote would bury the apostrophes it is after.
"""


def _check_apostrophes(doc: Document, text: str) -> None:
    """A straight `'` for an apostrophe, where the house style curls it: `’`.

    Docs curls it as it is typed, so a straight one arrives by pasting,
    and sits on the page beside the curled ones around it.
    """
    for match in STRAIGHT_APOSTROPHE.finditer(text):
        _warn(
            doc,
            "an apostrophe should be {}, not {}: {}",
            Shown("\u2019"),
            Shown("'"),
            Highlighted(_before(text, match.start()), match.group(), _after(text, match.end())),
        )


SPELLED_OUT = "the Effective Transit Alliance"
"""The name written out, which does take an article.

Only the initials go bare, so a line spelling the name out is already right
and this rule has nothing to say about it.
"""

ARTICLED = re.compile(r"\bthe[ \u00a0]+(?=ETA\b)", re.IGNORECASE)
"""An article before the initials, which is what is being warned about.

The initials themselves are left to the sentence: `ETA recommended` and
`ETA members` are how both reports write it, and the only thing wrong with
`the ETA` is the word in front. Case-insensitively, because a sentence
opening `The ETA` is the same mistake as one saying it mid-line.
"""


def _check_organization_name(doc: Document, text: str) -> None:
    """`the ETA`, where the initials are written on their own.

    It is the name rather than a description of one, the way somebody writes
    `NASA said` and not `the NASA said`, and both reports already say
    `ETA recommended` and `ETA members` in the places they say it at all.
    Spelled out it does take the article, which is why this looks only at
    the initials.
    """
    for match in ARTICLED.finditer(text):
        _warn(
            doc,
            "{} is written {}; it is {} on its own, and {} spelled out: {}",
            Shown("ETA"),
            Shown(text[match.start() : match.end() + len("ETA")]),
            Shown("ETA"),
            Shown(SPELLED_OUT),
            Shown(_excerpt(text, match.start(), match.end() + len("ETA"))),
        )


EDGES = "\"'“”‘’()[]{}.,;:!?…"
"""What a word is quoted, bracketed or punctuated with at either end.

Stripped before a word is looked up, so `Street.` at the end of a sentence
and `(88.5` inside a spec table are the words they are.
Only the ends: `72,000` and `1.6` are one word each,
and a hyphen is left alone because it joins two.
"""


def _words(text: str) -> list[tuple[str, int]]:
    """Each run of non-space characters, with where it starts.

    A style rule is about words next to each other: a number then its unit,
    a name then its kind of street. Scanning them once and looking each up
    says that directly, where a pattern has to describe what a word looks
    like and then be walked back for every word that looks like one and is not.
    """
    words: list[tuple[str, int]] = []
    start: int | None = None
    for i, char in enumerate(text):
        if char.isspace():
            if start is not None:
                words.append((text[start:i], start))
                start = None
        elif start is None:
            start = i
    if start is not None:
        words.append((text[start:], start))
    return words


def _bare(word: str) -> str:
    """`word` without whatever punctuation is around it."""
    return word.strip(EDGES)


def _at(word: str, start: int) -> int:
    """Where the word itself starts, past anything quoting it."""
    return start + len(word) - len(word.lstrip(EDGES))


def _number(word: str) -> str | None:
    """`word` as a number, or `None` where it is not one.

    Commas and points are part of it: `72,000` and `1.6` are each one number.
    """
    bare = _bare(word)
    if not bare or not any(c.isdigit() for c in bare):
        return None
    return bare if all(c.isdigit() or c in ",." for c in bare) else None


ORDINALS = ("st", "nd", "rd", "th")


def _counted(word: str) -> str | None:
    """A number with its ordinal ending taken off: `125th` is `125`."""
    for ending in ORDINALS:
        if word.endswith(ending) and _number(word[: -len(ending)]):
            return word[: -len(ending)]
    return None


TYPES = {
    "Street": "St",
    "Avenue": "Av",
    "Ave": "Av",
    "Boulevard": "Blvd",
    "Place": "Pl",
    "Road": "Rd",
    "Drive": "Dr",
    "Lane": "Ln",
    "Parkway": "Pkwy",
    "Turnpike": "Tpke",
    "Square": "Sq",
    "Expressway": "Expy",
    "Highway": "Hwy",
}
"""How the MTA writes each kind of street, and every spelling that is not it.

Its own signs, maps and announcements are where these come from:
`125 St`, `2 Av`, `Queens Blvd`, `Henry Hudson Pkwy`.
A report is about the system, so it should name a station the way the system
names it, and the reader who goes looking for the sign finds the sign.

Singular only. There is no MTA spelling of `116th and 125th Streets`,
and a rule that invents one would be worse than the one it corrects.

No `Plaza`, which the MTA writes out: `Grand Army Plaza` is the station.
No `Court` either: the station is `Court Sq`, where the court is the name
and the square is the kind, so a rule abbreviating it would rename it.
No `Terrace` either, which is not a kind of street these reports name and
not one the system has a station on.
"""

WRITTEN = frozenset(TYPES.values())
"""The spellings that are already right, which nothing is warned about."""

NUMBERED = {
    "First": "1",
    "Second": "2",
    "Third": "3",
    "Fourth": "4",
    "Fifth": "5",
    "Sixth": "6",
    "Seventh": "7",
    "Eighth": "8",
    "Ninth": "9",
    "Tenth": "10",
    "Eleventh": "11",
    "Twelfth": "12",
}
"""The avenues whose number somebody writes as a word.

The MTA writes the digit: the station on Second Avenue is `2 Av`,
on every sign and in every announcement, so a spelled-out number is
corrected like an ordinal rather than left standing.
"""

PROJECTS = ("Second Avenue Subway", "Second Avenue Stubway")
"""Names of the line, which are not names of the street under it.

The Second Avenue Subway is the MTA's own name for the project, and these
reports say it constantly. The Second Avenue Stubway is what SAS West calls
it for having `only made it three stops`, a joke that is on the project's
name and works only while it keeps it.

The street is `2 Av` and the line along it is one of these,
so each full phrase is left exactly as it is written here,
and a phrase written any other way is corrected towards it
rather than towards the station.
"""


def _spellings() -> dict[str, str]:
    """Every way one of these names gets written, and the name it is.

    The avenue abbreviated, which is the mistake being corrected, and the
    line in lowercase, which is how SAS West writes `subway` twice.
    """
    spellings = {}
    for project in PROJECTS:
        street, _, line = project.rpartition(" ")
        for name in (street, street.replace("Avenue", "Ave")):
            for word in (line, line.lower()):
                spellings[f"{name} {word}"] = project
    return spellings


SPELLED = _spellings()

NOT_A_STREET = ("Rail Road",)
"""Phrases ending in what looks like a kind of street and is not one.

The Long Island Rail Road is a railroad, spelled as two words since 1876,
and `Long Island Rail Rd` is not a thing anybody has ever called it.
"""

COMMON_NOUN = "The"
"""What a name starts with when it is a phrase rather than a street.

`The Wrong Place to Scale Back` is a heading in SAS West, and `Place`,
`Square` and `Drive` are all ordinary words as well as kinds of street.
No street is `The` anything, so this is the one that can be told
apart by reading it.
"""

ELSEWHERE = frozenset({"Nanba Road", "Heping South Street", "Ball Square", "Jersey Avenue"})
"""Streets these reports name that are not in New York.

`Nanba Road` is in Shanghai, `Heping South Street` in Beijing,
`Ball Square` is a Green Line station outside Boston,
and `Jersey Avenue` a Hudson-Bergen Light Rail station in Jersey City, and none
is a street the MTA has a spelling for: restyling them to `Nanba Rd` would be
inventing a name nothing anywhere calls it.
Nothing in the text says which city a street is in,
so a report naming another one adds it here.
"""


def _street_name(word: str) -> str | None:
    """`word` as the name of a street, or `None` where it names nothing.

    A number, written as digits or as the word for one, or a capitalized
    word. `Fordham Road` and `125th Street` are named; `the Road` is not.
    """
    if _number(word) or _counted(word) or word in NUMBERED:
        return word
    return word if word[:1].isupper() and word[1:].islower() else None


def _ends_a_phrase(word: str) -> bool:
    """Whether the punctuation after `word` closes what it was part of.

    `Ruling Grade: The Wrong Place` is a heading whose name does not run back
    past the colon, which is what keeps `The` at the front of the phrase that
    is then recognized as no street at all.
    """
    return word.rstrip(EDGES) != word


def _named(words: list[tuple[str, int]], kind: int) -> int:
    """Where the name ending at `kind` starts.

    The run of capitalized words and numbers leading up to the kind of street,
    stopping at whatever punctuation ends a phrase:
    `Henry Hudson Parkway` is named for two of them.
    """
    first = kind
    while (
        first
        and _street_name(_bare(words[first - 1][0])) is not None
        and not _ends_a_phrase(words[first - 1][0])
    ):
        first -= 1
    return first


def _check_street_names(doc: Document, text: str) -> None:
    """A station or a street named some way other than the MTA's.

    The reports are about what the MTA builds, and a reader who goes looking
    for `125th Street` on a map finds `125 St`, which is the sign on the
    platform, the name in the app, and what the announcement says.
    """
    words = _words(text)
    for i, (word, _) in enumerate(words):
        kind = _bare(word)
        if kind not in TYPES or not i:
            continue
        last = _street_name(_bare(words[i - 1][0]))
        if last is None:
            continue
        first = _named(words, i)
        phrase = " ".join(_bare(word) for word, _ in words[first : i + 1])
        if (
            phrase in ELSEWHERE
            or phrase.startswith(f"{COMMON_NOUN} ")
            or phrase.endswith(NOT_A_STREET)
        ):
            continue
        # A spelled-out number or a digit ends the name whatever led up to it:
        # the street in `The Second Avenue Subway` is `Second Avenue`.
        counted = last in NUMBERED or _number(last) or _counted(last)
        name = last if counted else " ".join(_bare(word) for word, _ in words[first:i])
        start = _at(*words[i - 1 if counted else first])
        written = f"{name} {kind}"
        named = _named_project(text, start)
        if named is not None:
            # The whole phrase, so the warning is about the name the project
            # has rather than about the two words of it that are a street.
            written, correct = named
        else:
            correct = _mta(name, kind)
        if correct == written:
            continue
        _warn(
            doc,
            "{} should be {}: {}",
            Shown(written),
            Shown(correct),
            Highlighted(_before(text, start), written, _after(text, start + len(written))),
        )


def _named_project(text: str, start: int) -> tuple[str, str] | None:
    """The line named at `start`, as it is written there and as it is called."""
    for written, project in SPELLED.items():
        if text.startswith(written, start):
            return written, project
    return None


def _mta(name: str, kind: str) -> str:
    """`name` and `kind` written the way the MTA writes them.

    A number is a digit whether it was written as one or not,
    and it carries no ordinal suffix: `125th Street` and `Second Avenue`
    are `125 St` and `2 Av`.
    """
    return f"{NUMBERED.get(name) or _counted(name) or name} {TYPES[kind]}"


UNITS = {
    "feet": "ft",
    "foot": "ft",
    "inches": "in",
    "inch": "in",
    "meters": "m",
    "meter": "m",
    "metres": "m",
    "metre": "m",
    "kilometers": "km",
    "kilometer": "km",
    "kilometres": "km",
    "kilometre": "km",
    "miles per hour": "mph",
    "minutes": "min",
    "minute": "min",
    "seconds": "sec",
    "second": "sec",
    "pounds": "lb",
    "pound": "lb",
    "lbs": "lb",
    "kilograms": "kg",
    "kilogram": "kg",
    "millimeters": "mm",
    "millimeter": "mm",
    "millimetres": "mm",
    "millimetre": "mm",
    "centimeters": "cm",
    "centimeter": "cm",
    "centimetres": "cm",
    "centimetre": "cm",
    "tonnes": "t",
    "tonne": "t",
    "decibels": "dB",
    "decibel": "dB",
    "hertz": "Hz",
    "volts": "V",
    "volt": "V",
    "kilovolts": "kV",
    "kilovolt": "kV",
    "kilowatts": "kW",
    "kilowatt": "kW",
    "megawatts": "MW",
    "megawatt": "MW",
    "kilometers per hour": "km/h",
    "kilometres per hour": "km/h",
    "kmh": "km/h",
    "kph": "km/h",
    "trains per hour": "tph",
}
"""How a unit is written after a number, and every spelling that is not it.

A symbol has no plural, which is why `lbs` is in here beside `pounds`:
`3 lb` is how the unit is written however many of them there are.

`kmh` and `kph` are in here for the same reason as `lbs`: they are the
spellings somebody reaches for, and neither is the symbol.
The symbol is `km/h`, which is the two units it is made of.

The ones the reports already write as symbols are in here too, from the
other side: `750 V`, `232 t`, `83 dB`, `2.9 mm`, `33 tph`. Each is written
right today, and the spelled-out form is what the check is for.

`mile` is not, and is the one length these reports spell out:
`two miles` is a distance a reader pictures,
where `137 ft` and `1.2 km` are measurements a reader compares.
"""


TIME_UNITS = frozenset({"minutes", "minute", "seconds", "second"})
"""Units that may be written out as well as abbreviated: the times.

`3 min` and `3 minutes` are both how these reports write a headway,
and a time is read in a sentence rather than compared down a column,
so neither spelling is wrong. The symbols are still read as units.
"""

SYMBOLS = frozenset(UNITS.values())
"""The symbols themselves, for a measurement that is already spelled right."""

LONGEST_UNIT = max(len(unit.split()) for unit in UNITS)
"""How many words a unit can be: `miles per hour` is the long one."""


def _unit(words: list[tuple[str, int]], first: int) -> tuple[str, int] | None:
    """The unit the words from `first` spell, and where it ends.

    The longest reading wins, so `miles per hour` is the unit it is
    rather than the `miles` at the front of it.
    """
    for length in range(LONGEST_UNIT, 0, -1):
        taken = words[first : first + length]
        if len(taken) < length:
            continue
        unit = " ".join(_bare(word) for word, _ in taken)
        if unit in UNITS or unit in SYMBOLS:
            word, at = taken[-1]
            return unit, _at(word, at) + len(_bare(word))
    return None


def _measurements(text: str) -> Iterator[tuple[int, int, str, str, str]]:
    """Every number written next to a unit: where it is, and its three pieces.

    The gap says which of the two rules has something to say about it,
    a space or the hyphen of `a 600-foot train`,
    and the unit is yielded as written, symbol or word,
    because the hyphen is worth saying either way.
    """
    words = _words(text)
    for i, (word, at) in enumerate(words):
        yield from _hyphenated(word, at)
        amount = _trailing_number(_bare(word))
        if amount is None:
            continue
        found = _unit(words, i + 1)
        if found is None:
            continue
        unit, end = found
        start = _at(word, at) + len(_bare(word)) - len(amount)
        yield start, end, amount, " ", unit


def _trailing_number(word: str) -> str | None:
    """The number `word` ends with, which is the one a unit after it counts.

    `6-8 minutes` is a range, and the eight is what the minutes are:
    the reports write four of these.
    """
    return _number(word.rpartition("-")[2])


def _hyphenated(word: str, at: int) -> Iterator[tuple[int, int, str, str, str]]:
    """Each number joined to a unit inside one word: `600-foot`, `1.5-2-min`."""
    parts = _bare(word).split("-")
    offset = _at(word, at)
    for first, second in zip(parts, parts[1:], strict=False):
        amount = _number(first)
        if amount is not None and (second in UNITS or second in SYMBOLS):
            yield offset, offset + len(first) + 1 + len(second), amount, "-", second
        offset += len(first) + 1


def _defines(text: str, end: int, symbol: str) -> bool:
    """Whether the symbol follows in brackets, which is a unit being introduced.

    SAS West writes `30 trains per hour (tph)` once and `33 tph` after it,
    which is how an abbreviation is handed to a reader.
    Spelling it out there is the point rather than the mistake.
    """
    return text.startswith(f" ({symbol})", end)


def _check_units(doc: Document, text: str) -> None:
    """A measurement whose unit is spelled out where the symbol is the style.

    These reports are full of them, and they are read against each other:
    `137 ft`, `140 ft`, `969 ft` down a column is a comparison,
    where the same numbers spelled out is a paragraph to read twice.

    The house's own, unlike the station names: the MTA writes `125 St` on its
    signs, and how a report abbreviates a kilogram is nothing to do with it.
    """
    for start, end, amount, gap, unit in _measurements(text):
        symbol = UNITS.get(unit)
        if symbol is None or unit in TIME_UNITS or _defines(text, end, symbol):
            continue
        _warn(
            doc,
            "{} should be {}: {}",
            Shown(text[start:end]),
            Shown(f"{amount}{gap}{symbol}"),
            Highlighted(_before(text, start), text[start:end], _after(text, end)),
        )


def _check_hyphenated_units(doc: Document, text: str) -> None:
    """A measurement hyphenated into the phrase it modifies.

    The hyphen is right, as English: `a 600 ft cavern` is one adjective.
    It is dropped all the same, so that a measurement is written one way
    wherever it appears and a search for `600 ft` finds every one of them
    rather than the ones that happened not to be describing anything.

    What it says to write is the whole measurement, `600 ft`,
    spelled out unit and all. A unit spelled out is the other warning's to
    make, and this one says it too rather than leaving somebody to write
    `600 foot` and be told about it on the next build.
    """
    for start, end, amount, gap, unit in _measurements(text):
        if gap != "-":
            continue
        _warn(
            doc,
            "{} should be {}, with no hyphen: {}",
            Shown(text[start:end]),
            Shown(f"{amount} {unit if unit in TIME_UNITS else UNITS.get(unit, unit)}"),
            Highlighted(_before(text, start), text[start:end], _after(text, end)),
        )


SCALES = ("thousand", "million", "billion", "trillion")
"""What sits between a sum and the word `dollars`, and never inside a percentage.

The amount is carried through to the symbol with it:
`7.7 billion dollars` is `$7.7 billion`, not `$7.7 billion dollars`.
"""

PERCENT = ("percent", "per cent")
MONEY = ("dollars", "dollar")

DATED = "in"
"""What says the number dates the dollars rather than counting them.

`in 2026 dollars` is the year a cost is inflated to, and the `in` says so
whatever the number is: `in 5 dollars` is the year 5, not five dollars.
That is what makes it the clearer half of the test:
it holds for years no rule about four digits would recognize.
"""

YEARS = range(1900, 2100)
"""Numbers that date the dollars rather than counting them.

Beside `DATED` rather than instead of it, for `2026 dollars` written with no
`in` in front. Either way `$2026` is nothing.
A year is only a year here where no scale follows it:
`2026 million dollars` would be a sum of money written strangely.
"""


def _spelled_out_symbol(words: list[tuple[str, int]], first: int) -> tuple[str, str, int] | None:
    """The scale and the word for a symbol that follow `first`, and where they end."""
    scale = ""
    at = first
    if at < len(words) and _bare(words[at][0]).lower() in SCALES:
        scale = f" {_bare(words[at][0]).lower()}"
        at += 1
    for length in (2, 1):
        taken = words[at : at + length]
        if len(taken) < length:
            continue
        word = " ".join(_bare(w).lower() for w, _ in taken)
        if word in PERCENT or word in MONEY:
            last, where = taken[-1]
            return scale, word, _at(last, where) + len(_bare(last))
    return None


def _check_spelled_out_symbols(doc: Document, text: str) -> None:
    """A percentage or a sum of money written as a word.

    These reports are an argument about costs, and the costs are read against
    each other: `$7.7 billion`, `$4.5 billion per mile`, `92%` are what a
    reader compares at a glance, where the same numbers in words are prose to
    work through. The symbol is also what every figure in them already uses.
    """
    words = _words(text)
    for i, (word, at) in enumerate(words):
        amount = _number(word)
        if amount is None:
            continue
        found = _spelled_out_symbol(words, i + 1)
        if found is None:
            continue
        scale, said, end = found
        money = said in MONEY
        dated = (i and _bare(words[i - 1][0]).lower() == DATED) or _is_year(amount)
        if money and not scale and dated:
            continue
        start = _at(word, at)
        _warn(
            doc,
            "{} should be {}: {}",
            Shown(text[start:end]),
            Shown(f"${amount}{scale}" if money else f"{amount}%"),
            Highlighted(_before(text, start), text[start:end], _after(text, end)),
        )


def _is_year(amount: str) -> bool:
    """Whether a number reads as a year rather than as a quantity."""
    return amount.isdigit() and int(amount) in YEARS
