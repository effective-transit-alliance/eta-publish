# Plan: private drafts in `eta-drafts`

Decided 2026-11-20, and updated 2026-11-21 with what's been decided and set up since.
Of the code, steps 1 to 3 of the order of work below are built:
`eta-publish all` builds `drafts/`,
`eta-publish drafts site` builds the drafts site with all three kinds,
`eta-publish drafts preview` uploads it as a branch's preview,
and `eta-publish drafts deploy` uploads it from CI.
`eta-drafts` has no deploy workflow running `eta-publish drafts deploy` yet.
So is what the drafts share with this repository's own site:
the build setup, `.github/actions/build-setup`;
the refusal of two publications at one path;
and the label on every preview page saying which kind of publication it is.
The rest isn't merged yet.
[`accounts.md`](accounts.md) has the accounts and credentials it uses,
which already exist.

## Goal

New publications have to be drafted somewhere private,
while the code stays open source in this public repository.
The code changes often, mostly to make new drafts look right once published,
so every code change has to be easy to see in every draft,
locally and deployed, before and after it lands.

## The three kinds of publication

| Kind | Label on its preview page | Where it lives | Public? |
| --- | --- | --- | --- |
| Published by the tool | **Automatically Published** | `eta-publish`, `site/published/` | yes |
| Published by hand, not yet moved to the tool | **Manually Published** | `eta-publish`, `site/unpublished/` | yes |
| Not published anywhere yet | **Draft** | `eta-drafts` | no |

A manually published report moves from `site/unpublished/` to `site/published/`
once its publishing is switched to the tool, in one commit here.
When a draft is published, it moves from `eta-drafts` into this repository.

The drafts already in this repository's history stay there:
they've all been published since.

All three share one set of paths.
A draft can never be built at a path a publication here already has:
once something is published at a path, it stays live there,
so a draft at the same path is an error, not a replacement.

## Repositories

- **`eta-publish` (public):** the code, the tests, `site/published/`, `site/unpublished/`,
  and their entries in `publications.toml`. Unchanged apart from what's below.
- **`eta-drafts` (private):** the drafts' entries in a `publications.toml` of its own,
  their built output with the saved Google Docs data it's rebuilt from,
  and a submodule `eta-publish`, pinning the `eta-publish` commit that built them.

The pin is a submodule, git's own way to pin another repository,
rather than a file format of our own, or `uv.lock`:
`uv lock` fetches the commit it pins from GitHub,
which fails for a commit not pushed yet,
and the local hook below pins commits before they're pushed.
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
   A `drafts/` without its `publications.toml` is an error;
   a list with no entries is fine, and builds nothing.
   With no `drafts/` at all, as in this repository's CI, the drafts are skipped.
2. **Preview from the working copy.** `eta-publish drafts preview`
   builds the same way, with all three kinds as [the drafts site shows them](#what-the-drafts-site-shows),
   and uploads the result as a preview of the current commit,
   behind the same sign-in, with no commit or push.
   Its address is `<alias>-<commit>.eta-drafts.pages.dev`,
   with `-dirty` after it when a tracked file has uncommitted edits,
   where the alias is the branch name as Cloudflare writes it:
   lowercased, with anything not a letter or digit turned into `-`,
   and the commit is its first 7 hex digits.
   Not `<alias>.eta-drafts.pages.dev`, which is CI's preview of the branch, on every push:
   the two would overwrite each other.
   Its pages link within that preview, not to production or the public site;
   a drafts `[site]` other than `eta-drafts.pages.dev` with `published/` under it is refused.
   It builds in a directory of its own in `drafts/`, leaving `site/` and `drafts/site/` as they are,
   and uploads every list's `site/unpublished/` at `/` and `site/published/` under `/published/`,
   with no `doc.json`, through `wrangler pages deploy`.
   It uses the local Cloudflare token, which has Pages Edit.
   There is no local deploy to `main`'s site: that's only done from CI.

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
  and fails the commit on a build error, as a broken publication here does now.
- `post-commit` commits the new pin and the rebuilt drafts in `drafts/`,
  on the branch of the same name.

**On push, in CI:** a workflow here tells `eta-drafts` which commits arrived.
For each one, in order, `eta-drafts` makes the matching commit,
unless one naming that code commit is already there (made locally).
The jobs run one at a time and none is cancelled, so no commit is skipped.
This covers commits made where there's no `drafts/`, such as GitHub's web editor.

If both make one for the same code commit, the two are identical,
since the same code rebuilds the same data,
so `git pull --rebase` in `drafts/` drops the local copy.

**Push order:** a drafts commit can only be deployed once
the code commit it pins is on GitHub,
so `eta-publish` is pushed first.
A `pre-push` hook in `drafts/` refuses to push a commit
whose pinned code commit isn't on GitHub yet, and says so.

Pulling new content from the Google Docs stays its own step and its own commit,
made with whatever code is pinned at the time.

## Branches mirror

`eta-publish` development happens on branches,
so each `eta-publish` branch `foo` gets an `eta-drafts` branch `foo`,
holding the drafts commits for `foo`'s code commits,
and deployed to `foo.eta-drafts.pages.dev`.
`main` goes to `eta-drafts`'s `main`, deployed to `eta-drafts.pages.dev`.
Once `foo` is merged, its commits get their drafts commits on `main`,
and `eta-drafts`'s `foo` can be deleted.

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
`site/published/` and `site/unpublished/` from the pinned `eta-publish` commit,
and the drafts from `eta-drafts`, all built by the same code.

- The index lists them in three groups, by kind.
- Every preview page has the label saying which kind it is, as this repository's do.
  It's never in `report.html`, the Markdown or the PDF.

## How the deploy is set up

`eta-drafts`'s deploy workflow checks out the `eta-publish` commit it pins,
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

The token that lets `eta-publish`'s workflow start `eta-drafts`'s exists,
limited to `eta-drafts`.
[`accounts.md`](accounts.md) has both.

## Order of work

1. Teach the tool to build drafts from `drafts/`, and the local build (1 above).
2. `eta-publish drafts preview` (2 above).
3. The deploy workflow in `eta-drafts`, and the three-kind index.
4. The local `pre-commit` and `post-commit` hooks, and the `pre-push` check in `drafts/`.
5. The push-time workflow here, filling in missing drafts commits, with branch mirroring.
