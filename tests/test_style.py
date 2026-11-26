"""How a publication is written, as distinct from what it says.

Each test is one realistic document, built the way a build builds one,
with a paragraph for each thing a writer might do.
A paragraph that is fine is there to be left alone, so each list of warnings
says what the writer is told about the mistakes and nothing about the rest.
"""

from pathlib import Path

from docs_json import HEADER, build, cites, drafted, footnote, link, para, rich, warned

from eta_publish.docs_json import JsonObject
from eta_publish.nodes import Inline, Text, plain_text
from eta_publish.style import _prose


def paragraphs(*texts: str) -> list[JsonObject]:
    """One paragraph for each text."""
    return [para(text) for text in texts]


def test_spacing_punctuation_and_the_initials(tmp_path: Path) -> None:
    body = [
        # Spaces: after a sentence, inside one, and at the edge of a line.
        *paragraphs(
            "It is deep. It is also expensive.",
            "It is deep.  It is also expensive.",
            "(costs are given separately.)  This is a Buy America cost.",
            "It is deep.   It is expensive.",
            "On such routes, demand  requires high frequency.",
            "  It is deep.",
            "It is deep.  ",
        ),
        # Apostrophes and quotes.
        *paragraphs(
            "The MTA’s trains don’t wait.",
            "The MTA's trains don’t wait.",
            "It was called 'automation' then.",
        ),
        # Dashes and ranges.
        *paragraphs(
            "They are unfixable mistakes—while the debt is not.",
            "Groundwater is only 10–20 ft deep.",
            "They are unfixable mistakes — while the debt is not.",
            "It is cheaper —and faster.",
            "It spans 125 St, 2 – 3x the station width.",
            "The pipe-jacking at Jing’an Temple station.",
            "Trains every 5-10 minutes, from 2027-2031.",
            "Trains every 5–10 minutes.",
            "Opened on 2024-05-01.",
            "Call 212-555-0100.",
            "See nyc.gov/report-2024-5 for more.",
            "The R211-T cars.",
            "A 3-car train.",
            "Change at 47-50 Sts/6 Av for the F.",
            "See https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242) there.",
        ),
        # The initials.
        *paragraphs(
            "ETA recommended reducing the scope.",
            "For the same reason, the ETA recommended reducing the scope.",
            "The ETA recommended reducing the scope.",
            "The Effective Transit Alliance recommended reducing it.",
            "Read the ETA’s response to the MTA.",
            "The ETAs quoted were all optimistic.",
        ),
        # A footnote is read like the body, whoever it cites.
        rich(
            "A spacing slip",
            cites("fn.spaces"),
            ", a dash",
            cites("fn.dash"),
            ", the initials",
            cites("fn.initials"),
            ".",
        ),
    ]
    site, _ = build(
        tmp_path,
        drafted(
            body,
            changes={
                "Short": "It is deep.  It is also expensive.",
                "SEO Description": "The ETA outlines the best practices.",
            },
            footnotes={
                "fn.spaces": footnote('Barbara Russo-Lennon, "Subway spots.  The ad blitz."'),
                "fn.dash": footnote('Barbara Russo-Lennon, "Subway spots — the ad blitz."'),
                "fn.initials": footnote('Barbara Russo-Lennon, "What the ETA wants."'),
            },
        ),
    )
    assert warned(site) == [
        "1 URL typed out but not linked; link it in the doc:\n"
        "- `https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242)`",
        "style: a sentence should end with 1 space, not 2: `It is deep.\u00b7\u00b7It is "
        "also expensive.`",
        "style: `ETA` is written `The ETA`; it is `ETA` on its own, and `the "
        "Effective Transit Alliance` spelled out: `The ETA outlines the best "
        "practices.`",
        "style: a sentence should end with 1 space, not 2: `It is deep.\u00b7\u00b7It is "
        "also expensive.`",
        "style: a sentence should end with 1 space, not 2: `(costs are given "
        "separately.)\u00b7\u00b7This is a Buy America cost.`",
        "style: a sentence should end with 1 space, not 3: `It is deep.\u00b7\u00b7\u00b7It "
        "is expensive.`",
        "style: two words should be separated by 1 space, not 2: `On such "
        "routes, demand\u00b7\u00b7requires high frequency.`",
        "style: an apostrophe should be `\u2019`, not `'`: `The MTA's trains don\u2019t wait.`",
        "style: an em dash should not have spaces: `They are unfixable "
        "mistakes\u00b7\u2014\u00b7while the debt is not.`",
        "style: an em dash should not have spaces: `It is cheaper\u00b7\u2014and faster.`",
        "style: an en dash should not have spaces: `It spans 125 St, 2\u00b7\u2013\u00b73x "
        "the station width.`",
        "style: a range should use an en dash, `\u2013`, not a hyphen: `Trains "
        "every 5-10 minutes, from 2027-2031.`",
        "style: a range should use an en dash, `\u2013`, not a hyphen: `... every "
        "5-10 minutes, from 2027-2031.`",
        "style: `ETA` is written `the ETA`; it is `ETA` on its own, and `the "
        "Effective Transit Alliance` spelled out: `For the same reason, the "
        "ETA recommended reducing the scop...`",
        "style: `ETA` is written `The ETA`; it is `ETA` on its own, and `the "
        "Effective Transit Alliance` spelled out: `The ETA recommended "
        "reducing the scop...`",
        "style: `ETA` is written `the ETA`; it is `ETA` on its own, and `the "
        "Effective Transit Alliance` spelled out: `Read the ETA\u2019s response to "
        "the MTA.`",
        "style: a sentence should end with 1 space, not 2: `...a Russo-Lennon, "
        '"Subway spots.\u00b7\u00b7The ad blitz."`',
        "style: an em dash should not have spaces: `...ra Russo-Lennon, "
        '"Subway spots\u00b7\u2014\u00b7the ad blitz."`',
        "style: `ETA` is written `the ETA`; it is `ETA` on its own, and `the "
        'Effective Transit Alliance` spelled out: `Barbara Russo-Lennon, "What '
        'the ETA wants."`',
    ]


