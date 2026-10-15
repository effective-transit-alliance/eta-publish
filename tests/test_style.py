"""How a report is written, as distinct from what it says."""

import pytest

from eta_publish.nodes import Document, Footnote, Highlighted, Paragraph, Text
from eta_publish.style import style


def written(*paragraphs: str) -> Document:
    """A document that says these paragraphs and nothing else."""
    return Document(blocks=[Paragraph(content=[Text(text=p)]) for p in paragraphs])


def cited(text: str) -> Document:
    """A document whose only words are a footnote's, which are somebody else's."""
    doc = Document()
    doc.footnotes = [
        Footnote(footnote_id="f1", number=1, content=[Paragraph(content=[Text(text=text)])])
    ]
    return doc


def warnings(doc: Document) -> list[str]:
    style(doc)
    return [str(w) for w in doc.warnings]


def test_one_space_after_a_sentence_is_not_warned_about() -> None:
    assert warnings(written("It is deep. It is also expensive.")) == []


def test_two_spaces_after_a_sentence_are_warned_about() -> None:
    found = warnings(written("It is deep.  It is also expensive."))
    assert len(found) == 1
    assert "1 space, not 2" in found[0]


def test_the_warning_shows_which_spaces_it_means() -> None:
    """The spaces themselves, drawn: quoted as spaces they are a space,
    in HTML and in the PDF alike, and the line reads as already correct."""
    found = warnings(written("It is deep.  It is also expensive."))
    assert "It is deep.\u00b7\u00b7It is also expensive." in found[0]


def test_a_closing_bracket_does_not_hide_the_gap() -> None:
    """`costs are given separately).  This` is how the real report writes one:
    the spaces come after the sentence, whatever closes the quote around it."""
    assert len(warnings(written("(costs are given separately.)  This is a Buy America cost."))) == 1


def test_three_spaces_are_counted_rather_than_rounded_to_two() -> None:
    found = warnings(written("It is deep.   It is expensive."))[0]
    assert "1 space, not 3" in found
    assert "deep.\u00b7\u00b7\u00b7It" in found


def test_two_spaces_mid_clause_are_a_different_warning() -> None:
    """`demand  requires` is a slipped finger rather than the typewriter habit,
    so it is said differently even though the characters are the same."""
    found = warnings(written("On such routes, demand  requires high frequency."))
    assert found == [
        "style: two words should be separated by 1 space, not 2: "
        "`On such routes, demand\u00b7\u00b7requires high frequency.`"
    ]


def test_indentation_is_neither_mistake() -> None:
    """A run at the start or the end of a line is not two words run together."""
    assert warnings(written("  It is deep.")) == []
    assert warnings(written("It is deep.  ")) == []


def test_a_footnote_is_read_like_the_body() -> None:
    """A footnote carries the report's own prose as often as a citation,
    and a citation is published here under this report's name too."""
    assert len(warnings(cited('Barbara Russo-Lennon, "Subway spots.  The ad blitz."'))) == 1


def test_a_curled_apostrophe_is_not_warned_about() -> None:
    assert warnings(written("The MTA\u2019s trains don\u2019t wait.")) == []


def test_a_straight_apostrophe_is_warned_about() -> None:
    found = warnings(written("The MTA's trains don\u2019t wait."))
    assert len(found) == 1
    assert "MTA's" in found[0]


def test_a_straight_quote_around_words_is_not_an_apostrophe() -> None:
    assert warnings(written("It was called 'automation' then.")) == []


def test_a_closed_up_dash_is_not_warned_about() -> None:
    assert warnings(written("They are unfixable mistakes—while the debt is not.")) == []


def test_a_range_is_not_warned_about() -> None:
    """`10–20 ft` is how the reports write a range, and it is closed up already."""
    assert warnings(written("Groundwater is only 10–20 ft deep.")) == []


def test_a_spaced_em_dash_is_warned_about() -> None:
    found = warnings(written("They are unfixable mistakes — while the debt is not."))
    assert found == [
        "style: an em dash should not have spaces: "
        "`They are unfixable mistakes\u00b7—\u00b7while the debt is not.`"
    ]


def test_a_dash_spaced_on_one_side_is_warned_about() -> None:
    assert len(warnings(written("It is cheaper —and faster."))) == 1


def test_a_spaced_en_dash_is_warned_about() -> None:
    found = warnings(written("It spans 125 St, 2 – 3x the station width."))
    assert len(found) == 1
    assert found[0].startswith("style: an en dash should not have spaces: ")


def test_a_hyphen_is_not_a_dash() -> None:
    """`pipe-jacking` is one word, and `2 - 3` is a different thing to say."""
    assert warnings(written("The pipe-jacking at Jing\u2019an Temple station.")) == []


