#import "template.typ": capped_image, report

#show: report.with(
  title: "Monthly Passes",
  headline: [Monthly Passes],
  subtitle: none,
  phase: "",
  dateline: "",
  contributors: ("John Ericson", "Madison Feinberg", "Elijah Fischer", "Robert Hale", "Darius Jankauskas", "Tim Lazaroff", "Alon Levy", "Blair Lorenzo", "Samuel Santaella", "Khyber Sen", ),
  contributors_note: "We wish to acknowledge the following ETA members who contributed to this report, and without whose hard work it would not be possible:",
  hero: [
#figure(
  link("https://kkysen.github.io/eta-publish/reports/monthly-passes/images/img-ae6ddd33.jpg")[#capped_image("print/img-ae6ddd33.jpg")],
)
  ],
)

= Bring Back the Monthly: The Value of Affordable Transit Passes

#figure(
  link("https://kkysen.github.io/eta-publish/reports/monthly-passes/images/img-cf3f2056.jpg")[#capped_image("print/img-cf3f2056.jpg", alt: "Image: Tapping onto the subway with OMNY")],
  caption: [Image: Tapping onto the subway with OMNY],
)

Credit: Blair Lorenzo, ETA

== The Death of the Monthly

When the MTA retired the MetroCard at the end of last year, it also brought an end to something that had been familiar to New York straphangers for nearly 30 years: the monthly unlimited-ride pass.
Ever since the introduction of the unlimited-ride pass in 1998, regular subway and bus riders hadn’t needed to think about whether any given ride was worth the cost.
Instead, with just a single purchase each month, they could use transit for every trip without worry.

Monthly passes, however, have never been made available on MetroCard’s replacement, OMNY.
This is not a technical limitation.
Other open-loop payment systems—systems that accept any contactless payment—from around the world allow riders to buy unlimited passes.
This even includes the Port Authority’s new TAPP system, which uses identical technology to OMNY. 

Instead, the MTA has decided to move to an entirely new system based on weekly fare capping.
At least in theory, fare capping is designed to ensure that riders never pay more than \$35 (\$1 less than 12 rides) over seven days, although in reality, OMNY’s design has meant it doesn’t operate in the way many riders expect. #strong[This change not only eliminated a strong impetus to ride, but also effectively raised the fare for the MTA’s most loyal commuters by 14%], a massive jump considering that at the same time MetroCard was discontinued, the price of a single ride only increased by 3%#footnote[(\$35/7 days) / (\$132/30 days) = 1.136 vs \$3 / \$2.90 = 1.034].

In theory, fare capping should provide the same benefits as a transit pass.
OMNY’s implementation of fare capping, however, makes it unlikely to provide the same impetus for transportation usage as a normal transit pass.
One possible way to fix this would be to institute a monthly cap in addition to the weekly one to make the system more affordable for regular riders.
This would still leave a deeper issue than merely the lack of a monthly pass or an unlimited monthly cap option, an issue which may have encouraged the elimination of monthly passes for fare capping in the first place.

Even before it was discontinued, the MTA’s unlimited-ride pass was one of the most expensive transit passes in the world as measured by the number of rides required for the pass to break even.
This made the monthly pass a far less attractive option to riders than it should have been—and that was before the rise of hybrid and remote work and the decline of regular commuting.
The MTA pitched fare capping in part as a solution to ensure that riders weren’t wasting their investment. #strong[But this solved the wrong problem: rather than make passes less expensive, it only made it possible to purchase an overpriced pass piecemeal. ]

Other transit systems around both the country and the world not only continue to use monthly passes, but craft policies specifically designed to encourage as many riders to use them as possible.
For transit agencies, monthly passes provide regular, reliable revenue, reduce fare evasion, and reduce the cost of fare enforcement.
Perhaps more importantly, transit passes lead to an increase in ridership, especially at off-peak times.
This is because, for riders, a transit pass means freedom: taking transit is always an easy decision when the marginal cost of a trip is free.

Getting affordable passes into the hands of as many riders as possible boosts ridership while lowering costs.
The MTA and other transit agencies around the region should learn from the rest of the world, and reinstate a monthly pass option based on cost ratio comparable to New York’s peer cities.

== Why Monthly Passes Work