def test_streets_and_the_second_avenue_subway(tmp_path: Path) -> None:
    body = paragraphs(
        # The way the MTA writes a station.
        "The ventilation structure at 69 St and 2 Av.",
        "The proposed 125th Street extension.",
        "Blasting at the 2nd Ave site.",
        "Circumferential routes such as Fordham Road.",
        "It runs along Queens Boulevard today.",
        "It runs along Henry Hudson Parkway today.",
        "It runs along Union Square today.",
        "It runs along Sutphin Place today.",
        "The stations along Second Avenue are deep.",
        "It runs under Fifth Ave for a mile.",
        # The project is not a station.
        "The Second Avenue Subway opened in 2017.",
        "The cost of the Second Ave Subway.",
        "Features of the Second Ave subway.",
        # Not a street at all, or not in New York.
        "The steepest of these grades is the 4th grade.",
        "Cross-traffic on Nanba Road could move underground.",
        "The Green Line Extension reaches Ball Square.",
        "The light rail stops at Jersey Avenue.",
        "Metro-North and the Long Island Rail Road both.",
        "Ruling Grade: The Wrong Place to Scale Back",
        "Uncropped Source: 96st_station, sas-west-72nd-street.jpg",
        # The court is the name and the square the kind.
        "The train terminates at Court Square today.",
        # The joke is on the name, so it keeps the name it is on.
        "The so-called “Second Avenue Stubway” made three stops.",
        "Riding the Second Ave Stubway.",
    )
    site, _ = build(tmp_path, drafted(body))
    assert warned(site) == [
        "style: `125th Street` should be `125 St`: `The proposed 125th Street extension.`",
        "style: `2nd Ave` should be `2 Av`: `Blasting at the 2nd Ave site.`",
        "style: `Fordham Road` should be `Fordham Rd`: `...ircumferential "
        "routes such as Fordham Road.`",
        "style: `Queens Boulevard` should be `Queens Blvd`: `It runs along "
        "Queens Boulevard today.`",
        "style: `Henry Hudson Parkway` should be `Henry Hudson Pkwy`: `It runs "
        "along Henry Hudson Parkway today.`",
        "style: `Union Square` should be `Union Sq`: `It runs along Union Square today.`",
        "style: `Sutphin Place` should be `Sutphin Pl`: `It runs along Sutphin Place today.`",
        "style: `Second Avenue` should be `2 Av`: `The stations along Second Avenue are deep.`",
        "style: `Fifth Ave` should be `5 Av`: `It runs under Fifth Ave for a mile.`",
        "style: `Second Ave Subway` should be `Second Avenue Subway`: `The "
        "cost of the Second Ave Subway.`",
        "style: `Second Ave subway` should be `Second Avenue Subway`: "
        "`Features of the Second Ave subway.`",
        "style: `Court Square` should be `Court Sq`: `The train terminates at Court Square today.`",
        "style: `Second Ave Stubway` should be `Second Avenue Stubway`: "
        "`Riding the Second Ave Stubway.`",
    ]


