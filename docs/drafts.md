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
A new publication starts as a draft:
`eta-publish add <url>` writes its entry into `drafts/publications.toml` by default,
and refuses with no clone of `eta-drafts` there rather than adding it here;
`-p publications.toml` adds it to this repository's list instead, on purpose.
A manually published report becomes an automatically published one
once its publishing is switched to the tool,
by changing its `published` to `"automated"`, in one commit here.
When a draft is published, it moves from `eta-drafts` into this repository,
with `eta-publish publish <name>`, as `automated` unless `--as manual` says otherwise:
its entry moves from `drafts/publications.toml` to `publications.toml`,
and what its last build saved, `drafts/site/unpublished/<path>/`, moves to `site/unpublished/<path>/`,
so this repository's offline build has its `doc.json`.
It only edits files: rebuild with `uv run eta-publish all`,
then commit in `drafts/` first, and then here,
since `scripts/drafts-commit.sh head`, making the code commit's drafts commit, refuses a `drafts/` with changes not committed.

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
`scripts/drafts-commit.sh` records the pin without a checkout,
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

**Locally, on commit:** `pre-commit` builds the drafts with the code being committed,
and fails the commit on a build error, as a broken publication here does.
It builds into a directory of its own, leaving `drafts/` as it is.

**Locally, on request:** `scripts/drafts-commit.sh head`
makes the drafts commit for the code commit just made, `HEAD`.

- It commits the new pin and the rebuilt drafts in `drafts/`,
  on the branch of the same name, which starts from `main`'s drafts commits the first time.
  The rebuild is offline and with no images, as CI's is,
  so the same code commit builds the same files on both.
  It leaves the commit to CI when the working copy isn't the code committed,
  as with `git commit <path>`, or when commits before it have no drafts commits yet,
  since only the code checked out can be built with.
- After an amend or a rebase, the drafts commits for the commits rewritten are dropped,
  and it makes new ones, the way the code branch itself was rewritten.
  It drops only drafts commits it made itself, which it can make again,
  and never one on `origin`'s `main`.
  Anything else in the way, such as a pull, stops it, to be rebased by hand,
  and so do uncommitted changes in `drafts/`.

Both are modes of `scripts/drafts-commit.sh`, and only the build check is a hook.
`drafts/` gets its own `pre-commit install` for the `pre-push` check below.

**On push, in CI:** `.github/workflows/drafts.yml` here starts `eta-drafts`'s `sync.yml` with the branch.
It finds the code commits on the branch with no drafts commit yet,
from the pin of the drafts branch's last commit, with `scripts/drafts-commit.sh missing`,
and sets up with the oldest's own build setup.
A job can set up only once, so it makes the drafts commits, each with its own commit's code,
for the oldest and the ones after it up to the first whose build setup differs, 100 at most,
then starts another run for the rest, and once there are none left, the deploy.
Runs for a branch go one at a time, none cancelled once running,
and each finds the commits afresh, so a run GitHub replaces while it waits leaves none out.
This covers commits made where there's no `drafts/`, such as GitHub's web editor,
and the ones `scripts/drafts-commit.sh head` leaves to CI.
A rewritten code branch gets its drafts commits made again, as `scripts/drafts-commit.sh head` does after a rebase,
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
  It's never in `report.partial.html`, the Markdown, or the PDF.
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
with a token from the GitHub App `eta-drafts-ci-dispatch`,
which can only run `eta-drafts`'s workflows.
[`accounts.md`](accounts.md) has the service account and the App.

## What `eta-publish`'s commits show

The drafts commits and the deploys are made in `eta-drafts`, which is private,
so its runs say how they're going on the `eta-publish` commits they're for,
as two commit statuses, shown with the checks on each commit and pull request:

- **`eta-drafts / sync`:** pending on the commit pushed, from `drafts.yml`,
  or failure if it couldn't start the sync, and error if its run was cancelled before starting it.
  Each sync run sets it pending on the code commits it makes the drafts commits for, linking the run,
  then success on each of them, once pushed,
  or on the branch's last commit if none was missing,
  and failure on the one whose drafts commit failed, or on the oldest if the run fails otherwise before pushing.
  A refused push leaves them pending, for the next run to make again.