def test_a_range_written_with_a_hyphen_is_warned_about() -> None:
    found = warnings(written("Trains every 5-10 minutes, from 2027-2031."))
    assert len(found) == 2
    assert all("en dash" in w for w in found)


def test_a_range_with_an_en_dash_is_not_warned_about() -> None:
    assert warnings(written("Trains every 5\u201310 minutes.")) == []


@pytest.mark.parametrize(
    "text",
    [
        "Opened on 2024-05-01.",
        "Call 212-555-0100.",
        "See nyc.gov/report-2024-5 for more.",
        "The R211-T cars.",
        "A 3-car train.",
        "See https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242) there.",
    ],
)
def test_what_only_looks_like_a_range_is_not_warned_about(text: str) -> None:
    assert warnings(written(text)) == []


def test_a_footnote_dash_is_read_like_the_body() -> None:
    assert len(warnings(cited('Barbara Russo-Lennon, "Subway spots — the ad blitz."'))) == 1


def test_the_initials_on_their_own_are_not_warned_about() -> None:
    assert warnings(written("ETA recommended reducing the scope.")) == []


def test_an_article_before_the_initials_is_warned_about() -> None:
    found = warnings(written("For the same reason, the ETA recommended reducing the scope."))
    assert len(found) == 1
    assert "`the ETA`" in found[0]
    assert "`the Effective Transit Alliance`" in found[0]


def test_a_sentence_opening_with_it_is_the_same_mistake() -> None:
    assert len(warnings(written("The ETA recommended reducing the scope."))) == 1


def test_the_name_spelled_out_keeps_its_article() -> None:
    assert warnings(written("The Effective Transit Alliance recommended reducing it.")) == []


def test_a_possessive_is_still_the_initials() -> None:
    assert len(warnings(written("Read the ETA’s response to the MTA."))) == 1


def test_a_word_beginning_with_the_initials_is_not_them() -> None:
    assert warnings(written("The ETAs quoted were all optimistic.")) == []


def test_a_footnote_saying_the_initials_is_warned_about() -> None:
    assert len(warnings(cited('Barbara Russo-Lennon, "What the ETA wants."'))) == 1


def test_the_header_is_read_like_the_body() -> None:
    """`Short:` publishes as the standfirst and `SEO Description:` as what a
    search result shows, and the header is consumed before the body walk,
    so neither is reached by walking the blocks."""
    doc = Document()
    doc.meta = {"Short": "It is deep.  It is also expensive."}
    assert len(warnings(doc)) == 1


def test_a_header_field_saying_the_initials_is_warned_about() -> None:
    doc = Document()
    doc.meta = {"SEO Description": "The ETA outlines the best practices."}
    assert len(warnings(doc)) == 1


def test_every_warning_says_it_is_about_style() -> None:
    """The rest of a document's warnings are things the build could not do,
    and these are things somebody may want to write differently,
    which is a different thing to go and fix."""
    found = warnings(written("It is deep.  The ETA said so — twice."))
    assert len(found) == 3
    assert all(w.startswith("style: ") for w in found)


def test_the_gap_is_carried_as_its_own_piece_of_the_excerpt() -> None:
    """So a terminal can highlight it without having to find it again,
    and so a document writing a middle dot of its own is never mistaken for one."""
    doc = written("It is deep.  It is expensive.")
    style(doc)
    (part,) = [p for p in doc.warnings[0].parts if isinstance(p, Highlighted)]
    assert (part.before, part.marked, part.after) == (
        "It is deep.",
        "\u00b7\u00b7",
        "It is expensive.",
    )


def test_a_station_written_the_way_the_mta_writes_it_is_left_alone() -> None:
    assert warnings(written("The ventilation structure at 69 St and 2 Av.")) == []


def test_an_ordinal_loses_its_suffix_and_the_kind_is_abbreviated() -> None:
    found = warnings(written("The proposed 125th Street extension."))
    assert found == [
        "style: `125th Street` should be `125 St`: `The proposed 125th Street extension.`"
    ]


def test_an_avenue_is_av_rather_than_ave() -> None:
    assert "`2 Av`" in warnings(written("Blasting at the 2nd Ave site."))[0]


def test_a_named_street_is_abbreviated_too() -> None:
    assert "`Fordham Rd`" in warnings(written("Circumferential routes such as Fordham Road."))[0]


def test_every_kind_the_mta_spells_its_own_way() -> None:
    for name, correct in (
        ("Queens Boulevard", "Queens Blvd"),
        ("Henry Hudson Parkway", "Henry Hudson Pkwy"),
        ("Union Square", "Union Sq"),
        ("Sutphin Place", "Sutphin Pl"),
    ):
        assert f"`{correct}`" in warnings(written(f"It runs along {name} today."))[0]


