#import "template.typ": capped_image, report

#show: report.with(
  title: "Too Damn Loud: Announcements on NYC Transit are Out of Control",
  headline: [Too Damn Loud: Announcements on NYC Transit are Out of Control],
  subtitle: none,
  phase: "",
  dateline: "September 9, 2026",
  contributors: ("Madison Feinberg", "Elijah Fischer", "Robert Hale", "Darius Jankauskas", "Tim Lazaroff", "Alon Levy", "Blair Lorenzo", "Khyber Sen", ),
  contributors_note: "We wish to acknowledge the following ETA members who contributed to this report, and without whose hard work it would not be possible:",
  warnings: (
    [the #raw("Header") section has an unrecognized #raw("Related Document:") line; check it for a typo],
    [the #raw("Short:") line is no longer used; if it is a blog post's excerpt, rename it #raw("Excerpt:"), and otherwise delete it],
    [the #raw("Header") section has an unrecognized #raw("Video:") line; check it for a typo],
    [2 images share one paragraph; only the first becomes a figure],
    [the image #raw("img-831248b1") has no caption],
    [the image #raw("img-831248b1") has no #raw("Credit:") line],
    [the image #raw("img-b17aa21a") has no #raw("Credit:") line],
    [2 images are unnamed, so each publishes under a hash; give each a #raw("Source:") line naming its file:#list([#raw("img-831248b1")], [#raw("img-b17aa21a"): PNG SVG], )],
    [24 suggestions still open on this tab; the build publishes the document without them, as it reads today],
    [2 comment threads still open on this tab],
    [3 links show their URL as their text; give each words in the doc:#list([#raw("https://www.sciencedirect.com/science/article/abs/pii/S0966692316302393")], [#raw("https://www.amny.com/news/mta-nyc-subway-ads-and-money/")], [#raw("https://sbahn.berlin/fahren/bauen-stoerung/")], )],
    [the #raw("Header") section has no #raw("SME/Liaison:") line],
    [the #raw("Header") section has no #raw("Goals:") line],
    [the #raw("Header") section has no #raw("Audience:") line],
    [the #raw("Header") section has no #raw("Social Title Card:") line],
    [#raw("SEO Description:") is 363 characters, over the 300 a search result shows:#quote(block: true)[The seemingly-endless onslaught of announcements on NY transit not only annoys riders, but impairs accessibility, making navigating transit far more difficult than it needs to be. ETA outlines the best practices for transit audio design: clear, concise messages reserved for actionable information. I#strike[t's time to stop the cacophony, and let riders travel in peace.]]],
    [style: an apostrophe should be #raw("’"), not #raw("'"): #raw("...for actionable information. It's time to stop the cacophony, ...")],
    [style: a sentence should end with 1 space, not 2: #raw("..., often one message at a time.··Slowly, by following the path ...")],
    [style: an apostrophe should be #raw("’"), not #raw("'"): #raw("...ual advertisements, riders can't simply choose to look away f...")],
    [style: an apostrophe should be #raw("’"), not #raw("'"): #raw("... be a positive part of a rider's day, not an annoyance.")],
    [style: a sentence should end with 1 space, not 2: #raw("...ersion of the curb cut effect.··In this case, designing announ...")],
    [style: an apostrophe should be #raw("’"), not #raw("'"): #raw("...o understand for those who don't speak English as a first lan...")],
    [style: an apostrophe should be #raw("’"), not #raw("'"): #raw("...become intolerable. The region's transit agencies, and the MT...")],
    [style: an apostrophe should be #raw("’"), not #raw("'"): #raw("... New York is too damn loud. It's time to let riders travel in...")],
    [the image #raw("img-831248b1") has no alt text and no caption; add a description to it in the doc],
  ),
)

#link("https://youtube.com/shorts/o90JQBWdgTI?is=I4sZ3txy37d2RiGU")[Video: Too Damn Loud: Announcements on NYC Transit are Out of Control (Effective Transit Alliance on YouTube)]#super[#link(<src1>)[\[1\]]]

#figure(
  link("https://kkysen.github.io/eta-publish/briefs/too-damn-loud/images/img-831248b1.jpg")[#capped_image("print/img-831248b1.jpg")],
)

= Too Damn Loud

Transit in and around New York is just too damn loud.

Some of this is unavoidable.
Providing transit can be a noisy endeavor, and things like the squeal of a train around a tight curve or the roar of a diesel engine can be difficult to eliminate.

But far too much of the noise that bombards New Yorkers’ ears, is not the product of a loud environment, but rather a deliberate assault on riders’ attention.
Whether waiting on a platform or traveling on a bus or on the subway, transit riders rarely get more than a few moments of peace before being inundated in a stream of unnecessary, verbose announcements.

From incessant “Important reminder\[s\] from the NYPD” about theft, to repeated “It is against New York State law to smoke on platforms and waiting areas” on commuter trains to endless repetitions of “New York has more than 100 accessible stations,” riders’ ears are constantly assailed with messages that have little or no bearing on their travels.
The MTA has even #link("https://nypost.com/2026/02/25/us-news/mta-to-blast-75-decibel-ads-in-subways-as-critics-blast-fahrenheit-451-style-spin/")[begun to experiment with advertisements]#super[#link(<src2>)[\[2\]]] played to a captive audience over its PA systems.
This cacophony has reached the point that it is noticeably degrading the riding experience, for no gain at all. 

Indeed, ETA recorded a one-way ride from 34 St-Hudson Yards to Flushing-Main St, and nearly 10 minutes out of a 40 minute ride comprised announcements.
Riders should not be subjected to constant sound for 25% of their ride.
On the Berlin S-Bahn, a complex branched system that must announce train numbers and destinations, the announcements—all short snippets of information about the train’s identity and destination or the door closing warning—are 15 seconds per interstation segment, only about 12.5% of the ride, half as long as on New York City Transit.

#figure(
  link("https://kkysen.github.io/eta-publish/briefs/too-damn-loud/images/img-b17aa21a.png")[#capped_image("print/img-b17aa21a.jpg", alt: "PNG SVG")],
  caption: [#link("https://drive.google.com/file/d/1ceFr--thicXMKXMuKG87Rhxs7oY2xWgC/view?usp=drive_link")[PNG]#super[#link(<src3>)[\[3\]]] #link("https://drive.google.com/file/d/18pQbx_DJ_n_OHNDaQlfHOvRSZqJPd88V/view?usp=drive_link")[SVG]#super[#link(<src4>)[\[4\]]]],
)

Hands over ears icon created by Gan Khoon Lay from the Noun Project, used with permission.

This misuse of public address systems is particularly frustrating because announcements, when done correctly, are a key part of any transit system.
Announcements are critical for increasing riders’ situational awareness, ensuring that they always know where they are, where they are going, what’s going on around them, and what to do if service is disrupted.
Audio announcements are especially vital for visually impaired riders, who rely on their presence and their clarity to navigate the transit system with minimal visual input. 

This noise pollution has proliferated gradually, often one message at a time.  Slowly, by following the path of least resistance, best practices were eroded.
What began as relatively clear announcements designed around riders' needs has slowly accreted more and more unnecessary pieces.
One manager may have wanted to push a safety campaign.
Another may have seen an opportunity for ad revenue.
Another organization, for instance, the NYPD, asks to have safety announcements.
Each ask is minor—after all, who would complain about just one more brief message?
However, over time, announcements have snowballed, burying riders in a sea of noise.

Restoring clarity and concision in announcements is not difficult.
Less important communication like public service announcements should be moved to posters and digital information boards, and even necessary announcements can be shortened.
It is time for the region to create a travel environment that is not only more accessible, but respects the public’s wish to ride in peace.

= The Proper Role of Announcements

Transit announcements are a balancing act.
On the one hand, they must convey the vital information that riders need.
On the other hand, if they are too frequent or too verbose, they can bring a host of negative consequences:

- Incessant announcements cause riders to tune out as much as possible. This means they are primed to miss critical information during service changes or emergencies.
- They make it much more difficult for non-English speakers to pick out key destinations and phrases.
- They increase the cognitive load on riders with vision impairment who are relying on audio cues to navigate.
- Constant noise simply makes transit a louder and more unpleasant place for riders to be.

Announcement design must keep in mind that passengers can’t just choose what to listen to the way they can choose where to cast their eyes.
The best they can do is try to tune out the entire environment, which means if there is too much noise, they will not listen even for important things.

This is made worse by the fact that transit stations and vehicles are already loud places, so that understanding announcements can often be difficult even in the best of times.
The automatic announcements used on most modern MTA trains and buses have improved clarity, but the fundamental problem of distractions remains.
Announcements that are either verbose or, worse, irrelevant only make the situation harder.
This is especially difficult for passengers who don’t speak fluent English, as they need to be listening carefully to extract information, which is far more difficult to do with too much auditory distraction.

A similar problem exists in a very different context for industries that use radio communication, such as air traffic control, emergency services, and even transit dispatching.
Analog radios are often noisy and low fidelity, not unlike announcements in a noisy transit environment, making communication difficult.
As clear understanding can often be a matter of life or death in these industries, they have developed systems to ensure messages are understood: radio discipline.
The key is that listeners know what to expect: communication sticks to simple, key phrases and unnecessary chatter is kept to a minimum.

The MTA and other transit operators can take a page from radio discipline and reconcile all these issues by emphasizing focus and concision.
Clear and concentrated announcements serve all riders best: they are simpler for non-English speakers to understand, create a less cluttered aural environment for visually-impaired travelers, and are less likely to grate on regular riders and be tuned out.

To that end, audio messages should focus on a small set of topics:

- The current and next stop
- Available connections
- Service changes
- Real-time updates on unexpected delays
- Elevator location, on vehicles that cannot display such information on screens

Greater New York’s transit network is already one of the most complicated in the world; its announcements should do everything they can to simplify the experience of navigating it.

= Constructing Better Announcements

=== Basic Principles

For the same reason that announcements should only include the most critical information, they should also be made with the minimum number of words necessary.
Short, simple messages allow non-fluent English speakers to pick out vital words more easily.
The same holds true for the visually impaired: shorter messages mean less time and less mental energy expended on parsing information.
Finally, short announcements minimize annoyance for frequent transit riders, who will hear them dozens of times daily.

This is why in the 1960s #link("https://www.ltmuseum.co.uk/blog/mind-gap-story-embankment-stations-announcement")[London Transport spent so long developing the now-iconic phrase “Mind the Gap”]#super[#link(<src5>)[\[5\]]]: it was short, clear, and to the point.
Similarly, in Berlin, the phrase “Zurückbleiben bitte”—“please stay back”—is very short and understandable even by people with middling German.
In contrast, New York’s “Stand clear of the closing doors please” sentence, while iconic to many, is so long that conductors often interrupt it to close the doors faster.
It’s even longer than Ottawa’s bilingual announcements.
Bernie Wagenblast’s announcements have become iconic in New York, and it would be ideal for the MTA to bring her back to record new, shorter versions of her original work.

\[audio files of NYC, Berlin, and Ottawa door closings\]

The audio announcements on today’s subway trains are far too verbose.
Compare the normal announcements used on these trains with the #link("https://www.youtube.com/watch?v=KDaRRmUWUZI")[shortened versions]#super[#link(<src6>)[\[6\]]] that the MTA created around 2015 but never put into service.

Beyond verbosity, automated announcements should also be designed to communicate common reroutes and changes.
This is especially true in New York, where the complicated subway system enables many potential reroutes.
Right now, conductors must manually announce changes, often leading to garbled, unclear messages that confuse riders.
While some more intensive maintenance regimes might call for reroutes that are difficult to communicate, systems should be designed to inform riders of common changes, like trains running local or express unexpectedly.

The announcements on both Metro-North and the Long Island Rail Road’s recent rolling stock are even worse, both in length and design.
This is especially true of the announcements made at terminals before trains depart, where the system must inform riders of complex stopping patterns that often change.
Conductors often feel the need to provide their own supplementary descriptions, a clear sign that the announcements need further attention and design.
Significant information, such as informing riders of short platforms, must be made manually by conductors.

Of course, transit systems obviously need and want to communicate things other than destinations, connections, and immediate service disruptions.
Thankfully, LCD screens across the region’s transit network and increasingly on trains give operators the perfect place to present such information.
Using screens for PSAs, announcements about future service changes, and other less-critical pieces of information would keep the transit soundscape free of clutter.

Once transit operators have established a system of high-quality, clear, concise announcements, it is then important they remain consistent.
There will always be pressure to add just one more announcement, be it for a new PSA, or from an outside agency, or a message from a politician.
Allowing one could quickly open the floodgates, recreating the loud, chaotic audio situation greater New York faces today.
Transit operators should make clear guidelines akin to those presented here, and stick to them as much as possible.
Ensuring accessible and pleasant trips for all users means constantly being on guard against erosion of announcement principles.
Audio announcements should remain solely the domain of important, actionable information.

#strong[Accessibility]

Audio announcements are a vital tool for creating transit systems that are accessible and usable for all.
Indeed, public address systems are required on transit vehicles by the Americans With Disabilities Act.#footnote[#link("https://chanrobles.com/usa/uslaws/cfr/title36/36-3.0.9.1.7.2.1.8.php")[36 CFR 1192.35]#super[#link(<src8>)[\[8\]]] #link("https://www.ecfr.gov/current/title-49/subtitle-A/part-37/subpart-G/section-37.167")[49 CFR 37.167(b) & (c)]#super[#link(<src9>)[\[9\]]]] The ADA is neutral about whether the announcements are automated, but in practice, automated announcements are enunciated more clearly for riders and with more neutral accent and diction.

Proper design is critical for announcements to serve as an effective accessibility aid.
The key is to keep the needs of various different groups in mind when designing announcements.
Thankfully, the needs of most disabled riders line up with the general principles presented above: announcements should be clear, concise, and limited to the most important information about travel.

#emph[The blind and vision-impaired]

Traditionally, it has been difficult for those with significant vision impairments to navigate transit systems without outside aid.
Most transit systems have been designed for people to navigate primarily by sight, using either signs or landmarks.
The advent of audio announcements—and especially of pre-recorded announcements—has significantly improved the situation for travelers with impaired vision.
Announcement design, however, is required to maximize the benefit to these riders.

A subway system is a loud and complex place.
Keeping audio announcements clear and concise helps declutter the auditory environment.
Unnecessary announcements like PSAs, general safety or rules information, and advertisements force blind and vision-impaired riders to pay attention to a near-endless list of comparatively unimportant information to pick out the vital information that they need to navigate.
It also takes a fair amount of concentration to separate announcements from loud background noises such as moving trains and large crowds of people.
Similar to how radio discipline makes noisy communications understandable, a clear, concise system of announcements with a minimum of unnecessary noise reduces the amount of information that blind and vision-impaired riders need to process.

#emph[Riders who don’t speak English as a first language]

It is a similar story for passengers who do not speak English as their first language, and especially those who don’t speak it fluently.
New York is a world city of the highest order, welcoming untold numbers of visitors and immigrants from around the world, speaking every language on the planet.
As such, the needs of non-native and non-fluent English speakers needs to be taken into account in any system of announcements.

Unfortunately, the subway’s current user interface is not at all legible to passengers who speak poor English, especially if they only speak languages that don’t use the Latin alphabet, like Mandarin.
They can’t parse the verbal announcements and often can’t even read the station names; an ethnography found that one Chinese rider navigated by the first letters of the station names on the Flushing Line.#footnote[Yu, Shaolu, 2016. "’I am like a deaf, dumb and blind person’: Mobility and immobility of Chinese (im)migrants in Flushing, Queens, New York City,” #emph[Journal of Transport Geography], 54(C) (June 2016): 10–21. #link("https://www.sciencedirect.com/science/article/abs/pii/S0966692316302393")[https://www.sciencedirect.com/science/article/abs/pii/S0966692316302393]#super[#link(<src10>)[\[10\]]]] In countries used to either illiteracy or tourism by people who can’t read the alphabet, such as Japan or China, stations are numbered sequentially within each line.

#strong[Things that should be Avoided or Minimized]

#emph[Advertisements]

In a disturbing precedent, the MTA recently experimented with playing commercial advertisements over subway station PA systems.
For all the reasons listed above, this is an inappropriate use of passenger information systems.
Unlike normal visual advertisements, riders can't simply choose to look away from the sound surrounding them.
Commercials further incentivize passengers to tune out as much as possible, make life harder for the visually impaired, who have no choice but to listen for critical information, and make the system harder to navigate for those who do not speak fluent English.

More fundamentally, while these advertisements have brought in a modicum of revenue,#footnote[Barbara Russo-Lennon, “Subway spots: MTA’s ad blitz delivers big bucks for NYC’s transit system and reliability for riders,” #emph[AMNY], July 3, 2025, #link("https://www.amny.com/news/mta-nyc-subway-ads-and-money/")[https://www.amny.com/news/mta-nyc-subway-ads-and-money/]#super[#link(<src11>)[\[11\]]]] they have arguably cost the system more in riders and long-term reputation.
They cheapen transit, treating riders not as the customers or as citizens, but as the product.
It screams that the MTA doesn’t care about the experience of its riders.
In the long run, such maneuvers could well push riders away from transit towards other modes of travel that respect their time and attention.

Announcements exist to inform passengers, not to take advantage of them.

#emph[Hiring Announcements]

Hiring announcements have recently become common on the MTA.
Staff who spoke to ETA not for attribution indicated that it generated a raft of consumer complaints.
These announcements are essentially a hiring advertisement for the MTA itself, and should be treated as such.
Riders should not be subjected to such messages simply in order to ride transit.

#emph[Public Service Announcements]

New York straphangers have been subjected to more and more dubiously effective public service announcements (PSAs).
These began with the now ubiquitous important messages from the NYPD, and have in recent years have expanded to include things like continual announcements about the dangers of subway surfing.

Just as with advertising, these PSAs assume that passengers are simply blank slates with no interest in reading, talking to traveling companions, or simply riding in peace.
They affect usability, and make transit simply a far less pleasant place than it ought to be.
Constant NYPD reminders about pickpockets reinforce false stereotypes about the dangers of transit that have no basis in reality.
Such announcements only hurt the perception of transit over the long term.
A private automobile never forces its driver to listen to such messages, or even messages about the risk of car crashes.

If PSAs are to be a part of the subway experience, they should be limited to the digital screens, as with all other non-essentially pieces of travel information.
Indeed, the MTA already has a successful history of both print and digital PSAs about such courtesy norms as using headphones, taking one’s bag off, not taking up multiple seats, and not blocking doors.

#emph[Long-Term Work]

One of the key things that audio announcements may be appropriate for is to communicate reroutes and/or delays caused by temporary work.
When work is scheduled to take around two weeks or more, however, it can generally be assumed that riders are aware of service changes.
Indeed, Berlin, which sometimes shuts down segments of the subway for long-term renewal work and regularly shuts down commuter rail segments on weekends, announces those changes purely visually and on maps.#footnote[#emph[S-Bahn Berlin], “Störungen und Bauarbeiten,” accessed August 24, 2026, #link("https://sbahn.berlin/fahren/bauen-stoerung/")[https://sbahn.berlin/fahren/bauen-stoerung/]#super[#link(<src12>)[\[12\]]].]

It is good practice to announce major changes for the week before they happen and then the first week they occur.
After that point, LCD screens and other information systems are a far better way to keep riders informed than the constant repetition of announcements.
For example, riders do not need constant audio announcements about elevator replacements scheduled to take months or more.#footnote[Elevator replacements should not take months, but that is another piece.]

#strong[In Short, Respect Riders]

Announcement design is a balancing act.
Getting it right will require an ongoing process of trial, evolution, and improvement.
However, the current state of announcements is very far from any reasonable optimum.
The constant barrage of PSAs and lengthy messages about the system disrespects the riders’ attention.
Transit should strive to be a positive part of a rider's day, not an annoyance.

Announcements that treat riders with respect are almost a reverse version of the #link("https://en.wikipedia.org/wiki/Curb_cut_effect")[curb cut effect]#super[#link(<src7>)[\[7\]]].  In this case, designing announcements that do not grate and do not waste straphangers’ time also winds up creating announcements that are less taxing for the visually impaired and easier to understand for those who don't speak English as a first language.

There is much more about announcements beyond the scope of this piece.
This includes equipment design, ensuring that ongoing improvement is easy to implement, operator training, both on automated equipment and on improved techniques for manual announcements, and on the design of the passenger experience, in general.
Solving these problems will take time and effort.
Regardless, the situation in New York has become intolerable.
The region's transit agencies, and the MTA in particular, can no longer assume it is okay to fill every quiet second with unimportant noise.
It hurts usability, and it damages the reputation of transit in general.

Transit in New York is too damn loud.
It's time to let riders travel in peace.

= Sources

#[
#set par(justify: false)
#set text(hyphenate: false)
+ (archived #link("https://web.archive.org/web/20261009211344/https://youtube.com/shorts/o90JQBWdgTI?is=I4sZ3txy37d2RiGU")[Oct 9, 2026]) #link("https://youtube.com/shorts/o90JQBWdgTI?is=I4sZ3txy37d2RiGU")[#box[youtube.com/shorts/o90JQBWdgTI?]#box[is=]#box[I4sZ3txy37d2RiGU]] <src1>
+ (archived #link("https://web.archive.org/web/20260410141149/https://nypost.com/2026/02/25/us-news/mta-to-blast-75-decibel-ads-in-subways-as-critics-blast-fahrenheit-451-style-spin/")[Apr 10, 2026]) #link("https://nypost.com/2026/02/25/us-news/mta-to-blast-75-decibel-ads-in-subways-as-critics-blast-fahrenheit-451-style-spin/")[nypost.com/2026/02/25/us-news/mta-to-blast-75-decibel-ads-in-subways-as-critics-blast-fahrenheit-451-style-spin/] <src2>
+ (archived #link("https://web.archive.org/web/20261009033511/https://drive.google.com/file/d/1ceFr--thicXMKXMuKG87Rhxs7oY2xWgC/view?usp=drive_link")[Oct 9, 2026]) #link("https://drive.google.com/file/d/1ceFr--thicXMKXMuKG87Rhxs7oY2xWgC/view?usp=drive_link")[#box[drive.google.com/file/d/1ceFr--thicXMKXMuKG87Rhxs7oY2xWgC/view?]#box[usp=]#box[drive\_link]] <src3>
+ (archived #link("https://web.archive.org/web/20261009034236/https://drive.google.com/file/d/18pQbx_DJ_n_OHNDaQlfHOvRSZqJPd88V/view?usp=drive_link")[Oct 9, 2026]) #link("https://drive.google.com/file/d/18pQbx_DJ_n_OHNDaQlfHOvRSZqJPd88V/view?usp=drive_link")[#box[drive.google.com/file/d/18pQbx\_DJ\_n\_OHNDaQlfHOvRSZqJPd88V/view?]#box[usp=]#box[drive\_link]] <src4>
+ (archived #link("https://web.archive.org/web/20240505072338/https://www.ltmuseum.co.uk/blog/mind-gap-story-embankment-stations-announcement")[May 5, 2024]) #link("https://www.ltmuseum.co.uk/blog/mind-gap-story-embankment-stations-announcement")[ltmuseum.co.uk/blog/mind-gap-story-embankment-stations-announcement] <src5>
+ (archived #link("https://web.archive.org/web/20240606135521/https://www.youtube.com/watch?v=KDaRRmUWUZI")[Jun 6, 2024]) #link("https://www.youtube.com/watch?v=KDaRRmUWUZI")[#box[youtube.com/watch?]#box[v=]#box[KDaRRmUWUZI]] <src6>
+ (archived #link("https://web.archive.org/web/20260911062544/https://en.wikipedia.org/wiki/Curb_cut_effect")[Sep 11, 2026]) #link("https://en.wikipedia.org/wiki/Curb_cut_effect")[en.wikipedia.org/wiki/Curb\_cut\_effect] <src7>
+ (archived #link("https://web.archive.org/web/20260920115631/https://chanrobles.com/usa/uslaws/cfr/title36/36-3.0.9.1.7.2.1.8.php")[Sep 20, 2026]) #link("https://chanrobles.com/usa/uslaws/cfr/title36/36-3.0.9.1.7.2.1.8.php")[chanrobles.com/usa/uslaws/cfr/title36/36-3.0.9.1.7.2.1.8.php] <src8>
+ (archived #link("https://web.archive.org/web/20260401154612/https://www.ecfr.gov/current/title-49/subtitle-A/part-37/subpart-G/section-37.167")[Apr 1, 2026]) #link("https://www.ecfr.gov/current/title-49/subtitle-A/part-37/subpart-G/section-37.167")[ecfr.gov/current/title-49/subtitle-A/part-37/subpart-G/section-37.167] <src9>
+ (archived #link("https://web.archive.org/web/20200729104447/https://www.sciencedirect.com/science/article/abs/pii/S0966692316302393")[Jul 29, 2020]) #link("https://www.sciencedirect.com/science/article/abs/pii/S0966692316302393")[sciencedirect.com/science/article/abs/pii/S0966692316302393] <src10>
+ (archived #link("https://web.archive.org/web/20260328223010/https://www.amny.com/news/mta-nyc-subway-ads-and-money/")[Mar 28, 2026]) #link("https://www.amny.com/news/mta-nyc-subway-ads-and-money/")[amny.com/news/mta-nyc-subway-ads-and-money/] <src11>
+ (archived #link("https://web.archive.org/web/20260904171034/https://sbahn.berlin/fahren/bauen-stoerung/")[Sep 4, 2026]) #link("https://sbahn.berlin/fahren/bauen-stoerung/")[sbahn.berlin/fahren/bauen-stoerung/] <src12>
]