More than anything else, #strong[transit passes boost ridership].
As one study puts it, “Transit pass ownership status is the single most important variable associated with the daily number of transit trips made by urban residents.”#footnote[Badoe, D. & Yendeti, M., “Impact of Transit-Pass Ownership on Daily Number of Trips Made by Urban Public Transit,” #emph[Journal of Urban Planning and Development] (2007, 133:4, 242). https://doi.org/10.1061/(ASCE)0733-9488(2007)133:4(242)] This makes sense: once a rider has bought a pass, they no longer need to think about the marginal cost of any given trip, or how far away they are from hitting a fare cap.
Instead, they are simply free to hop on the next train or bus.

Transit passes are not just a boon to riders, however.
They are also a powerful tool for transit agencies:

- They #strong[drive all-day transit ridership], increasing utilization while lowering the per-passenger cost. Regular transit commuters to work or school are incentivized to buy a monthly pass, which then ensures that their other trips, during less busy times, have zero marginal cost.
- They bring #strong[predictable revenue streams] that are easy to plan around.
- They #strong[reduce fare evasion], as those who have already purchased a pass have no incentive to evade the fare. Faregate vendors credit their systems with reducing #emph[opportunistic] fare evasion,#footnote[Ironman Turnstile mentions this in its brochure, #link("https://www.ironmanturnstile.com/transportation-and-smart-hubs/")[https://www.ironmanturnstile.com/transportation-and-smart-hubs/]#super[#link(<src9>)[\[9\]]], and Cubic mentions that as an argument for reducing fare payment friction, #link("https://www.cubic.com/news-events/blogs/why-enforcement-cant-be-the-only-solution-for-transit-revenue-protection")[https://www.cubic.com/news-events/blogs/why-enforcement-cant-be-the-only-solution-for-transit-revenue-protection]#super[#link(<src10>)[\[10\]]].] and the same arguments apply to prepaid passes: there is no reason for most people to avoid the fare if they have already paid.
- They #strong[make all-door bus boarding and proof-of-payment easier to implement], as passes not only reduce evasion, but are quicker and easier to scan during an inspection.
- They scale well with #strong[pre-tax commuter benefits], administered by organizations like TransitChek, Edenred, and JAWNT. These provide a specific pre-tax amount up to an IRS-defined limit. A consistently priced monthly pass allows easy configuration of that amount, whereas a cap leads to varied costs every month.
- Historically, prepaid monthly passes have worked to reduce #strong[transaction costs], including curtailing the number of ticket-vending machines needed at stations. With modern payment by contactless card and app, this effect is reduced, but there is still less friction when the user buys one monthly than when they buy individual tickets. Many riders also prefer the simplicity of a single charge on their bank statement instead of dozens.

As a result of all of this, the general policy of international transit operators has been to encourage as many riders to use transit passes as possible. #strong[More people utilizing passes means more riders and lower costs.]

== The Problem: the MTA’s Pricey Pass Ratio

Even with all of those benefits, however, the MTA’s previous unlimited-ride pass had a major problem: #strong[it was far too expensive].
This was already true before the pandemic, and has only been exacerbated by the pandemic rise of hybrid and remote work.

When discussing unlimited travel passes, the most informative number to consider is usually the pass ratio: the number of trips it takes for a traveller to break even.
Prior to the discontinuation of MetroCard, the MTA’s monthly pass cost the equivalent of #strong[46 rides, one of the highest ratios in the world].
To put that number in perspective, there are on average only 21 or 22 workdays in any given month.
That means that a full-time worker commuting to and from their job every day would have only taken a maximum of 44 rides, not breaking even on an unlimited-ride MetroCard.
Things are even worse under the current weekly fare capping scheme: at \$35 per week, the equivalent of an unlimited pass now breaks even at #strong[50 rides per month, the highest ratio in the world].