- **`eta-drafts / deploy`:** on the `eta-publish` commit a deploy pins,
  pending once the sync starts the deploy, and again once the deploy starts, linking the run,
  then success linking the site deployed, failure if it fails,
  and error if a newer deploy of the branch replaces it.
  A deploy started by a push to `eta-drafts` sets it too.

`drafts.yml` sets its statuses with its own run's token.
`eta-drafts`'s runs can't, since theirs are for `eta-drafts` alone,
so they set theirs with a token from the GitHub App `eta-drafts-ci-status`,
which can only set commit statuses, and only on `eta-publish`.
[`accounts.md`](accounts.md#github-apps) has both Apps.

### Nothing is left pending

A run's own steps set statuses only on the commits it knows of,
so every sync and deploy run ends with a `sweep` job, whatever happened before it,
which settles what's still pending on the branch's commits.
It's `eta-drafts`'s `.github/workflows/sweep.yml`, running `scripts/sweep-statuses.sh`,
both read from the commit of the workflow calling it, `eta-drafts`'s `main` for a dispatched run,
not from the branch the run builds, which can be older.
When a sync or deploy run ends with anything but success,
`eta-drafts`'s `reconcile.yml` sweeps again for it,
for when its own `sweep` never ran or didn't finish, as with a lost runner.
It knows the run's branch from its title, `Sync <branch>` or `Deploy <branch>`.

The sweep of a sync run that started the next one goes through only the branch's last commit,
for the status `drafts.yml` set, and the commits the run set pending,
so each run's sweep reads as many statuses as its batch has commits, however many are missing.
Anything else pending is left to the other sweeps:
of the sync run that starts the deploy or no other run, once for each chain of runs, of a deploy, and from `reconcile.yml`.
Those go through the branch's commits,
from its last back along first parents to the first commit with a final `eta-drafts / deploy` and nothing pending,
then every commit in the last one's history but not in that one's.
That commit is where an earlier sweep settled everything before it,
so this relies on every earlier sweep of the branch having run,
`main`'s and any other branch's alike.
It also takes the deploy's pin, and the commits the sync run set pending, in case a force-push has dropped them since.
Of each status still pending, by the run it links and that run's branch,
since a commit can be on more than one branch:

- **`eta-drafts / sync`:** success once the commit has its drafts commit.
  Still with none, it's left to the run it links while that's going,
  left to the next sync run if this run started it, set pending on this run first if `drafts.yml` set it,
  left to a sync run of that branch that's going or waiting,
  and otherwise failure or error: nothing is left to make it.
  On a commit no longer on the branch: error, if it's this branch's run.
- **`eta-drafts / deploy`:** left to the run it links while that's going.
  On the commit this deploy pinned: failure or error if the deploy didn't succeed.
  On any other commit: error, replaced by a newer deploy,
  once this run deployed or started one and no other deploy of that branch is going or waiting.
  With none going, waiting, or done: error.

The commits a force-push drops from a branch, or its deletion, are on none of its runs' sweeps after.
So `drafts.yml` compares the branch before the push with after it, or with `main` once deleted,
and sets error on each dropped commit's status still pending from this branch's runs,
leaving the ones from another branch's runs, which still have the commit, to that branch's sweeps.
It reads which branch an `eta-drafts` run was for with a token from `eta-drafts-ci-dispatch`, asking only to read.

What can still leave a status pending:

- **A run that's never swept:** if a run's `sweep` doesn't finish and `reconcile.yml` never runs for it either,
  as in an Actions outage, or fails itself,
  what it left pending stays so until a later sweep of the branch that goes back through its commits,
  unless a commit behind it has been settled since, where sweeps stop.
- **`drafts.yml`'s own jobs:** nothing reruns its `dropped` job,
  so if that job doesn't finish, what it would have settled stays pending.
  If its `settle` job doesn't run, the pushed commit's status stays pending until the branch's next sync.
- **A run re-run by hand** from the Actions page:
  it keeps its first attempt's link and inputs,
  and the sweep takes a branch's runs to come in the order `drafts.yml` starts them,
  which a re-run of an older one breaks.
