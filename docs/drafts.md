# Private drafts in `eta-drafts`

New publications are drafted somewhere private,
while the code stays open source in this public repository.
The code changes often, mostly to make new drafts look right once published,
so every code change has to be easy to see in every draft,
locally and deployed, before and after it lands.

So the drafts are in a private repository of their own, `eta-drafts`,
cloned inside this one as `drafts/`.
`eta-publish all` builds them along with this repository's publications,
every code commit gets a drafts commit rebuilding them with it,
and the drafts site, `eta-drafts.pages.dev`, shows every publication, drafts included,
for `main` and for every branch.
[`accounts.md`](accounts.md) has the accounts and credentials it uses.

## The three kinds of publication

| Kind | Label on its preview page | Listed in | Public? |
| --- | --- | --- | --- |
| Published by the tool | **Automatically Published** | `eta-publish`'s `publications.toml`, with `published = "automated"` | yes |
| Published by hand, not yet moved to the tool | **Manually Published** | `eta-publish`'s `publications.toml`, with `published = "manual"` | yes |
| Not published anywhere yet | **Draft** | `eta-drafts`'s `publications.toml` | no |

This repository's publications are all built into `site/unpublished/`,
and the automatically published ones, the part their live pages need, into `site/published/` too
(see [the Pages pipeline](../README.md#the-pages-pipeline)).
A manually published report becomes an automatically published one
once its publishing is switched to the tool,
by changing its `published` to `"automated"`, in one commit here.
When a draft is published, it moves from `eta-drafts` into this repository.

The drafts already in this repository's history stay there:
they've all been published since.

All three share one set of paths.
A draft can never be built at a path a publication here already has:
once something is published at a path, it stays live there,
so a draft at the same path is an error, not a replacement.

## Repositories

- **`eta-publish` (public):** the code, the tests, `site/published/`, `site/unpublished/`,
  and their entries in `publications.toml`.
- **`eta-drafts` (private):** the drafts' entries in a `publications.toml` of its own,
  their built output with the saved Google Docs data it's rebuilt from,
  and a submodule `eta-publish`, pinning the `eta-publish` commit that built them.

The pin is a submodule, git's own way to pin another repository.
GitHub shows the pin as a link to that commit,
and each drafts commit's diff shows the pin moving.

The submodule is never checked out.
Locally, `drafts/` is already inside the `eta-publish` checkout,
so checking it out would nest a second copy of `eta-publish` inside the first.
`.gitmodules` sets `update = none` for it, with a comment saying why,
so `git clone --recurse-submodules` and `git submodule update --init` skip it.
The hook records the pin without a checkout,
with `git update-index --cacheinfo 160000,<commit>,eta-publish`,
and the deploy reads it with `git rev-parse HEAD:eta-publish`.

## Working locally

`eta-drafts` is cloned inside the `eta-publish` checkout as `drafts/`,
which `eta-publish` ignores. It's a separate repository with its own commits.

1. **Build with the working copy.** `uv run eta-publish all` builds `drafts/` too,
   with whatever code is in the working copy, uncommitted edits included.
   The drafts' list is `drafts/publications.toml`, with a `[site]` of its own,
   and they are built into `drafts/site/`.
   Only `eta-publish all` with its default list and output does,
   not with another list, `-o`, or `--into`.
   A `drafts/` without its `publications.toml` is an error;
   a list with no entries is fine, and builds nothing.
   With no `drafts/` at all, as in this repository's CI, the drafts are skipped.
2. **Look at the drafts site.** `eta-publish drafts site <dir>`
   builds the drafts site, with all three kinds as [the drafts site shows them](#what-the-drafts-site-shows),
   into `<dir>`, a new or empty directory, uploading nothing.
3. **Preview from the working copy.** `eta-publish drafts preview`
   builds the drafts site the same way,
   and uploads the result as a preview of the current commit,
   behind the same sign-in, with no commit or push.
   Its address is `<alias>-<commit>.eta-drafts.pages.dev`,
   with `-dirty` after it when a tracked file has uncommitted edits,
   where the alias is the branch name as Cloudflare writes it:
   lowercased, with anything not a letter or digit turned into `-`,
   and the commit is its first 7 hex digits.
   A branch name that isn't ASCII, that would start or end with `-`,
   or that is longer than 63 characters is refused,
   since Cloudflare doesn't document what it makes of those.
   Not `<alias>.eta-drafts.pages.dev`, which is CI's preview of the branch, on every push:
   the two would overwrite each other.
   Its pages link within that preview, not to production or the public site;
   a drafts `[site]` other than `unpublished = "https://eta-drafts.pages.dev"`
   and `published = "https://eta-drafts.pages.dev/published"` is refused.
   It builds in a directory of its own in `drafts/`, leaving `site/` and `drafts/site/` as they are,
   and uploads every list's `site/unpublished/` at `/` and `site/published/` under `/published/`,
   with no `doc.json`, through `wrangler pages deploy`.
   It uses the local Cloudflare token, which has Pages Edit.
   It's refused on `main`, and off any branch:
   `main`'s drafts site is only deployed from CI.

## A drafts commit for every code commit

Every commit to `eta-publish` gets a matching commit in `eta-drafts` that:

- pins that `eta-publish` commit, and
- rebuilds every draft with it, from the saved Docs data, without fetching anything,
  the same way `scripts/check-committed-site.sh` rebuilds this repository's site.

So `eta-drafts`'s history shows exactly what each code commit did to each draft,
the way this repository's history does for its own publications.
Its subject names the code commit,
e.g. `` `eta-publish` ff67c5d: Keep the logo's curves as curves ``,
and its message names the full commit, so a drafts commit can be traced back.

**Locally, on commit:**

- `pre-commit` builds the drafts with the code being committed,
  and fails the commit on a build error, as a broken publication here does.
  It builds into a directory of its own, leaving `drafts/` as it is.
- `post-commit` commits the new pin and the rebuilt drafts in `drafts/`,
  on the branch of the same name, which starts from `main`'s drafts commits the first time.
  The rebuild is offline and with no images, as CI's is,
  so the same code commit builds the same files on both.
  It leaves the commit to CI when the working copy isn't the code committed,
  as with `git commit <path>`, or when commits before it have no drafts commits yet,
  since only the code checked out can be built with.
- After an amend or a rebase, the drafts commits for the commits rewritten are dropped,
  and the hook makes new ones, the way the code branch itself was rewritten.
  It drops only drafts commits it made itself, which it can make again,
  and never one on `origin`'s `main`.
  Anything else in the way, such as a pull, stops it, to be rebased by hand,
  and so do uncommitted changes in `drafts/`.

Both are `scripts/drafts-commit.sh`, which `pre-commit install` installs as hooks.
`drafts/` gets its own `pre-commit install` for the `pre-push` check below.

**On push, in CI:** `.github/workflows/drafts.yml` here starts `eta-drafts`'s `sync.yml` with the branch.
It finds the code commits on the branch with no drafts commit yet,
from the pin of the drafts branch's last commit, with `scripts/drafts-commit.sh missing`,
and makes the drafts commit for the oldest, with that commit's code and its own build setup.
A job can set up only once, so it then starts another run for the rest,
and once there are none left, the deploy.
Runs for a branch go one at a time, none cancelled once running,
and each finds the commits afresh, so a run GitHub replaces while it waits leaves none out.
This covers commits made where there's no `drafts/`, such as GitHub's web editor,
and the ones the local hook leaves to CI.
A rewritten code branch gets its drafts commits made again, as the local hook does after a rebase,
and the drafts branch is pushed only over what the run fetched, so a push made meanwhile is never lost.

If both make one for the same code commit, the two are identical,
since the same code rebuilds the same data,
so `git pull --rebase` in `drafts/` drops the local copy.

**Push order:** a drafts commit can only be deployed once
the code commit it pins is on GitHub,
so `eta-publish` is pushed first.
A `pre-push` hook in `drafts/` refuses to push a commit
whose pinned code commit isn't on GitHub yet, and says so.

Pulling new content from the Google Docs is its own step and its own commit in `drafts/`,
which leaves the pin as it is.

## Branches mirror

`eta-publish` development happens on branches,
so each `eta-publish` branch `foo` gets an `eta-drafts` branch `foo`,
holding the drafts commits for `foo`'s code commits,
and deployed to `<alias>.eta-drafts.pages.dev`, with the alias as above.
`main` goes to `eta-drafts`'s `main`, deployed to `eta-drafts.pages.dev`.
Once `foo` is merged, its commits get their drafts commits on `main`.
Nothing deletes `eta-drafts`'s `foo`, even once `eta-publish`'s `foo` is deleted:
that's done by hand.

## Deploys fetch the documents

A publication's images aren't committed (18 MB, rewritten by every fetch),
and the saved `doc.json` can't recover them:
its image links are signed and stop working the next day.
So a rebuild from saved data alone has no images,
which is why this repository's Pages workflow fetches the live documents
instead of deploying the committed `site/`
(see [the Pages pipeline](../README.md#the-pages-pipeline)).

Deploying the drafts site does the same,
both from CI and with `eta-publish drafts preview`:
it fetches the live documents, images included,
so a deploy shows the documents as they are now, not as of the commit.
The drafts commits above still rebuild from the saved data,
since what they record is the committed text, which needs no images.

## What the drafts site shows

`eta-drafts.pages.dev`, and every branch preview, shows all three kinds:
the publications in `eta-publish`'s `publications.toml`
and the drafts in `eta-drafts`'s, all built by the same code:
for a deploy, the `eta-publish` commit the drafts commit pins,
and for a local preview, the working copy.

- The index lists them in three groups, by kind.
- Every preview page has the label saying which kind it is, as this repository's do.
  It's never in `report.html`, the Markdown or the PDF.
- Two publications at one path, in one list or across both, are refused,
  and so are two builds that write different files at one path,
  such as the shared `assets/`; nothing is uploaded then.

## How the deploy is set up

`eta-drafts`'s `.github/workflows/deploy.yml` deploys a branch's last drafts commit:
`main` to `eta-drafts.pages.dev`, and any other branch to `<alias>.eta-drafts.pages.dev`.
It's started by `sync.yml` once the branch has all its drafts commits,
and runs on every push to `eta-drafts` too, as of drafts pulled from their documents.
A newer deploy of a branch cancels the older one.

The deploy workflow checks out the `eta-publish` commit the drafts commit pins,
and runs that commit's `.github/actions/build-setup`,
so it sets up exactly what that commit's code was written against,
the same way this repository's Pages workflow does.
It builds and uploads with `eta-publish drafts deploy --branch <branch>`,
which refuses to run anywhere but GitHub Actions,
and reads the Cloudflare token from `$CLOUDFLARE_API_TOKEN`.

It reads the documents as the `eta-publish-ci` service account,
signing in with Workload Identity Federation rather than a key,
which the organization's policy forbids creating.
Each draft, or its folder, has to be shared with that account as a Viewer.

`eta-publish`'s `drafts.yml` starts `eta-drafts`'s `sync.yml`
with `DRAFTS_DISPATCH_TOKEN`, a token limited to `eta-drafts`.
[`accounts.md`](accounts.md) has both.