#figure(
  link("https://kkysen.github.io/eta-publish/reports/monthly-passes/images/img-6b5eb7d1.png")[#capped_image("print/img-6b5eb7d1.jpg", alt: "Worldwide Monthly Pass Ratios")],
  caption: [#emph[A comparison of monthly fare pass ratios. Note: for cities with multiple zones, only an inner zone pass is used.]],
)

Other cities across both the country and the globe have taken a very different approach: they keep the cost of their monthly pass comparatively low in order to encourage as many riders as possible to use them.
In ETA’s data, the average breakeven point is 29, usually higher in English-speaking countries and Japan, and lower in Continental Europe.
In Tokyo, for example, the breakeven point for monthly passes is a high 38; in Paris, which offers one of the least generous monthly discounts in Europe, it’s 36; and in the entirety of Germany, the Deutschlandticket is available for €63 a month, leading to a ratio of about 16 in Berlin.
Domestically, both Chicago and San Francisco’s monthly passes are priced at 30 rides to break even. #strong[New York’s current pass ratio for monthly riders is fully two-thirds higher than the global average].

In Europe, low monthly pass ratios are part of an overall strategy to not only boost ridership in general, but to incentivize off-peak trips in particular.
This is because #strong[off-peak rides are far cheaper to provide than peak-hour rides].#footnote[Brian D. Taylor, Mark Garrett, and Hiroyuki Iseki, “Measuring Cost Variability in Provision of Transit Service,” #emph[Transportation Research Record] (2000, 1745(1), 101-112). https://doi.org/10.3141/1735-13 Professor Taylor also explains this phenomenon in #link("https://youtu.be/OVq1SRBy3aY?si=JyTyJlIe4zqtKe60")[this presentation for the Transit Costs Project]#super[#link(<src11>)[\[11\]]].]
Transit systems must be designed to provide enough capacity during peak hours, creating a large reserve of buses, trains, and staff that are only needed for a few hours a day and are underutilized the rest of the time.
What’s more, maintenance costs scale with peak service and not off-peak service, and crew scheduling is easier when the peak-to-base ratio of frequency is lower.#footnote[See computations in our report, Modernizing New York Commuter Rail, #link("https://www.etany.org/modernizing-new-york-commuter-rail")[https://www.etany.org/modernizing-new-york-commuter-rail]#super[#link(<src12>)[\[12\]]], footnotes 73–77.
Subway rolling stock lasts regardless of how intensively it is run, and the commuter rail crew schedules in Berlin, where there is limited difference between peak and off-peak frequency, get 12% more hours out of every train driver than Metro-North, which has to pay extra for split shifts, and 50% more than the LIRR, which does not.
Those computations are equally valid for subway and commuter rail service.]
The same effect can be seen in other modes of travel, which often adopt peak pricing to mitigate these extra costs, such as high airline and intercity rail fares at busy times, congestion pricing and tolls that vary by time of day, surge pricing on app-hailed vehicle rides, and parking rates that rise during peak hours.
Rather than ration service through peak fares, unlimited passes allow a system to better use peak resources by running more of them during the day and stimulating off-peak travel by making it effectively free for regular riders.
ETA has #link("https://www.etany.org/statements/six-minute-service")[previously argued that the MTA can and should run better off-peak service]#super[#link(<src1>)[\[1\]]] for this reason: filling empty cars is essentially free, and running more service off-peak is far cheaper than adding service during rush hour.

In other words, #strong[transit passes create all of the social, economic, and environmental benefits of increased transit ridership while lowering the per-rider operating cost].
This is especially important post-pandemic, as ridership during off-peak and weekend hours has grown far faster than peak travel.
The transit agencies around the world that have recovered best from COVID have leaned into this fact, providing more service off-peak and on weekends while working to encourage more people to ride for reasons other than commuting.
Reasonably priced transit passes have played a major role in enabling this growth.

== Choosing a Ratio for the Hybrid Work Era

The MTA has argued that relying on weekly fare caps makes sense in a post-pandemic world, where #link("https://www.mta.info/press-release/transcript-mta-chair-and-ceo-lieber-appears-brian-lehrer-show-0")[remote and hybrid work means fewer people commuting every day]#super[#link(<src2>)[\[2\]]], many of whom #link("https://www.mta.info/press-release/mta-pilot-major-changes-fare-structures-new-york-city-transit-lirr-and-metro-north")[may not know in advance if they will be traveling enough]#super[#link(<src3>)[\[3\]]] to make a monthly pass worthwhile.

However, the logic of the MTA’s solution is precisely backwards.
If a pass is so expensive that regular riders are unsure if they will break even, that means the pass itself is too expensive. 

The pandemic was a global event, and the rise of hybrid work has not been a uniquely American phenomenon by any means.
For years after the pandemic, Parisian ridership patterns had reduced ridership on Mondays and Fridays while the other three weekdays bounced back to pre-pandemic ridership.
And yet, these systems have adjusted their fare policy so that the vast majority of local riders will hit the pass ratio.
Having a pass encourages riders to develop what in old transit research was called the ridership habit: taking transit becomes the default option for any trip.
If riders only seldom hit the pass ratio, however, then it is far more difficult to develop the habit of using transit for off-peak, non-essential trips.

