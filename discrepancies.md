# Discrepancies

## What is being compared

Three things, not two.
For a publication whose header block names `URL: /reports/$publication`,
which is the one place its name is written:

1. `https://www.etany.org/reports/$publication`,
   the live page, as Squarespace serves it today.
   It is assembled by hand, one block at a time,
   162 of them for SAS West,
   so it is a record of what a person typed, not a reference.
2. `site/reports/$publication/doc.json`,
   the `documents.get` response for the tab named in that publication's
   `url` in `publications.toml`, committed next to the outputs it produced.
   This is the source: everything published comes from here.
3. `site/reports/$publication/index.html`,
   written from that `doc.json` by `uv run eta-publish`,
   or offline by `uv run eta-publish site/reports/$publication --no-images`.

Below, `doc.json` and `index.html` are those two files
for the publication the section is about, and *live* is that URL.

Naming all three is what makes an entry actionable,
because where a difference sits says who fixes it:

- Emitter. `doc.json` and `index.html` disagree.
  The document is right and the code is wrong. Fix the code.
- Document. `index.html` faithfully carries something
  missing or miswritten in `doc.json`.
  Live may look right, because someone fixed it by hand after publishing.
  Fix the document, and the fix reaches every output at once.
- Hand assembly. `doc.json` and `index.html` agree and live differs.
  Either the live page is defective,
  or the emitter deliberately publishes something else.
  Nothing to fix in this repository.
- Stale live. All three agreed when the publication went out,
  and `doc.json` has been edited since.

A publication is compared by normalizing live and `index.html`
to a tagged stream
(headings, paragraphs, list items, captions, alt text, cells),
diffing that in both directions,
then settling every hit against `doc.json`.
Anything the three agree on is not listed:
today that is every figure caption, every image credit,
and the text of every footnote body.

## All publications

These follow from what the emitters do,
so they apply to whatever publication is published next.

### The table of contents lists every heading, indented (intended)

Hand assembly.
Live runs six links together on one line separated by pipes,
so the eight subsections `doc.json` carries appear nowhere
and `Ground Conditions` is unreachable from the top of the page.
`index.html` lists all twenty-two headings as a nested list,
one per line, each indented under the section it belongs to.

`Footnotes` and `Contributors` are listed too,
though the emitter writes those two headings rather than the document.
They are sections of the page like any other,
and "at the end" is not an address in a publication this long.

### One `h1`, not a split title (intended)

Hand assembly.
`doc.json` holds one `TITLE` paragraph,
`Digging Out of a Very Deep Hole: Saving Billions on 125th Street`,
and `index.html` emits exactly that as a single `h1`.
Live splits it across an `h1` and an `h2`,
which leaves the subtitle looking like the first section heading.

### Everything on the page has an id (intended)

Hand assembly.
Live gives ids to headings and to the footnote anchors someone typed by hand,
and to nothing else,
so there is no way to link to a paragraph, a figure, or a table.
`index.html` gives one to the title, the standfirst, the table of contents,
the date, every heading, every paragraph, list, figure, and table,
each footnote, and the back matter sections themselves.

A paragraph is named by the section it is in and its place in that section:
`#ground-conditions-p2`.
That is a name a reader can read before following it,
and it survives the copy edits that are most of what happens to a publication,
which a hash of the text does not.
The cost is the other direction:
inserting a paragraph renumbers the ones after it in its own section,
and links to those land one paragraph early.
Numbering across the whole page would have spread that cost
to every paragraph below the insertion.
Figures and tables are still named by what they hold rather than where they sit.

### Section references are links (intended)

Hand assembly.
Google Docs cannot write a link to a heading in the same document,
so the publication italicizes the section's name and means a link by it.
Live publishes the italics as italics:
`See SAS Phase 2 Tail Tracks`, `as suggested in Station Depth`,
and the addendum's `Station Depth`,
each of them a name pointing nowhere.
One of the three was linked by hand, to `#phase2-tail-tracks`.

