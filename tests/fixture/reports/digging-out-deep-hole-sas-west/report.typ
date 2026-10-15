#import "template.typ": capped_image, report

#show: report.with(
  title: "Digging Out of a Very Deep Hole: Saving Billions on 125th Street",
  headline: [Digging Out of a Very Deep Hole: Saving Billions on 125th Street],
  subtitle: none,
  phase: "",
  dateline: "",
  contributors: (),
  contributors_note: "We wish to acknowledge the following ETA members who contributed to this report, and without whose hard work it would not be possible:",
  warnings: (
    [the #raw("Header") section has an unrecognized #raw("MTA SAS West Feasibility Study:") line; check it for a typo],
  ),
)

= The Elephants in the Room

SAS West is projected to cost #strong[\$7.7 billion] for 1.25 miles#footnote[Inflation-adjusted from the 2024 capital plan.], per the #link("https://www.mta.info/document/196361")[MTA study]#super[#link(<src1>)[\[1\]]].

#figure(
  link("https://kkysen.github.io/eta-publish/reports/digging-out-deep-hole-sas-west/images/sas-west-036.png")[#capped_image("print/sas-west-036.jpg", alt: "SAS West alignment map")],
  caption: [The SAS West and Phase 2 alignments. \
  Credit: MTA],
)

That is a lot of money.

#table(
  columns: 2,
  [#strong[Project]],
  [#strong[Cost per mile]],
  [SAS West],
  [\$6.2B],
  [Grand Paris Express],
  [\$530M],
)

== Ground Conditions

- First point
  - Nested point
- Second point

Stations are over 100 ft deep.#footnote[Measured from street level to platform.]

= Sources

#[
#set par(justify: false)
#set text(hyphenate: false)
+ (not archived) #link("https://www.mta.info/document/196361")[mta.info/document/196361] <src1>
]