If the rise of hybrid work meant fewer people were hitting the fare cap, that was not a reason to give up on passes altogether and retreat to fare capping, but rather an indication that it was time to lower the ratio for passes so they remain competitive.
The pandemic should have been a wake-up call for the MTA that their pass ratio, which was already too high, was now becoming truly untenable.

Lowering the pass ratio would require some combination of raising the single ride fare and increasing the short-term subsidy to MTA operations.
The funds required, however, would probably not be as high as might be expected, because of the savings that passes offer: regular revenue, increased off-peak travel, easier fare inspections, and less fare evasion.
Without a more detailed study on ridership elasticities by travel purpose, we can’t give an exact recommendation for how much of each is required.
Systems with very large monthly discounts, with ratios below 20, have either low farebox recovery ratios or single-ride fares in excess of \$5, but systems with ratios in the high 20s or so do not.
As such, the MTA should move its pass ratio to be in line with practices of around 30.

Affordable passes lower the cost to provide service while increasing ridership.
Most importantly, however, #strong[increasing the number of New Yorkers with transit passes creates the most valuable outcome of all: more people using transit for more of their trips].

== OMNY’s Fare Cap in Practice: Left in the Dark

In theory, fare capping realizes many of the same benefits as unlimited passes.
For example, passengers who have hit the cap already, and even some who know they will definitely hit it, will in principle behave in the same way as passengers who have prepaid passes.
But the technical limitations of OMNY make it difficult for users to appreciate those benefits in practice.

For one, as currently designed, the system is unable to alert riders and inform them they have hit the fare cap when they tap in.
Indeed, pay-per-ride OMNY users cannot even see their current balance without either signing up online or going to a fare machine, while Metrocard users could swipe at balance checkers.
As a result, unless riders register their card online and check their status regularly, they have no way of knowing if they have earned a transit pass or not.
This negates many of the advantages of an unlimited ride pass, namely, the care-free ability to use transit at any time.

Making matters worse, OMNY’s weekly fare capping is not nearly as intuitive or cost-saving as it has been marketed to be, because of the way it tallies rides.
OMNY doesn’t use a moving window that examines your past seven days of rides every time you tap.
Instead, the system uses a fixed seven-day window that starts from the first time your card is used after the end of a previous window.
For example, imagine you return to New York after a trip.
You tap in on a Thursday, and then don’t ride again until the next Tuesday, and then proceed to ride twice a day that entire week.
You might reasonably assume you will hit the fare cap—after all, you will have taken more than 12 rides in seven days—but in reality, because your cap window is now from Thursday-to-Thursday, not Tuesday-to-Tuesday you will wind up paying for each ride.
If you take additional rides beyond commuting starting the Monday you return, you could in fact pay for as many as 23 rides#footnote[Example: One ride to trigger the period, 11 more in the last three days of the first period, 12 more in the first four days of the last period.
The maximum is one short of 24 because at least one ride outside the first part of the rolling 7 days is needed to trigger the non-rolling window that splits the rolling window.] that week before you hit the cap—almost double the “12 rides in seven days” expectation.
This is precisely the type of planning complexity that unlimited passes are designed to eliminate.

Recently, there have been multiple reports that bus proof-of-payment has been severely hampered by fare inspectors being unable for technical reasons to verify when riders have met the cap just by tapping their payment mechanisms to a verification device.
This has led to MTA staff asking riders to display bank account information, which not only is an unacceptable violation of privacy, but has also resulted in #link("https://hellgatenyc.com/the-mtas-farebeating-crackdown-on-buses-is-a-mess/")[tickets being issued to fare-paying straphangers]#super[#link(<src4>)[\[4\]]]. 

These fare issues are technical problems that should have been ironed-out years ago, and need to be fixed as soon as possible.
At the same time, they illustrate that the additional complexity of fare capping is not free.
Prepaid monthly passes by their nature can only be implemented in a way that avoids these technical issues altogether.
This simplicity is not just good for passengers: it’s also good for agencies with limited resources.
There was no need to transition away from tried-and-true monthly passes at the same time the MTA was switching to digital payments.

Fare capping already requires riders to weigh the marginal cost of a transit trip before hitting the cap.
But with OMNY, riders often have a hard time knowing if they have hit the cap in the first place.
The easiest to understand fare system, of course, is a pass bought upfront.