The parser reads the convention,
so all three resolve to the heading they name, in every output.
All four references the live page links resolve,
`Appendix A` among them, by the name a heading gives before its colon.
Live italicizes two other things, `and` and `tens of billions`,
and both stay italic here: they name no section.
The live page and the generated page shared this defect,
which is why comparing the two could not surface it.

### The back matter headings are `h2` (intended)

Hand assembly.
Every output credits the same nine people the live page credits,
in the same order, in a `Contributors` section after the footnotes,
under the sentence the live page introduces them with.
The names come from `Public Contributors:` in the header block,
sorted by surname, which is how `etany.org` credits contributors
and is not the order that field happens to be typed in.

What differs is the level.
`Footnotes` and `Contributors` are `h2` here and `h3` live,
making them sections of the publication rather than subsections of whatever came last.

### Footnote markers are bare superscripts after the punctuation (intended)

Hand assembly.
`index.html` puts each marker exactly where `doc.json` puts the `footnoteReference`,
which for reference 3 is after the period in `takes seven minutes.`,
and renders it as a plain superscript number.
Live renders `[3]` and places it before the period.

### Every source is listed and archived (intended)

New here.
Every external link carries a `[n]` into a `Sources` section
after the footnotes, where the entry names the page,
the capture of it in the Wayback Machine,
and a `↑` back to each place the publication cites it.
Live has no such section and no such markers:
a link there is a link, and when the page behind it moves, it is gone.

Four of SAS West's links are already `web.archive.org` URLs typed by hand,
and `index.html` shows those as the page they are of
with the capture beside it rather than as an address
that is itself an archive.

## SAS West

- <https://www.etany.org/reports/digging-out-deep-hole-sas-west>
- `site/reports/digging-out-deep-hole-sas-west/doc.json`
- `site/reports/digging-out-deep-hole-sas-west/index.html`

### The live footnotes are misnumbered from 13 onward (intended)

Hand assembly, and the clearest case of it.
`doc.json` holds 20 footnotes and 20 references,
and `index.html` emits 20 references, 20 bodies, and 20 backlinks, 1:1.
Live carries 21 markers and 21 `id="fnN"` anchors against 20 rendered bodies:
an extra marker sits on `...has space for more tracks than it needs`,
so every marker after it resolves one footnote too far.
Live `[14]`, on the steep-tracks sentence, lands on the soft-costs note,
and live `[21]` lands on nothing.
Live also carries the debris `README.md` describes,
an `id="#fn3-return"` and a duplicated `fn18-return`.

Nothing to do. This is the discrepancy the project exists to produce.

### The chart captions lost their `SVG` and `PNG` links (todo)

Document.
Live ends both chart captions with `[SVG] [PNG]` download links.
`doc.json` has bare `SVG: TODO` and `SVG:` placeholders where those links were,
so `index.html` has no links to emit and the `unfinished text` warning fires.
Put the links back in the document.

### The share card has no alt text (todo)

Document.
The wide image with the title set into it,
which the document puts above the headline,
publishes as `og:image` and nowhere else,
the same image live serves as `saswest.jpg`.
`og:image:alt` is written when the image has alt text, and this one has none,
so a link preview read aloud says nothing.
Describe it in the document.

### The images the document names no source for are named by hash (todo)

Emitter.
Where a figure has a `Source:` line, that file is the name:
`images/sas-west-217.jpg`, which is what the document calls it.
Seventeen of the 28 figures have no such line,
and those are still `images/img-8827f5de.jpg`, from the Docs object id.
Live serves `saswest.jpg`, named by a person.
Naming an image also names the figure's anchor,
so the eleven with a source line moved:
`#img-af4262b6` is now `#sas-west-tunnel-profile-pg-18-screenshot-af4262b6`.
The rest of the names belong in the document too, next to the image,
the way `Credit:` and `Source:` are,
and until they are there a hash is the only thing stable across edits.

### Four wordings the live page predates (intended)

Stale live.
`doc.json` has been edited since the publication went out,
and `index.html` carries the current text:
`10-story` for `10 story`,
`station box, while` for `station box while`,
`more cheaply` for `cheaper`,
and footnote 9's reference moved to a different sentence.
