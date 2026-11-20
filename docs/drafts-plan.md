# Plan: private drafts in `eta-drafts`

Decided 2026-11-20; none of it is built yet.
[`accounts.md`](accounts.md) has the accounts and credentials it uses,
which already exist.

## Goal

New publications have to be drafted somewhere private,
while the code stays open source in this public repository.
The code changes often, mostly to make new drafts look right once published,
so every code change has to be easy to see in every draft,
locally and deployed, before and after it lands.

## The three kinds of publication

| Kind | Label on the drafts site | Where it lives | Public? |
| --- | --- | --- | --- |
| Published by the tool | **Published** | `eta-publish`, `site/published/` | yes |
| Published by hand, not yet moved to the tool | **Manually Published** | `eta-publish`, `site/unpublished/` | yes |
| Not published anywhere yet | **Draft** | `eta-drafts` | no |

A manually published report moves from `site/unpublished/` to `site/published/`
once its publishing is switched to the tool, in one commit here.
When a draft is published, it moves from `eta-drafts` into this repository.

The drafts already in this repository's history stay there:
they've all been published since.

## Repositories

- **`eta-publish` (public):** the code, the tests, `site/published/`, `site/unpublished/`,
  and their entries in `publications.toml`. Unchanged apart from what's below.
- **`eta-drafts` (private):** the drafts' entries in a `publications.toml` of its own,
  their built output with the saved Google Docs data it's rebuilt from,
  and a file such as `eta-publish.rev` naming the `eta-publish` commit that built them.

The pin is a plain file rather than `uv.lock`
because `uv lock` fetches the commit it pins from GitHub,
which fails for a commit not pushed yet,
and the local hook below pins commits before they're pushed.

## Working locally

`eta-drafts` is cloned inside the `eta-publish` checkout as `drafts/`,
which `eta-publish` ignores. It's a separate repository with its own commits.

1. **Build with the working copy.** `uv run eta-publish all` builds `drafts/` too,
   with whatever code is in the working copy, uncommitted edits included.
   The tool needs to learn to find the drafts' list and output under `drafts/`.
2. **Deploy from the working copy.** A command (name to be decided)
   builds the same way and uploads the result as a preview to
   `<branch>.eta-drafts.pages.dev`, behind the same sign-in,
   with no commit or push. It uses the local Cloudflare token, which has Pages Edit.

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
both from CI and with the local deploy command:
it fetches the live documents, images included,
so a deploy shows the documents as they are now, not as of the commit.
The drafts commits above still rebuild from the saved data,
since what they record is the committed text, which needs no images.

## What the drafts site shows

`eta-drafts.pages.dev`, and every branch preview, shows all three kinds:
`site/published/` and `site/unpublished/` from the pinned `eta-publish` commit,
and the drafts from `eta-drafts`, all built by the same code.

- The index lists them in three groups, by kind.
- Every page has a banner saying which kind it is.
  The banner is only added for the drafts site, never to the real published output.

## Still to set up

- A GitHub token, or a GitHub App, that lets `eta-publish`'s workflow trigger `eta-drafts`'s,
  limited to `eta-drafts`. Someone with admin rights on the organization makes it.
- `GOOGLE_CREDENTIALS` in `eta-drafts`, for deploys to fetch the documents:
  the same `eta-publish-ci` service account key as in `eta-publish`,
  with each draft, or its folder, shared with that account as a Viewer.

## Order of work

1. Teach the tool to build drafts from `drafts/`, and the local build (1 above).
2. The local deploy command (2 above).
3. The deploy workflow in `eta-drafts`, and the three-kind index and banners.
4. The local `pre-commit` and `post-commit` hooks, and the `pre-push` check in `drafts/`.
5. The push-time workflow here, filling in missing drafts commits, with branch mirroring.
