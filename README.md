# `eta-publish`

Convert an [ETA](https://www.etany.org/) report Google Doc
into publish-ready HTML, Markdown, and PDF.

Reports are drafted in Google Docs and published on Squarespace.
That hand-off is entirely manual today,
and it is the source of both the tedium and the mistakes.

- [Why this exists](#why-this-exists)
- [What it does](#what-it-does)
- [Using it](#using-it):
  [setup](#setup), [building](#building), [adding a report](#adding-a-report),
  [publishing to GitHub Pages](#publishing-to-github-pages),
  [writing a report](#writing-a-report)
- [How it works](#how-it-works):
  [design decisions](#design-decisions), [source archiving](#source-archiving),
  [builds](#builds), [the Pages pipeline](#the-pages-pipeline),
  [Squarespace constraints](#squarespace-constraints), [rate limits](#rate-limits)
- [Development](#development)
- [Status](#status), [TODO](#todo), [possible directions](#possible-directions)

## Why this exists

The most recent report,
[*Digging Out of a Very Deep Hole*](https://www.etany.org/reports/digging-out-deep-hole-sas-west),
is built from **162 hand-placed Squarespace blocks**:
86 text blocks, 54 image blocks, and 22 code blocks.
Squarespace itself [recommends no more than 60 blocks per page](https://support.squarespace.com/hc/en-us/articles/206543087-Page-limits),
warning that pages beyond that load and save slowly.

Those 22 code blocks are not charts or embeds.
They are hand-written anchor targets, one per footnote,
that exist only so the `↑` backlinks work:

```html
<a id="fn7-return"></a>
```

Maintaining that by hand across 21 footnotes went about as well as expected.
The published page is missing the backlink for footnote 13 entirely,
and carries two pieces of leftover debris:
a stray `#` inside an `id` (`id="#fn3-return"`),
and a duplicated `fn18-return`.

None of this is anyone's fault.
It is what happens when a person is asked to be a compiler.
So we should use a compiler.

## What it does

Reads the Google Doc, builds a document tree, and emits from that tree:

| Output | Purpose |
| --- | --- |
| `report.html` | One fragment to paste into a single Squarespace code block, linking its images and videos on GitHub Pages (`--no-hosted-media` links them relative to itself) |
| `report.md` | Human-readable, diffable archive committed to git |
| `report.typ` / `report.pdf` | [Typst](https://typst.app/) source, and the compiled PDF |
| `index.html` | Standalone page for review, including any warnings |
| `images/` | The doc's inline images, for hosting outside Squarespace |
| `archives.json` | Where each source the report cites is archived |

Headings, anchors, the table of contents, footnote numbering,
the `Sources` section, and the `↑` backlinks are all generated.
They cannot drift out of sync, because nothing maintains them by hand.

# Using it

## Setup

[`mise`](https://mise.jdx.dev) is required, not optional:
it installs `uv`, `pre-commit`, and `biome` at the versions `mise.toml` pins,
and `biome` lays out every emitted page, so a build without it writes nothing.
Install `mise` itself first,
then [activate it in your shell](https://mise.jdx.dev/getting-started.html#activate-mise)
so the tools it installs are on `$PATH`:

```sh
curl https://mise.run | sh
```

Then, from the repository:

```sh
mise install
uv sync
```

### Authentication

The Docs API needs an OAuth client, which is free and takes a few minutes.
It is per-person: the token identifies you,
and grants read access only to documents you can already open.

1. Open the [Google Cloud console](https://console.cloud.google.com/)
   and create a project, or reuse one.
2. Enable the **Google Docs API** for it,
   under *APIs & Services* → *Library*.
3. Under *APIs & Services* → *OAuth consent screen*, configure it as
   **External**, in **Testing**,
   and add your own Google account under *Test users*.
   Nothing is being published to Google, so it never needs verification.
4. Under *APIs & Services* → *Credentials*,
   create an **OAuth client ID** of type **Desktop app**, and download its JSON.
5. Save it as `~/.config/eta-publish/client_secret.json`,
   or point `$ETA_CLIENT_SECRETS` at it.

The first run opens a browser to approve read-only access.
The token is cached at `~/.config/eta-publish/token.json` and refreshes itself,
so this happens once.
Both files are secrets;
the repository ignores them by name, but they belong outside it anyway.

### Archiving new sources (optional)

Every build looks up existing Wayback Machine captures of the sources a report cites,
which needs no account.
Asking for a *new* capture goes through
[Save Page Now](https://archive.org/account/s3.php),
which works best with an archive.org account:
put its keys in `$SPN2_ACCESS_KEY` and `$SPN2_SECRET_KEY`,
or run `ia configure` once, whose `ia.ini` is read when those are unset.
Without them a build asks for captures anonymously, and warns that it is:
one every 30 seconds, rate-limited much harder, and vaguer about failures.
In CI (wherever `$CI` is set) it does not,
and sources with no capture publish saying they have no archive, which is true.
`--no-archive` skips both halves.
[Source archiving](#source-archiving) explains what a build does with them.

## Building

```sh
# Every report in `reports.toml`, into `site/unpublished/`.
uv run eta-publish all

# Or one document, before it is on the list, somewhere scratch.
uv run eta-publish one <google-doc-url> -o out

# Or a different list.
uv run eta-publish all drafts.toml -o preview

# Add a document to the list, named as the document names itself.
uv run eta-publish add <google-doc-url>

# Write `eta_publish/assets/logo.svg` from `logo.src.svg`, after editing the logo.
# Every build does this first anyway.
uv run eta-publish logo

# Without the slowest question a build asks, when the counts can wait.
uv run eta-publish all --no-comments

# Rebuild what is committed, from the responses saved beside it. No network.
uv run eta-publish all --offline
```

`all` takes a list and `one` takes a document.
A document can also be a directory a previous build wrote,
which holds the API response as `doc.json` beside its outputs,
so anything built once rebuilds with no network and no credentials.
A report already in `reports.toml` can be named instead, in any case,
as in `eta-publish one 'IBX Automation' -o out`,
and is then checked against its entry as `all` checks it.

Pass the full URL including its `?tab=` id.
ETA reports live in multi-tab documents,
and the Docs API defaults to the first tab, usually an earlier draft.
A multi-tab document with no tab specified refuses to guess and lists its tabs.
The URL is the only way to name a tab, on the command line and in `reports.toml` alike.

A publish is always a site, whether it holds one report or four:
each lands under the path its own front matter names,
alongside an `index.html` listing them.
Outputs land in `out/<the report's path>/`,
each report's images in an `images/` directory beside its pages.
One report failing to build does not stop the rest;
the run exits non-zero and the index names what failed.

Flags worth knowing:

- `--split` cuts at `h2` boundaries, for a report over the
  [code block limit](#squarespace-constraints).
- `--no-images` skips the image download while iterating on the text.
- `--no-comments` skips counting comments, leaving the last count standing.
- `--offline` skips the network altogether, for a change to this code rather than to a document;
  see [builds](#builds) for what it cannot notice.
- `--no-archive` skips looking up and submitting archive captures.
- `--suggestions accepted` previews the document with its open suggestions accepted
  instead of rejected.

## Adding a report

Adding the next report is an entry in `reports.toml` and nothing else,
which `eta-publish add <url>` writes:

```toml
[[report]]
name = "Next Report"
tab = "Draft 2"
url = "https://docs.google.com/document/d/<id>/edit?tab=<tab>"
published = "draft"
```

`name` and `tab` are what the document and its tab are called in Drive,
which is why the command writes them rather than asking anyone to type them:
a `?tab=` id is opaque, so nothing but the document itself
says which of its drafts an entry points at.
A build holds both up against the document it fetched
and refuses the report when they disagree,
a blank one included: no document is called nothing.

`published` is whether the report is out on Squarespace, and how:
`automated` when the live page is the pasted `report.html`,
`manual` when it is a page built by hand,
and `draft` until it is out.
It is required, and `add` writes `draft`.

Putting a report on the list is the act that says it is ready:
nothing published is built from anything else.
Build a document on its own first with `uv run eta-publish one <url> -o out`.

## Publishing to GitHub Pages

`.github/workflows/pages.yml` runs `eta-publish all`,
which builds **every report in `reports.toml`**
from its live document and deploys them as one site.
Each lands at the path its own front matter names,
so `/reports/digging-out-deep-hole-sas-west` in the header
becomes `kkysen.github.io/eta-publish/reports/digging-out-deep-hole-sas-west/`
(under `reports.toml`'s `site`),
serving `index.html` there
alongside `report.html`, `report.pdf`, and its images.
The site's front page lists them,
with each report's date, byline, and warning count,
and names any report that failed to build.

It runs on a push to `main`,
and on `workflow_dispatch` to redeploy the same list on demand.
CI authenticates as a **service account**, not a person;
[the Pages pipeline](#the-pages-pipeline) explains why.

Set it up once:

```sh
gcloud auth login
gcloud config set project eta-publish

gcloud iam service-accounts create eta-publish-ci \
  --display-name "eta-publish CI"

gcloud iam service-accounts keys create key.json \
  --iam-account eta-publish-ci@eta-publish.iam.gserviceaccount.com
```

No IAM roles are needed: access to the document comes from sharing it,
not from a project role.

Then share each report with
`eta-publish-ci@eta-publish.iam.gserviceaccount.com` as a **Viewer**.
Sharing the folder a report lives in is the better move:
it covers the document, the images, and the Drive files
the document links as `SVG:` charts in one action,
and it covers the next report in that folder without another visit.
Without the chart files, the vectors fall back to the rasters with a warning.

Finally, hand the key and the document URL to GitHub, and delete the key:

```sh
gh secret set GOOGLE_CREDENTIALS < key.json
rm key.json

# Pages serves what the workflow uploads, rather than a branch.
gh api -X POST repos/:owner/:repo/pages -f build_type=workflow
```

Then run it with `gh workflow run Pages`,
or from the Actions tab.

Two things to know about the key:

- **It is a long-lived secret in a public repository's settings.**
  Fork pull requests never receive it,
  and `pull_request_target`, which would hand it to unreviewed code,
  is deliberately not used here.
  Anyone with write access can read it, as with any Actions secret.
- **Rotate it with**
  `gcloud iam service-accounts keys list --iam-account <account>`
  and `keys delete`, which revokes it immediately.
  Workload Identity Federation removes the stored key entirely
  by exchanging GitHub's OIDC token for a short-lived one;
  it is the better answer if this outlives being a convenience.

The deployed site is public.
It publishes an unreleased report at a stable URL,
which is a decision rather than a detail:
build it as a plain artifact instead
(swap the last two steps for `actions/upload-artifact`)
if a report should stay inside the repository until it ships.

## Writing a report

The converter reads structure, so the doc has to carry it.
Anything it cannot classify is reported as a warning rather than silently dropped.

None of this is fixed. If a convention is awkward to write,
it is easier to change the converter than to fight it in every report, so say so.

### Front matter

"Front matter" is the block of `Key: value` lines at the top of a document
that describes it rather than being part of it:
where it publishes, what its summary is, who wrote it.
The name comes from printing, where the front matter is the title page
and copyright notice, as distinct from the body.

ETA reports already have one, under the `Header` heading:

```text
Header
Project Manager: Khyber Sen
Phase: published
URL: /reports/digging-out-deep-hole-sas-west
SEO Description: A 125 St subway should be a slam dunk ...
```

The converter reads that block into metadata and keeps it out of the body.
`URL:` becomes the published path, and a document without one is refused
rather than published under a guess at it.
`SEO Description:` becomes the page description,
`Short:` is a blog post's Squarespace excerpt, or a page's line in `What's New`,
and the summary on the report's card in the site index,
`Excerpt:` is no longer used and warns, suggesting `Short:`,
`Public Contributors:` becomes the byline,
named the way the header lists them,
and `Final Due Date:` becomes the dateline.
`Social Title Card:` names the share card, the picture a link to the report unfurls as,
which is what Squarespace calls the page's social image:
the value is the file's name, linked to the file,
and the picture itself goes on the line under it.
A header without one warns, and a picture above the headline stands in as the card.
`Private Contributors:` is never read for the byline,
which is the point of the two fields being separate.
`SME/Liaison:`, `Goals:`, and `Audience:` are for the editors and never published,
but a header without them warns; `SME/Liaison:` may be left empty.
Everything else is carried along and made available to the templates.

Three rules matter, because all three are load-bearing:

**The name is underlined, up to but not including the colon.**
That is what makes a line a field rather than prose that holds a colon,
and it is the only thing that does.
Docs carries the underline forward as you keep typing,
so turn it off after the name:
an underline running into the value is reported.

**The block ends at the first line that is not `Key: value`.**
Any heading, the headline, a paragraph containing an image, or ordinary prose.
Keep the header lines together, with nothing between them.

Lines *before* the `Header` heading are production scaffolding and are dropped,
each one reported so nothing leaves silently.
The SAS West tabs open with `Header` directly, so this is defensive.

**The headline must be styled `Title`.**
The underline rule already keeps
`Digging Out of a Very Deep Hole: Saving Billions on 125th Street`
out of the metadata, but the headline still has to be a headline:
without the style the converter falls back to the Drive filename,
a working name (`SAS West Feasibility Response`) and not what should publish.
Alternatively, put `Title:` in the header block.

Unrecognized keys are kept rather than treated as body text,
so adding a field to a future report is safe.

### The rest

- **Real heading styles**, not bolded body text.
  Heading text determines the anchor, which is a published URL,
  so renaming a heading moves it unless an override is set.
- **Real footnotes.** Numbering and backlinks are generated from them.
- **Images inserted inline.**
  The lines around an image are folded into its figure:
  a `Source: <file>` or `Source: <url>` paragraph before it,
  or an `[Image Source](<url>)` paragraph after the caption,
  plus the caption and a `Credit:` line.
  `Image Source` still works but warns, asking for a `Source:` line instead:
  one label, in one place.
  Each of these names is underlined too, for the same reason a field's is;
  a linked one needs no underline, since Docs draws one under every link.
  The underline marks the line and is not published:
  a figure's credit reaches the page with no rule under `Credit`.
  A paragraph whose entire text is the link, reading just `Image Source`,
  counts as the same note;
  a paragraph that merely starts with the word is prose and is left alone.
  Both spellings of the source are treated as editorial notes:
  they are kept in the Markdown archive as comments
  and never appear in the published HTML or the PDF,
  matching the live page,
  where `Source:` and `Image Source` each appear zero times
  and `Credit:` appears 26 times.
  When an image has no alt text in Docs, its caption is used,
  which is what the live page does by hand.
- **A chart credited to ETA carries the ETA logo.**
  An SVG whose `Credit:` line starts with `ETA` gets the logo, with `etany.org` under it,
  in its top right corner,
  where that corner is empty.
  Where it is not, the chart grows a strip along its top, in its own background color,
  and the logo goes there, so it never covers anything the chart draws.
  The chart is drawn with `resvg` to see which,
  with DejaVu standing in for whatever fonts it names.
- **A `Source:` in our GitHub repos is the picture.**
  When a `Source:` links a file in an `effective-transit-alliance` or `kkysen` repo on GitHub,
  or a release asset of one,
  that file is downloaded on every build in place of the copy pasted into the doc,
  so a regenerated chart publishes without being pasted again.
  The doc's crop is still applied to it.
  An `.svg` is taken exactly as an `SVG:` line linking it would be;
  any other file that cannot be downloaded falls back to the doc's copy with a warning.
  One whose pixels differ from the doc's copy of the same type is warned about,
  once the larger is scaled to the smaller, since Docs shrinks a wide paste,
  since the doc is then showing its editors an outdated picture.
- **Suggestions are rejected.**
  The doc is fetched as it currently reads, with every open suggestion rejected,
  so nothing publishes because someone proposed it and no one noticed.
  `--suggestions accepted` previews the other way.
- **Tabs.** Pass the URL including its `?tab=` id.
  The SAS West document has eight tabs,
  including `Draft 1 [OBSOLETE]`, `Draft 3 [OBSOLETE]`, `Research`, and `Notes/Scratch`.
  The Docs API returns only the first tab unless asked otherwise,
  so publishing the wrong draft is a real possibility rather than a theoretical one.
  A multi-tab document with no tab named refuses to guess and lists what it found.

### House style

The build also reads prose that parsed cleanly, and says where it is spelled
against the way every other report spells the same thing.
None of these is rewritten on the way out:
making the reports agree is the writer's, and the build only says where to look.

- **One space after a sentence**, not two.
  The pair is invisible everywhere anybody would catch it:
  Docs shows one space either way and HTML collapses it,
  so only the Markdown archive keeps it, and keeps it forever.
- **One space between two words.**
  The same characters and a different mistake, so a different warning:
  between sentences the pair is a typewriter habit, and mid-clause it is
  a slipped finger.
- **No space beside an em or en dash.**
  Every dash in the reports today is closed up;
  a spaced one arrives by pasting from somewhere that sets them open.
- **`ETA`, not `the ETA`**, the way one writes `NASA said`.
  Spelled out it does take the article: `the Effective Transit Alliance`.
- **Stations and streets as the MTA writes them**:
  `125 St`, not `125th Street`; `2 Av`, not `2nd Ave`;
  `Queens Blvd`, `Fordham Rd`, `Henry Hudson Pkwy`.
  A reader who goes looking for the station should be looking for what the
  platform says, so a number written as a word is a digit too:
  `Second Avenue` is `2 Av`.
  The exception is the phrase `Second Avenue Subway`, the project's own name,
  which `Second Ave Subway` is corrected towards rather than to the station.
  A street somewhere else has no MTA spelling,
  so `Nanba Road` and `Heping South Street` are listed in `ELSEWHERE`
  in `eta_publish/style.py`, which is where the next one goes.
- **Units as symbols after a number**:
  `137 ft`, `180 m`, `3 lb`.
  A column of `137 ft`, `140 ft`, `969 ft` is a comparison;
  the same numbers spelled out is a paragraph to read twice.
  Times may be either: `5 min` and `5 minutes`, `30 sec` and `30 seconds`.
  `mile` is the one length written out, and a number written as a word is
  left alone: `ten minutes` is a duration being described rather than measured.
  The units `eta_publish/style.py` knows are the ones these reports use:
  `ft`, `in`, `m`, `km`, `mm`, `cm`, `t`, `lb`, `kg`, `min`, `sec`, `mph`,
  `km/h`, `tph`, `dB`, `Hz`, `V`, `kV`, `kW` and `MW`.
  A unit introduced with its symbol after it, `30 trains per hour (tph)`,
  is being defined rather than misspelled, and is left alone.
- **`$` and `%`, never the word**:
  `3.5 percent` is `3.5%`, and `7.7 billion dollars` is `$7.7 billion`,
  with the scale carried across rather than left behind.
  `in 2026 dollars` is not a sum of money and is left alone.
- **No hyphen between a number and its unit**, even where English wants one.
  `a 600-foot train` is `a 600 ft train`, so a measurement is written one way
  wherever it appears and a search for `600 ft` finds all of them.
  The hyphen and the spelling are separate warnings,
  since a measurement can have either mistake without the other.

Each warning opens with `style: `,
because the rest of a document's warnings are things the build could not do
and these are things somebody may want to write differently.
The spaces a warning is about are drawn as `·`,
since quoted as themselves they are one space in HTML and in the PDF alike
and the line looks correct.
In a terminal they are highlighted as well as drawn.

These read the whole document: the body, the headings, the captions,
the footnotes, and the header's own prose in `SEO Description:`.

# How it works

## Design decisions

### The Google Docs API, not an HTML export

We read the doc with the Docs API (`documents.get`),
not Drive's HTML export.
The export is `<span class="c12">` soup with no semantics.
The API JSON gives us the three things a report actually needs:

- `footnotes` as first-class objects, with `footnoteReference` inline,
  so numbering and backlinks are derived rather than typed
- real named paragraph styles, so headings are headings
- `inlineObjects`, so images carry their alt text

### One tree, three emitters

Every output is emitted from the same document tree.
In particular, the HTML is **not** rendered from the Markdown.
Chaining them would add a lossy hop
(the source/caption/credit triple, superscripts, exact link targets)
and would create two sources of truth
the moment someone hand-edited the `.md`.

### Determinism is a feature, not a nicety

Unchanged input must produce byte-identical output.
The `.md` is committed to git, so every accidental difference
becomes noise in a diff that someone has to read.

So image filenames are keyed on what the document says about an image
rather than on a counter:
the file its `Source:` line names,
or the file at the end of the URL a `Source:` or `Image Source` links,
and the stable Docs object id where there is no such line.
A `Video:` line's file is named for its link's text, or hashed from its URL where the text is the URL.
Inserting one image into a 54-image report
must not rename the other 53 or move their published URLs.
The same applies to heading anchors.

A paragraph has no name of its own,
so it is named by the section it is in and its place in that section:
`#ground-conditions-p2`.
That is a link worth reading before following it,
and it survives the copy edits that are most of what happens to a published report.
It does not survive an insertion above it in the same section,
a smaller blast radius than numbering the page as a whole
and a larger one than hashing the text,
which moved the id of every paragraph anyone corrected.

### Semantic line breaks in the Markdown

The `.md` breaks lines at sentence and clause boundaries
rather than wrapping to a fixed width.
Wrapped, a paragraph is a single line
and correcting one word shows up as the whole paragraph changing.
Broken at sentences, the August 21 addendum to the SAS West report
is a three-line diff.

The splitter is conservative,
because the text is full of `125 St.`, `Phase 2.`, and `$7.7 billion.`,
and an over-eager one would churn the diff on every regeneration.
Changing it reflows every file, and should be its own commit.

## Source archiving

A link is a claim about a page nobody promised to keep.
*Digging Out of a Very Deep Hole* cites 113 of them:
33 on `www.mta.info`, 12 on `transitcosts.com`, 9 on `mp.weixin.qq.com`,
the rest agency press releases and news sites,
which are exactly the pages that get reorganized.
The report is supposed to outlive them.

So every external link carries a `[n]` into a `Sources` section at the end,
where the entry names the page and the capture of it,
with a `↑` back to each citation.
Hovering a citation does show the pair, built from the entry by `report.js`,
but it is not the way to it:
a phone has no hover and a printed page has no links at all,
so the number and the section are what always work.

`archives.json`, committed beside `report.md`, is the record of
which capture belongs to which source, keyed by the original URL
without its fragment.
A fragment never reaches a server: `#page=28` is an instruction to the PDF
viewer once the file has arrived, so the fifteen pages of one MTA PDF that
SAS West cites are one file to capture, and the page goes back on the
archived link so it still opens where the citation meant.

A `#page=` citation is archived with Wayback's `id_` modifier,
which is what makes that work.
The ordinary Wayback URL for a PDF is not the PDF:
it is an HTML page carrying the capture toolbar with the file inside it,
so the browser applies `#page=50` to that wrapper and the reader gets the cover.
Asked for raw, the same capture comes back as the PDF itself.
An HTML capture is the archived document,
so an anchor in one already resolves and it keeps the ordinary URL.
A build submits only what is missing from it,
so a source keeps the capture it has:
the point of a snapshot is that it is of the page as the report read it,
and recapturing would quietly move it forward to whatever the page says now.
A source the archive gave no answer about,
because it was busy, refused for the day, or is still capturing it,
publishes as not archived with the reason, and warns,
and is recorded `pending` so the next build that can asks again;
the build itself succeeds.
A capture already asked for is asked about by its Save Page Now job,
which the build keeps in its cache, rather than submitted again,
and a capture of any one source is asked for at most once a day.
A document that already writes a link as `web.archive.org/web/<ts>/<url>`
has it unwrapped on the way in and seeds the record with the capture it named,
so a source archived by hand and a source archived here are one source.

### Finding an existing capture

Every build asks the Wayback Machine what it already holds,
which needs no account and is most of the answer:
11 of IBX Automation's 14 sources were already archived by somebody else.
Only the newest capture that came back `200` counts,
because a page that has been taken down still gets crawled
and its newest captures are of the 404.
The replay is asked first and the index only if it did not answer.
`web.archive.org/web/2099/<url>` redirects to the capture closest to a date
nothing is archived past, which is the newest one,
and asking for that capture says whether it serves the page:
a point lookup of about 200 ms against a filtered scan of a URL's whole row set,
which took anywhere from 0.5s to 31s for the same query.
Sixteen sources took 11.7s that way and 47.3s through the index.
`wayback/available` would be a third way to ask and answers `429` outright.

`200` from the replay is the answer the index is asked for,
arrived at the other way round, and on one point it is better evidence:
the index says a crawler once logged `200`,
while this says the URL the report is about to publish serves the page.
It is looser on `warc/revisit`, a capture recording that the bytes
had not changed, which carries no status in the index and is filtered out
but which the replay resolves and serves.
`hsr.ca.gov`'s 2026 business plan is one, five weeks newer
than the newest row the index allows and the same digest.
Anything but `200` falls through to the index,
because the newest capture that *was* the page is a different question:
the NYT's 125th Street piece is captured daily
and its newest capture replays `403`.
A source with no capture falls through too,
so `not archived` still rests on the index rather than on a `404`.

What cannot be checked: a capture that answered `200`
with a login wall or a site's own "page not found"
is a capture of a page that loaded,
and nothing in the index tells it from the real thing.

### Remembering what was not found

An index lookup that finds nothing is remembered for a week,
in `archive.json` in the user cache directory `platformdirs` finds
(`~/.cache/eta-publish` on Linux) and never committed.
The index takes seconds per source and sometimes half a minute,
so a report with twenty unarchived sources spent minutes on every build
to write down the same nothing;
and nothing is what it writes, because a source with no capture
has no entry in `archives.json` either way.
So the cache cannot change what a build produces,
which is what lets it expire, be thrown away, or be missing on a fresh clone
without `scripts/check-committed-site.sh` noticing.
What changes the answer is somebody else archiving the page,
which happens on the scale of weeks if it happens at all.
CI keeps the same file through `actions/cache`,
because a runner starts with nothing and would re-ask about all of them.
A build that has [Save Page Now keys](#archiving-new-sources-optional) skips the cache:
that one submits a capture instead, and the source leaves the record for good.

The replay is remembered too, for an hour, in the same file.
It is the half that notices a capture somebody else has just made,
so it cannot be held back for a week the way the index is;
an hour is long enough that rebuilding twice in a row asks nothing twice.
A capture made inside that hour is not seen until the hour is up.

## Builds

`all` takes a list and `one` takes a document, so nothing has to be told apart:
which of the two a reference is used to be worked out from how it was spelled,
and the command name says it instead.
One at a time either way: building several in one run is what a list is for,
and a list is a file that can be committed and reviewed
rather than a shell line that was right once.

A build spends nearly all its time waiting on Google.
Most of that it now skips on its own: before fetching a document it asks Drive
when the document was last edited, which takes half a second against two for
the document and two more for its suggestions, and reuses the response saved
beside the last build when the answer has not moved. Editing is what moves it,
and proposing or resolving a suggestion is editing, so both are safe to reuse.
Commenting is not, so comments are counted every time.
A saved response also records how it read the document's suggestions
and which shape a build wrote it in, and a build reuses only what it would
have written itself: changing either is a change Drive cannot see,
since the document did not move, the code did.

Beyond that, a rebuild that has to be quicker still has two ways to be:
`--no-comments` skips the text export, which costs more than fetching the
document does and answers a question that changes slowly, leaving the last
count standing; `--offline` skips the network altogether and rebuilds each
report from the `doc.json` saved beside its outputs, which is the whole of a
build apart from asking Google for the text. Offline cannot notice a document
that changed, so it is for a change to this code rather than to a document,
and it is not what the workflow runs.

Reports are built several at a time, since a build is nearly all waiting,
so a list takes about as long as its slowest document rather than as long as
all of them. They are still reported in the order the list gives them.

## The Pages pipeline

Nothing else in the repository or the workflow names a document
but `reports.toml`,
and one report failing to build does not take the others with it;
the run still exits non-zero, and the failure is on the front page.

Nothing published is built from anything but that list.
A report the list does not name has nothing committed
for the build check to compare against,
so publishing it from CI would publish what nobody had reviewed.

It runs on a push rather than a schedule:
a report publishes when someone decides it is ready,
where a schedule would put whatever the doc said at 3 a.m.
onto a public URL with nobody looking.

The job fetches the document rather than deploying the committed
`site/`, because the images are not in the repository
and cannot be recovered from what is:
the `contentUri` values in a saved `doc.json` are signed and short-lived,
and are already `403` the next day.

So CI needs credentials, and they are a service account, not a person.
A service account is an identity inside the Cloud project, with no inbox,
no password, and an empty Drive of its own,
so its key grants read access to exactly what has been shared with it
and to nothing else in anyone's Drive.
The interactive flow is unchanged and still the default:
`_credentials` uses a service account only when
`$GOOGLE_APPLICATION_CREDENTIALS` names one.

## Squarespace constraints

These are load-bearing.
The block counts, the 7.1 version, and the two documented limits
were verified against the live site and Squarespace's own documentation;
the one estimate below is marked as such.

- **There is no content API.** The public Squarespace API covers commerce only.
  Nothing can create or update a page from a script,
  so the final step is necessarily a human paste.
  The goal is to make it *one* paste instead of 162 placements.
- **`etany.org` runs Squarespace 7.1**,
  so Developer Mode, Git, and SFTP are unavailable; those are 7.0-only.
  A single code block on an otherwise empty page
  is the closest thing to a pure HTML page, and it is close enough.
- **A code block holds 400 KB (~300,000 characters).**
  Two measurements bracket the SAS West report: its source text is 69 KB,
  and the live page's rendered text blocks come to 226 KB
  including Squarespace's own markup, which this emitter does not produce.
  The fragment should land between them, comfortably inside the limit,
  but it has not been generated from the real document yet.
  `--split` cuts at `h2` boundaries for a report that does not fit.
- **There is no file upload API.**
  Custom Files is a manual GUI that accepts images and fonts only.
  Host report images elsewhere and reference absolute URLs;
  the PDF needs those same local files anyway,
  so one upload serves both outputs.

## Rate limits

Not a concern at this scale.
The Docs API allows
[3,000 read requests per minute per project, and 300 per minute per user](https://developers.google.com/workspace/docs/api/limits).
One publish is one request,
so an afternoon of rebuilding sits orders of magnitude under the limit,
and exceeding it returns HTTP 429 rather than costing anything.

# Development

After [setup](#setup):

```sh
pre-commit install
uv run pytest
```

`mise` pins the `biome` version in `mise.toml` and nowhere else,
because the emitted HTML is committed
and a formatter that changed its mind between versions
would rewrite every report without a report having changed.

`ruff format`, `ruff check`, `ty`, `pyrefly`, and `pytest`
run as pre-commit hooks and again in CI.
Tests run against checked-in Docs API responses,
so neither ever needs Google credentials or the network.

`pytest` also rebuilds all of `site/` with `eta-publish all --offline --no-images --into`,
in the background while the rest of the suite runs,
and fails if that differs from what is staged,
so a change to the code is committed with the pages it now writes.
It fetches nothing and needs no images, credentials, or network,
so it runs the same in CI as on a machine that has built the site.

One more hook runs on push rather than on commit:
`scripts/check-committed-site.sh` rebuilds `site/` by fetching the documents
and fails if that differs from what is committed.
The Pages workflow runs the same script before it deploys,
so this is the deploy's own check,
run on the way out rather than after the push.
It runs on every branch, not only `main`:
a branch whose site is already stale is a merge that will fail.

It needs credentials and the network, unlike everything else here,
and `git push --no-verify` skips it when those are what is missing.
When it fails, the rebuilt files are left in the working tree,
which is what to read and commit.

`site/unpublished/` is every report, drafts included, committed:
a report at its published path with its `doc.json` and everything emitted from it,
and `site/unpublished/assets/` holding the one copy of the stylesheets and script
that every report page links.
It is what GitHub Pages serves.

`site/published/` is the part of it a live page needs:
for each `published = "automated"` report,
its `report.html` and any `--split` pieces, its `report.md`,
and every file that `report.html` links on the site,
at the same paths, so either directory serves the same URLs.
It is written from `site/unpublished/` after every build,
so a report that failed to build keeps hosting its last copy,
and a build with the pictures on disk fails
when a live page links one that is not there.
Only its text is committed, as with the rest.
It doubles as the project's main test corpus,
because an actual `documents.get` response for a real report
is where every bug that mattered came from.

`tests/fixture/` is the same directory in miniature,
from a hand-written document,
for the tests that want to be fast rather than real.

Every build saves the response as `doc.json` in the report's own directory,
so the pipeline re-runs against the last fetch with no network: pass the directory.
That is what the tests do.
Either `site/unpublished/` or `tests/fixture/` can be rebuilt that way,
which reads the saved response and needs no credentials:

```sh
uv run eta-publish one site/unpublished/reports/digging-out-deep-hole-sas-west
```

Add `--no-images` and it needs no network at all.
The one thing a no-network rebuild cannot reproduce is the image extensions:
a Docs `inlineObject` says nothing about what kind of file it is,
so `.jpg` and `.png` are learned by fetching, and without that the links lose them.
The names come from the document,
and each image's shape is read from the committed `images.json`,
so the page is otherwise the page that publishes.

When a snapshot changes, read the diff before accepting it:
it is exactly what the change does to a real published report.
Regenerate with `uv run pytest --regenerate-snapshots`.

# Status

The parser and all three emitters work, against a fixture.

**Not yet run against a real report.**
That needs OAuth credentials, and it is the next thing worth doing:
every finding so far that mattered came from the real document's shape
rather than from the fixture, and there are almost certainly more.
It will also settle the code block size estimate,
the one unmeasured number here.

# TODO

## Preserve the anchors of already-published reports

Existing reports have short, hand-chosen anchors.
The live SAS West table of contents links to `#elephants` and
`#unlearned-lessons`, where generated anchors would be
`#the-elephants-in-the-room` and `#the-unlearned-lessons-of-recent-projects`.
Regenerating one of those reports as-is would break every inbound link
to a section, including links from outside `etany.org`
that we cannot see or fix.

`AnchorAllocator` already accepts an `overrides` mapping;
what is missing is somewhere in the doc to write them
and a decision between two approaches:

- **Remap**, pinning each heading to its existing anchor.
  Keeps one anchor per section and keeps the short readable URLs,
  which are nicer than slugified headline text regardless of history.
- **Emit both**, generating the new anchor and keeping the legacy one
  alongside it as an empty target, so old links keep working.
  Safer for links already loose in the world,
  at the cost of two anchors per section.

These are not exclusive: remapping suits reports we are actively
republishing, and duplicate legacy targets suit ones we are not.

Wherever the overrides live, they have to be in the Google Doc,
since that is the source of truth
and the person republishing a report will be working there, not here.

# Possible directions

**Version history.** Because the `.md` is regenerated and committed
on every publish, git accumulates a usable history for free.
Reconstructing the *existing* Google Docs history is a separate problem
and probably not worth it: the Drive Revisions API merges revisions for Docs
and may omit older ones, so a faithful replay is not available.

**A PDF-first review loop.** The Typst template is deliberately plain.
Once a report has actually been through it,
the house style is the obvious next thing to invest in.

**A static site.** `reports.etany.org` built from the same tree in CI
would remove the paste step entirely, along with the block limits,
and would give real per-draft previews.
Once the tree and emitters exist this is nearly free:
same HTML, different wrapper.
It is an organizational decision rather than a technical one,
and nothing here forecloses it.