def test_a_spelled_out_number_is_a_digit_like_any_other() -> None:
    """The station on Second Avenue is `2 Av`, on every sign the MTA prints."""
    assert "`2 Av`" in warnings(written("The stations along Second Avenue are deep."))[0]
    assert "`5 Av`" in warnings(written("It runs under Fifth Ave for a mile."))[0]


def test_the_second_avenue_subway_is_left_as_the_mta_names_it() -> None:
    assert warnings(written("The Second Avenue Subway opened in 2017.")) == []


def test_the_project_is_corrected_towards_its_name_rather_than_the_station() -> None:
    """`Second Ave Subway` is the project written short, not a station,
    so the warning names the whole phrase rather than half of it."""
    assert (
        "`Second Ave Subway` should be `Second Avenue Subway`"
        in warnings(written("The cost of the Second Ave Subway."))[0]
    )


def test_the_project_is_named_however_it_was_written() -> None:
    """SAS West writes `Second Ave subway` twice, abbreviated and lowercase,
    and the name it is reaching for is the one it is corrected to."""
    assert (
        "should be `Second Avenue Subway`"
        in warnings(written("Features of the Second Ave subway."))[0]
    )


def test_an_ordinal_that_names_no_street_is_not_a_street() -> None:
    """`the 4th grade` is a slope in the IBX report, and `4 grade` is nothing."""
    assert warnings(written("The steepest of these grades is the 4th grade.")) == []


def test_a_street_in_another_city_keeps_its_own_name() -> None:
    """`Nanba Rd` is a name nothing anywhere calls it."""
    assert warnings(written("Cross-traffic on Nanba Road could move underground.")) == []
    assert warnings(written("The Green Line Extension reaches Ball Square.")) == []
    assert warnings(written("The light rail stops at Jersey Avenue.")) == []


def test_a_court_is_a_name_rather_than_a_kind_of_street() -> None:
    """The station is `Court Sq`: the court is the name and the square is the
    kind, so abbreviating the court would rename it."""
    assert warnings(written("The train terminates at Court Square today.")) == [
        "style: `Court Square` should be `Court Sq`: `The train terminates at Court Square today.`"
    ]


def test_a_railroad_is_not_a_road() -> None:
    assert warnings(written("Metro-North and the Long Island Rail Road both.")) == []


def test_an_ordinary_phrase_is_not_a_street() -> None:
    """`Place`, `Square` and `Drive` are words as well as streets,
    and no street is `The` anything."""
    assert warnings(written("Ruling Grade: The Wrong Place to Scale Back")) == []


def test_a_slug_is_not_a_street_name() -> None:
    """A URL and a filename write it without the space that names one."""
    assert warnings(written("Uncropped Source: 96st_station, sas-west-72nd-street.jpg")) == []


def test_the_joke_on_the_project_name_keeps_the_name_it_is_on() -> None:
    """SAS West calls the line the so-called `Second Avenue Stubway`,
    which only works while it is spelled like what it is playing on."""
    assert warnings(written("The so-called “Second Avenue Stubway” made three stops.")) == []
    assert (
        "should be `Second Avenue Stubway`"
        in warnings(written("Riding the Second Ave Stubway."))[0]
    )


def test_a_time_may_be_written_out_or_abbreviated() -> None:
    assert warnings(written("It cost riders 5 minutes every trip.")) == []
    assert warnings(written("It cost riders 5 min every trip.")) == []
    assert warnings(written("Doors close in 20 seconds.")) == []


def test_a_hyphenated_time_keeps_its_word() -> None:
    found = warnings(written("It runs on 3-minute headways."))
    assert len(found) == 1
    assert "`3 minute`" in found[0]


def test_a_unit_after_a_number_is_the_symbol() -> None:
    assert "`130 ft`" in warnings(written("Stations between 100 and 130 feet down."))[0]
    assert "`180 m`" in warnings(written("Trains of 180 meters or longer."))[0]
    assert "`6 in`" in warnings(written("Openings only 6 inches above the road."))[0]


def test_a_symbol_has_no_plural() -> None:
    """`3 lb` is how the unit is written however many of them there are."""
    assert "`72,000 lb`" in warnings(written("A weight of 72,000 lbs per car."))[0]


def test_a_unit_already_written_as_a_symbol_is_left_alone() -> None:
    assert warnings(written("It is 137 ft deep, 1.2 km long, and 2 kg lighter.")) == []


def test_a_mile_stays_a_word() -> None:
    """The one length these reports spell out:
    a distance a reader pictures rather than a measurement they compare."""
    assert warnings(written("It runs two miles north, or about 2 miles.")) == []