== The Unique Circumstances that Created Fare Capping

Fare capping was invented in London after the introduction of the Oyster fare card in 2003.
This new smartcard had the capability to automatically compute whether, for the card’s history, it would have been more advantageous to pay per ride or buy a day pass.
Once the passenger reached enough trips in one day for the pass to have been worth it, the system retroactively decided that the passenger must have bought a day pass, and stopped charging for further trips.
Essentially all fare capping since has been based on generalizing this system—one based on a complicated fare system and nearly thirty year-old technical limitations.

London is hardly the first city in the world to have introduced a smartcard for its subway system.
But it was the first to implement a fare cap, however, because of a unique combination of fare complexity and technical limitations:

- It has day, weekly, and monthly passes and expects regular riders to use them; some Asian early adopter cities of smart cards, like Singapore, have no passes at all.#footnote[Singapore technically does have a monthly pass, but it’s not designed to be used by the mass public and is on a different system from the point-to-point distance-based fares that everyone uses.] At the same time, the London monthly pass multiplier is high, and therefore the norm in most of Continental Europe that every rider should get a monthly pass doesn’t hold.
- It has a complex multi-zone system, with nine zones for the London Underground, a separate fare system for buses, and a commuter rail network that is mostly but not completely fare integrated with the Underground. Importantly, this complex fare system means that much of what might be considered a central-city ride in other cities actually crosses multiple zones. As a result, a rider who travels more than just a single round-trip commuter per day is likely to wind up travelling across multiple, changing combinations of zones as they travel to different destinations across the city. In contrast, Continental European cities’ zone systems are for the suburbs, whereas the entire city is usually in a single zone, as in New York.
- Oyster’s trip history could remember, for each card, enough past transactions to be able to implement a daily or weekly cap, but not a monthly cap. This technological limit, by now over 20 years no longer relevant, has been reified to the point that people expecting London-style fare capping still only implement a daily and weekly but not monthly cap.

In the United States, reform-oriented organizations such as #link("https://transitcenter.org/capping-the-way-to-fairer-fares/")[TransitCenter]#super[#link(<src5>)[\[5\]]] have seen the Oyster fare cap in action in London and #link("https://transitcenter.org/monthly-fare-capping-is-the-ticket-to-fare-equity/")[advocated to import it]#super[#link(<src6>)[\[6\]]] to the United States.
The technical context of London and the Oyster card is not applicable to any US metro system with a flat fare.
Instead, the organizations have made equity-based arguments, saying that prepaid monthly fares are difficult for poor riders, who may not have the money for a monthly pass upfront.

A better solution for low-income riders is the Fair Fares program, which offers reduced-cost travel to travelers below a certain income threshold.
Both #link("https://www.ridersalliance.org/news/its-time-to-expand-fair-fares")[Riders Alliance]#super[#link(<src7>)[\[7\]]] and #link("https://pcac.org/report/fairfares25/")[PCAC]#super[#link(<src8>)[\[8\]]] have proposed expanding the program’s eligibility from a maximum income of 1.5 times the federal poverty line to 2 times to a larger income range, a more direct solution for equity concerns.
Indeed, many of the European cities with low monthly fare ratios have reduced-fare products for children, students, retirees, and people qualifying for means-tested benefits.
To reduce administrative barriers, some systems have piggybacked on Medicaid eligibility for access to means-tested fares, for example Indego, Philadelphia’s bike share system.

== Bring Back Passes

Ending the sale of monthly subway and bus passes with the end of MetroCard was a step in the wrong direction.
Passes are a steady, guaranteed revenue stream, and ensuring that a high percentage of riders use passes not only works to reduce fare evasion, but makes service-improving policies like all-door bus boarding possible.
Eliminating the pass pushed New York further away from global best practices.

That said, even before it was eliminated, New York’s monthly pass was already the most expensive in the world by break even ratio, far above the international average.
Simply adding a monthly pass or a monthly fare cap to OMNY is not enough if it is priced at the same 46-ride breakeven point as before.
As cities around the world demonstrate, getting passes into the hands of riders is one of the best ways there is to boost ridership—especially low-cost off-peak and weekend ridership.
After all, the easiest transit trip to make is the one that you don't have to think about.

= Sources