def test_units_money_and_measurements(tmp_path: Path) -> None:
    body = paragraphs(
        # A time may be written out or abbreviated; a hyphenated one keeps its word.
        "It cost riders 5 minutes every trip.",
        "It cost riders 5 min every trip.",
        "Doors close in 20 seconds.",
        "It runs on 3-minute headways.",
        "The extreme 1-min headways of Lille.",
        # A unit after a number is the symbol, and a symbol has no plural.
        "Stations between 100 and 130 feet down.",
        "Trains of 180 meters or longer.",
        "Openings only 6 inches above the road.",
        "A weight of 72,000 lbs per car.",
        "It is 137 ft deep, 1.2 km long, and 2 kg lighter.",
        # A mile stays a word, and so does a number that is one.
        "It runs two miles north, or about 2 miles.",
        "The walk takes ten minutes from the mezzanine.",
        # A measurement is not hyphenated into what it describes, and says so once.
        "The capacity of a 600-foot train.",
        "It has 2-track lines, 4-car sets, and is NFPA 130-compliant.",
        # The units the publications already write as symbols, and the spelled-out ones.
        "At 750 V, 232 t, 83 dB, 2.9 mm, and 33 tph.",
        "It runs at 750 volts today.",
        "It runs at 83 decibels today.",
        "It runs at 3 millimeters today.",
        "It runs at 232 tonnes today.",
        "It runs at 1.5 kilovolts today.",
        "It runs at 60 hertz today.",
        "It runs at 30 trains per hour today.",
        "Lines run 30 trains per hour (tph) without tail tracks.",
        # Percentages and money.
        "Costs rose 3.5 percent last year.",
        "Utilization of 92 per cent is assumed.",
        "A cost of 7.7 billion dollars.",
        "It would cost 5 dollars a ride.",
        "At $7.7 billion and 92%, it is the most expensive.",
        # A year dates the dollars rather than counting them, unless a scale says otherwise.
        "That is $4.5 billion per mile in 2026 dollars.",
        "A cost of 2026 million dollars.",
        "That is $4.5 billion per mile in 2050 dollars.",
        "Costs are given in 2026 dollars throughout.",
        "A denarius bought more in 5 dollars than today.",
        # A speed is the two units it is made of.
        "It runs at 80 kmh today.",
        "It runs at 80 kph today.",
        "It runs at 80 kilometers per hour today.",
        "It runs at 80 km/h today.",
    )
    site, _ = build(tmp_path, drafted(body))
    assert warned(site) == [
        "style: `3-minute` should be `3 minute`, with no hyphen: `It runs on 3-minute headways.`",
        "style: `1-min` should be `1 min`, with no hyphen: `The extreme 1-min headways of Lille.`",
        "style: `130 feet` should be `130 ft`: `Stations between 100 and 130 feet down.`",
        "style: `180 meters` should be `180 m`: `Trains of 180 meters or longer.`",
        "style: `6 inches` should be `6 in`: `Openings only 6 inches above the road.`",
        "style: `72,000 lbs` should be `72,000 lb`: `A weight of 72,000 lbs per car.`",
        "style: `600-foot` should be `600 ft`, with no hyphen: `The capacity of a 600-foot train.`",
        "style: `750 volts` should be `750 V`: `It runs at 750 volts today.`",
        "style: `83 decibels` should be `83 dB`: `It runs at 83 decibels today.`",
        "style: `3 millimeters` should be `3 mm`: `It runs at 3 millimeters today.`",
        "style: `232 tonnes` should be `232 t`: `It runs at 232 tonnes today.`",
        "style: `1.5 kilovolts` should be `1.5 kV`: `It runs at 1.5 kilovolts today.`",
        "style: `60 hertz` should be `60 Hz`: `It runs at 60 hertz today.`",
        "style: `30 trains per hour` should be `30 tph`: `It runs at 30 trains per hour today.`",
        "style: `3.5 percent` should be `3.5%`: `Costs rose 3.5 percent last year.`",
        "style: `92 per cent` should be `92%`: `Utilization of 92 per cent is assumed.`",
        "style: `7.7 billion dollars` should be `$7.7 billion`: `A cost of 7.7 billion dollars.`",
        "style: `5 dollars` should be `$5`: `It would cost 5 dollars a ride.`",
        "style: `2026 million dollars` should be `$2026 million`: `A cost of "
        "2026 million dollars.`",
        "style: `80 kmh` should be `80 km/h`: `It runs at 80 kmh today.`",
        "style: `80 kph` should be `80 km/h`: `It runs at 80 kph today.`",
        "style: `80 kilometers per hour` should be `80 km/h`: `It runs at 80 "
        "kilometers per hour today.`",
    ]