def test_a_number_written_as_a_word_is_left_alone() -> None:
    """`ten minutes` is a duration somebody is describing,
    and `10 min` is one they are measuring."""
    assert warnings(written("The walk takes ten minutes from the mezzanine.")) == []


def test_the_second_avenue_is_not_a_second() -> None:
    """`second` is a unit and an avenue, and only one of them follows a number."""
    assert warnings(written("The Second Avenue Subway opened.")) == []


def test_a_measurement_is_not_hyphenated_into_what_it_describes() -> None:
    """The hyphen is right as English and dropped all the same,
    so a search for `600 ft` finds every one of them rather than the ones
    that happened not to be describing anything."""
    found = warnings(written("The extreme 1-min headways of Lille."))
    assert found == [
        "style: `1-min` should be `1 min`, with no hyphen: `The extreme 1-min headways of Lille.`"
    ]


def test_the_hyphen_and_the_spelling_are_two_warnings() -> None:
    """Two mistakes in one measurement, said separately.
    The hyphen one says the whole of what to write rather than leaving
    somebody to write `600 foot` and be told about it on the next build."""
    found = warnings(written("The capacity of a 600-foot train."))
    assert len(found) == 2
    assert "`600-foot` should be `600-ft`" in found[0]
    assert "`600-foot` should be `600 ft`, with no hyphen" in found[1]


def test_an_ordinary_hyphenated_phrase_is_not_a_measurement() -> None:
    """`2-track`, `4-car` and `NFPA 130-compliant` are hyphenated for the
    ordinary reason, and the reports are full of them."""
    assert warnings(written("It has 2-track lines, 4-car sets, and is NFPA 130-compliant.")) == []


def test_the_units_the_reports_already_write_as_symbols() -> None:
    """`750 V`, `232 t`, `83 dB`, `2.9 mm` and `33 tph` are right today,
    and the spelled-out form is what the check is for."""
    assert warnings(written("At 750 V, 232 t, 83 dB, 2.9 mm, and 33 tph.")) == []
    for spelled, symbol in (
        ("750 volts", "750 V"),
        ("83 decibels", "83 dB"),
        ("3 millimeters", "3 mm"),
        ("232 tonnes", "232 t"),
        ("1.5 kilovolts", "1.5 kV"),
        ("60 hertz", "60 Hz"),
        ("30 trains per hour", "30 tph"),
    ):
        assert f"`{symbol}`" in warnings(written(f"It runs at {spelled} today."))[0]


def test_a_unit_introduced_with_its_symbol_is_being_defined() -> None:
    """SAS West writes `30 trains per hour (tph)` once and `33 tph` after it,
    which is how an abbreviation is handed to a reader."""
    assert warnings(written("Lines run 30 trains per hour (tph) without tail tracks.")) == []


def test_a_percentage_is_a_symbol() -> None:
    assert "`3.5%`" in warnings(written("Costs rose 3.5 percent last year."))[0]
    assert "`92%`" in warnings(written("Utilization of 92 per cent is assumed."))[0]


def test_money_is_a_symbol_in_front_of_the_number() -> None:
    """The scale comes with it: `$7.7 billion`, not `$7.7 billion dollars`."""
    assert "`$7.7 billion`" in warnings(written("A cost of 7.7 billion dollars."))[0]
    assert "`$5`" in warnings(written("It would cost 5 dollars a ride."))[0]


def test_a_symbol_already_written_is_left_alone() -> None:
    assert warnings(written("At $7.7 billion and 92%, it is the most expensive.")) == []


def test_a_year_dates_the_dollars_rather_than_counting_them() -> None:
    """`in 2026 dollars` is what a cost is inflated to, and `$2026` is nothing."""
    assert warnings(written("That is $4.5 billion per mile in 2026 dollars.")) == []


def test_a_scale_says_a_year_is_a_sum_after_all() -> None:
    assert "`$2026 million`" in warnings(written("A cost of 2026 million dollars."))[0]


def test_the_in_is_what_says_the_dollars_are_dated() -> None:
    """The `in` says so whatever the number is,
    which is why it holds for years no pattern would recognize as one."""
    assert warnings(written("That is $4.5 billion per mile in 2050 dollars.")) == []
    assert warnings(written("Costs are given in 2026 dollars throughout.")) == []
    assert warnings(written("A denarius bought more in 5 dollars than today.")) == []


def test_a_speed_is_written_as_the_two_units_it_is_made_of() -> None:
    """`kmh` and `kph` are what somebody reaches for, and neither is the symbol."""
    for written_as in ("80 kmh", "80 kph", "80 kilometers per hour"):
        assert "`80 km/h`" in warnings(written(f"It runs at {written_as} today."))[0]
    assert warnings(written("It runs at 80 km/h today.")) == []