#[
#set par(justify: false)
#set text(hyphenate: false)
+ (archived #link("https://web.archive.org/web/20260203205100/https://www.etany.org/statements/six-minute-service")[Feb 3, 2026]) #link("https://www.etany.org/statements/six-minute-service")[etany.org/statements/six-minute-service] <src1>
+ (archived #link("https://web.archive.org/web/20260519002325/https://www.mta.info/press-release/transcript-mta-chair-and-ceo-lieber-appears-brian-lehrer-show-0")[May 19, 2026]) #link("https://www.mta.info/press-release/transcript-mta-chair-and-ceo-lieber-appears-brian-lehrer-show-0")[mta.info/press-release/transcript-mta-chair-and-ceo-lieber-appears-brian-lehrer-show-0] <src2>
+ (archived #link("https://web.archive.org/web/20260521040021/https://www.mta.info/press-release/mta-pilot-major-changes-fare-structures-new-york-city-transit-lirr-and-metro-north")[May 21, 2026]) #link("https://www.mta.info/press-release/mta-pilot-major-changes-fare-structures-new-york-city-transit-lirr-and-metro-north")[mta.info/press-release/mta-pilot-major-changes-fare-structures-new-york-city-transit-lirr-and-metro-north] <src3>
+ (archived #link("https://web.archive.org/web/20260410095829/https://hellgatenyc.com/the-mtas-farebeating-crackdown-on-buses-is-a-mess/")[Apr 10, 2026]) #link("https://hellgatenyc.com/the-mtas-farebeating-crackdown-on-buses-is-a-mess/")[hellgatenyc.com/the-mtas-farebeating-crackdown-on-buses-is-a-mess/] <src4>
+ (archived #link("https://web.archive.org/web/20260607172552/https://transitcenter.org/capping-the-way-to-fairer-fares/")[Jun 7, 2026]) #link("https://transitcenter.org/capping-the-way-to-fairer-fares/")[transitcenter.org/capping-the-way-to-fairer-fares/] <src5>
+ (archived #link("https://web.archive.org/web/20260517114557/https://transitcenter.org/monthly-fare-capping-is-the-ticket-to-fare-equity/")[May 17, 2026]) #link("https://transitcenter.org/monthly-fare-capping-is-the-ticket-to-fare-equity/")[transitcenter.org/monthly-fare-capping-is-the-ticket-to-fare-equity/] <src6>
+ (archived #link("https://web.archive.org/web/20260316022857/https://www.ridersalliance.org/news/its-time-to-expand-fair-fares")[Mar 16, 2026]) #link("https://www.ridersalliance.org/news/its-time-to-expand-fair-fares")[ridersalliance.org/news/its-time-to-expand-fair-fares] <src7>
+ (archived #link("https://web.archive.org/web/20260517234603/https://pcac.org/report/fairfares25/")[May 17, 2026]) #link("https://pcac.org/report/fairfares25/")[pcac.org/report/fairfares25/] <src8>
+ (archived #link("https://web.archive.org/web/20260429163851/https://www.ironmanturnstile.com/transportation-and-smart-hubs/")[Apr 29, 2026]) #link("https://www.ironmanturnstile.com/transportation-and-smart-hubs/")[ironmanturnstile.com/transportation-and-smart-hubs/] <src9>
+ (archived #link("https://web.archive.org/web/20260214174558/https://www.cubic.com/news-events/blogs/why-enforcement-cant-be-the-only-solution-for-transit-revenue-protection")[Feb 14, 2026]) #link("https://www.cubic.com/news-events/blogs/why-enforcement-cant-be-the-only-solution-for-transit-revenue-protection")[cubic.com/news-events/blogs/why-enforcement-cant-be-the-only-solution-for-transit-revenue-protection] <src10>
+ (archived #link("https://web.archive.org/web/20261009033532/https://youtu.be/OVq1SRBy3aY?si=JyTyJlIe4zqtKe60")[Oct 9, 2026]) #link("https://youtu.be/OVq1SRBy3aY?si=JyTyJlIe4zqtKe60")[#box[youtu.be/OVq1SRBy3aY?]#box[si=]#box[JyTyJlIe4zqtKe60]] <src11>
+ (archived #link("https://web.archive.org/web/20260519113718/https://www.etany.org/modernizing-new-york-commuter-rail")[May 19, 2026]) #link("https://www.etany.org/modernizing-new-york-commuter-rail")[etany.org/modernizing-new-york-commuter-rail] <src12>
]