def runs(inlines: list[Inline]) -> list[str]:
    """The text of each run, to say which runs a piece of prose is read from."""
    return [i.text for i in inlines if isinstance(i, Text)]


def test_each_run_of_prose_comes_with_the_inlines_it_is_read_from(tmp_path: Path) -> None:
    """So a finding's offset in the text can be mapped to where it is in the document."""
    body = [
        para("Cheaper, faster.", "SUBTITLE"),
        rich("It is ", ("deep", {"bold": True}), cites("fn.deep"), "."),
        rich("See ", ("the report", link("https://example.org/report")), " for more."),
    ]
    footnotes = {"fn.deep": footnote("Cited, ", ("in full", {"italic": True}), ".")}
    site, _ = build(tmp_path, drafted(body, footnotes=footnotes))
    doc = site.built[0].doc
    # Past the header's values, which are read from the lines they were written on.
    assert [(p.text, runs(p.inlines)) for p in _prose(doc)][len(HEADER) :] == [
        ("Cheaper, faster.", ["Cheaper, faster."]),
        ("It is deep.", ["It is ", "deep", "."]),
        ("See the report for more.", ["See ", "the report", " for more."]),
        ("Cited, in full.", ["Cited, ", "in full", "."]),
    ]


def test_a_header_value_is_read_from_the_lines_it_was_written_on(tmp_path: Path) -> None:
    """Not from `meta`, where a wrapped value is its lines joined with a space:
    that string is in no one place in the document, and each of its lines is."""
    site, _ = build(
        tmp_path,
        drafted([para("Tunnels are deep.")], changes={"Short": " It is deep.  \v  It is  dear."}),
    )
    doc = site.built[0].doc
    assert doc.meta["Short"] == "It is deep. It is  dear."
    # Each value, the line it is read from, and where in the line it starts.
    assert [(p.text, plain_text(p.inlines), p.at) for p in _prose(doc)][: len(HEADER) + 1] == [
        ("Khyber Sen", "Project Manager: Khyber Sen", 17),
        ("Blair Lorenzo", "SME/Liaison: Blair Lorenzo", 13),
        ("Drafting", "Phase: Drafting", 7),
        ("#a-draft", "Discussion Channel: #a-draft", 20),
        ("2026-12-01", "Publish Due Date: 2026-12-01", 18),
        ("Make the case.", "Goals: Make the case.", 7),
        ("Planners.", "Audience: Planners.", 10),
        ("Alon Levy, Khyber Sen", "Public Contributors: Alon Levy, Khyber Sen", 21),
        ("Blair Lorenzo", "Private Contributors: Blair Lorenzo", 22),
        ("/reports/a-draft", "URL: /reports/a-draft", 5),
        ("It is deep.", "Short:  It is deep.  ", 8),
        ("It is  dear.", "  It is  dear.", 2),
        ("Cheaper, shallower, faster.", "SEO Description: Cheaper, shallower, faster.", 17),
        ("A Draft", "Social Title Card: A Draft", 19),
    ]
    # So the excerpt is the line the slip is on, not the value it is part of.
    assert warned(site) == [
        "a paragraph is broken with `Shift+Enter` rather than `Enter`, so lines "
        "that look separate are one paragraph; give each line its own:\n"
        "- `Short:  It is deep.`\n"
        "- `It is  dear.`",
        "style: two words should be separated by 1 space, not 2: `It is\u00b7\u00b7dear.`",
    ]
