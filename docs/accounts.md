# Accounts, services and credentials

Everything `eta-publish` and `eta-drafts` depend on outside this repository:
which accounts exist, what each one holds, and where every credential lives.
State as of 2026-11-21.

No secret is written here, only where it is kept.
This repository is public,
so anything added here has to be safe to publish.

## Overview

| Service | Account | What it's for |
| --- | --- | --- |
| GitHub | organization `effective-transit-alliance` | the code (`eta-publish`, public), the drafts (`eta-drafts`, private), and the public site on GitHub Pages |
| Google Workspace and Google Cloud | `etany.org` | reading the Google Docs, and Google sign-in for the drafts site |
| Cloudflare | "Effective Transit Alliance", signed in with Google as `khybersen@etany.org` | hosting the drafts site (Pages), and the sign-in in front of it (Zero Trust Access) |
| Squarespace | `etany.org` | the public ETA website, where publications are pasted in |
| Internet Archive (optional) | an archive.org account | asking for new Wayback Machine captures of cited sources |

## GitHub

### `effective-transit-alliance/eta-publish` (public)

The code, the tests, and the publications built here
(`site/published/` and `site/unpublished/`).

- **GitHub Pages:** built by `.github/workflows/pages.yml` on every push to `main`
  and served at <https://effective-transit-alliance.github.io/eta-publish/>.
  [Publishing to GitHub Pages](../README.md#publishing-to-github-pages) has the setup.
- **No Google key:** the Pages build reads the documents as `eta-publish-ci`
  by signing in with Workload Identity Federation,
  through the `eta-publish` provider (see [Google](#google)),
  which accepts only runs in the `github-pages` environment.
- **Variable `DRAFTS_CI_DISPATCH_CLIENT_ID` and secret `DRAFTS_CI_DISPATCH_APP_KEY`,** on the repository:
  the client ID and private key of the App `eta-drafts-ci-dispatch` (see [GitHub Apps](#github-apps)),
  for `.github/workflows/drafts.yml` to start `eta-drafts`'s sync on every push,
  and to read which branch `eta-drafts`'s runs were for, on the commits a force-push drops
  (see [`drafts.md`](drafts.md)).

### `effective-transit-alliance/eta-drafts` (private)

Holds drafts that aren't public yet: none so far,
only an empty `publications.toml`, the pin of `eta-publish`,
and the workflows that make the drafts commits and deploy them,
`.github/workflows/sync.yml` and `.github/workflows/deploy.yml`,
with `.github/workflows/sweep.yml` and `.github/workflows/reconcile.yml` settling the commit statuses they leave.
[`drafts.md`](drafts.md) describes how the drafts work.

- **Secret `CLOUDFLARE_API_TOKEN`:** the Cloudflare token `eta-drafts GitHub Actions`
  (see [Tokens](#tokens)).
- **Secret `CLOUDFLARE_ACCOUNT_ID`:** the Cloudflare account's ID.
  It's not really a secret (it's in every dashboard URL), but it's kept with the token.
- **No Google key:** deploys read the drafts' documents as `eta-publish-ci`
  by signing in with Workload Identity Federation,
  through the `eta-drafts` provider (see [Google](#google)),
  so there's no secret to set.
- **Variable `DRAFTS_CI_STATUS_CLIENT_ID` and secret `DRAFTS_CI_STATUS_APP_KEY`:**
  the client ID and private key of the App `eta-drafts-ci-status` (see [GitHub Apps](#github-apps)),
  for `sync.yml`, `deploy.yml`, and `sweep.yml` to show how they're going on `eta-publish`'s commits,
  as commit statuses (see [`drafts.md`](drafts.md#what-eta-publishs-commits-show)).

### GitHub Apps

A workflow in one repository acts on the other through a GitHub App,
owned by the organization and installed on that other repository only.
The workflow makes a token from the App's client ID and private key
with `actions/create-github-app-token`,
asking for just the permission it uses, on just that repository.
The token lasts an hour at most, and is revoked when the job ends.

| App | Installed on | Permissions | Used by | Client ID and key |
| --- | --- | --- | --- | --- |
| `eta-drafts-ci-dispatch` | `eta-drafts` | Actions: Read and write | `eta-publish`'s `drafts.yml`, to start `eta-drafts`'s sync, and to read which branch its runs were for | variable `DRAFTS_CI_DISPATCH_CLIENT_ID` and secret `DRAFTS_CI_DISPATCH_APP_KEY` in `eta-publish` |
| `eta-drafts-ci-status` | `eta-publish` | Commit statuses: Read and write | `eta-drafts`'s `sync.yml`, `deploy.yml`, and `sweep.yml`, to read and set commit statuses on `eta-publish`'s commits | variable `DRAFTS_CI_STATUS_CLIENT_ID` and secret `DRAFTS_CI_STATUS_APP_KEY` in `eta-drafts` |

Every App can also read its repositories' metadata (Metadata: Read), as GitHub requires.
The client ID isn't a secret, so it's a variable, shown in the repository's settings.
The private key doesn't expire.
A copy of each App's key is in `~/.config/eta-publish/` (see [Local files](#local-files)),
for making a new token, or setting the secret again.

- **Manage them:** <https://github.com/organizations/effective-transit-alliance/settings/apps>,
  where each App's page has its permissions, client ID, and private keys.
  A new key is made there, and an old one deleted once its secret is replaced.
- **Installations:** <https://github.com/organizations/effective-transit-alliance/settings/installations>,
  where each App's repositories are chosen.

## Google

### Workspace and Cloud organization

`etany.org` is a Google Workspace, with a Google Cloud organization of the same name.

### Cloud project `eta-publish` ("ETA Publish")

- **Where:** inside the `etany.org` organization, moved there on 2026-11-02.
- **Owners:** `khybersen@etany.org`, and Khyber's personal Google account,
  which created the project before it moved.
- **APIs used:** Google Docs and Google Drive,
  and IAM, IAM Service Account Credentials and Security Token Service for Workload Identity Federation.
  The others enabled (BigQuery, Cloud Storage, logging and so on) are Google's defaults.
- **No service account keys:** the organization's policy forbids creating them,
  so CI signs in only with Workload Identity Federation.
- **Sign-in audience (Google Auth Platform → Audience):** **Internal**,
  so only `etany.org` accounts can sign in through its OAuth clients,
  Google never reviews the app, and sign-ins don't expire weekly the way they do in Testing.
  Setting: <https://console.cloud.google.com/auth/audience?project=eta-publish>.

It holds three credentials:

| Name | Type | Used by | Where the secret is |
| --- | --- | --- | --- |
| (desktop client) | OAuth client, **Desktop app** | `eta-publish` run locally, to read the Docs as you | `~/.config/eta-publish/client_secret.json`; the sign-in it produces is cached in `~/.config/eta-publish/token.json` |
| `Cloudflare Access (eta-ny)` | OAuth client, **Web application** | Cloudflare Access, for "Sign in with Google" on the drafts site | `~/.config/eta-publish/cloudflare-google-oauth.json`, and inside Cloudflare's identity provider settings |
| `eta-publish-ci@eta-publish.iam.gserviceaccount.com` | service account | GitHub Actions, to read the Docs without a person | none: both repositories sign in with Workload Identity Federation |

The web client allows only:

- JavaScript origin `https://eta-ny.cloudflareaccess.com`
- redirect URI `https://eta-ny.cloudflareaccess.com/cdn-cgi/access/callback`

Both follow the Zero Trust team domain:
renaming the team domain means updating them here too.

The service account has no IAM roles.
It reads a document only because the document,
or a folder it's in, is shared with it as a Viewer.

Clients: <https://console.cloud.google.com/auth/clients?project=eta-publish>.

### Workload Identity Federation

Lets a GitHub Actions run act as `eta-publish-ci` without a key:
the run trades the token GitHub signs for it for short-lived Google credentials.

- **Pool `github-actions`** ("GitHub Actions"), with one provider per repository.
  Each provider trusts tokens from `https://token.actions.githubusercontent.com`,
  and accepts only those its condition allows:
  - **`eta-drafts`:** `assertion.repository=='effective-transit-alliance/eta-drafts'`.
    Its sync and deploy run on every branch, for the previews, so it isn't limited further.
  - **`eta-publish`:** `assertion.repository=='effective-transit-alliance/eta-publish' && assertion.environment=='github-pages'`,
    and that environment admits only `main`.
    The Pages workflow's build job signs in through it.
- **Grant:** each repository's runs have `roles/iam.workloadIdentityUser` on `eta-publish-ci`,
  as `principalSet://iam.googleapis.com/projects/635412927675/locations/global/workloadIdentityPools/github-actions/attribute.repository/effective-transit-alliance/<repository>`.
- **Revoke:** disabling a provider stops its repository's sign-ins at once.

`khybersen@etany.org` has `roles/iam.serviceAccountTokenCreator` on `eta-publish-ci`,
so a local run can act as it, with no key, through `gcloud`:
`gcloud auth print-access-token --impersonate-service-account=eta-publish-ci@eta-publish.iam.gserviceaccount.com --scopes=<scopes>`.

Pools: <https://console.cloud.google.com/iam-admin/workload-identity-pools?project=eta-publish>.

## Cloudflare

One account, "Effective Transit Alliance",
created by signing in with Google as `khybersen@etany.org`.
Its ID is in `eta-drafts`'s `CLOUDFLARE_ACCOUNT_ID` secret and in every dashboard URL.

### Zero Trust organization

- **Name:** "Effective Transit Alliance".
- **Team domain:** `eta-ny.cloudflareaccess.com`, renamed from `effective-transit-alliance` on 2026-11-20.
  The organization can't be deleted, only renamed,
  and renaming it breaks the Google web client above until its URIs are updated.
- **Sign-in methods (identity providers):**
  - **Google (`etany.org`),** type Google Workspace, limited to the `etany.org` domain,
    using the `Cloudflare Access (eta-ny)` client.
  - **Email one-time PIN:** a code sent by email, for anyone outside `etany.org`.
- **Reusable policy "ETA viewers":** allows any `@etany.org` email.
  No outside addresses yet; add them to this policy.

### Pages project `eta-drafts`

- **Address:** <https://eta-drafts.pages.dev>, with previews at `<alias>.eta-drafts.pages.dev`,
  the alias being the branch name lowercased, with anything not a letter or digit turned into `-`,
  and local ones at `<alias>-<commit>.eta-drafts.pages.dev`.
  Pages projects can't be renamed, so neither can these addresses.
- **Direct upload,** not connected to Git: CI builds the site and uploads it on every push,
  with `eta-publish drafts deploy`,
  and `eta-publish drafts preview` uploads a commit's preview from a local machine.
- **Production branch:** `main`.
- Nothing deployed to production yet, so after signing in the main site shows "Connection timed out".
  One test preview, of the branch `drafts-preview`, is up and empty.

### Access application `eta-drafts`

- **Covers:** `eta-drafts.pages.dev` and `*.eta-drafts.pages.dev`,
  so the main site and every preview require sign-in.
- **Policy:** "ETA viewers".
- **Sign-in methods:** both of the above.
- **Session length:** 1 month (730 hours).
  Someone removed from the policy keeps access until their session ends,
  unless sessions are revoked.

### Custom domain

None. A name like `drafts.etany.org` could only be protected by Access
if `etany.org`'s DNS were on Cloudflare; it's on Squarespace's (NS1).
Without that, a custom domain would be public even with the `pages.dev` addresses locked.

## Tokens

Both tokens have no expiration: they work until deleted.

| Token | Kind | Permissions | Used by | Where it is |
| --- | --- | --- | --- | --- |
| `eta-drafts setup (claude)` | user token, owned by `khybersen@etany.org` | Account: Cloudflare Pages Edit; Access: Apps and Policies Edit; Access: Organizations, Identity Providers, and Groups Edit | setting up and changing Cloudflare from a local machine, by Claude Code, and the uploads of `eta-publish drafts preview` | `~/.config/eta-publish/cloudflare-token` |
| `eta-drafts GitHub Actions` | account token | Cloudflare Pages Edit, entire account | deploying the drafts site from CI | `~/.config/eta-publish/cloudflare-ci-token`, and `CLOUDFLARE_API_TOKEN` in `eta-drafts` |

- **Why two Cloudflare tokens:** the setup token can change who may view drafts and how they sign in.
  Keeping it off CI means a leak from CI can only touch Pages.
  An account token's Access calls return nothing,
  so the CI token can't even read who may view drafts.
- **Not included:** changing the account itself (its name, members, billing),
  which needs Account Settings permission. Do that in the dashboard.
- **Manage them:** Cloudflare user tokens at <https://dash.cloudflare.com/profile/api-tokens>,
  and account tokens under **Manage account → Account API tokens**.
  A token's permissions can be changed there without making a new one.
- **Check one works,** without printing it:

  ```sh
  curl -sS -H "Authorization: Bearer $(cat ~/.config/eta-publish/cloudflare-token)" \
    https://api.cloudflare.com/client/v4/user/tokens/verify | jq .result.status
  ```

  An account token is checked at `/accounts/<account id>/tokens/verify` instead.

## Local files

Everything secret on a working machine is in `~/.config/eta-publish/`,
each file readable only by its owner (`chmod 600`).

| File | What it is |
| --- | --- |
| `client_secret.json` | Google desktop OAuth client |
| `token.json` | the cached Google sign-in it produced |
| `cloudflare-google-oauth.json` | Google web OAuth client, for Cloudflare's Google sign-in |
| `cloudflare-token` | Cloudflare user token `eta-drafts setup (claude)` |
| `cloudflare-ci-token` | Cloudflare account token `eta-drafts GitHub Actions` |
| `github-app-eta-drafts-ci-dispatch.pem` | private key of the GitHub App `eta-drafts-ci-dispatch` |
| `github-app-eta-drafts-ci-dispatch.json` | that App's ID, client ID, owner, and permissions |
| `github-app-eta-drafts-ci-status.pem` | private key of the GitHub App `eta-drafts-ci-status` |
| `github-app-eta-drafts-ci-status.json` | that App's ID, client ID, owner, and permissions |

To save a new token without it appearing on screen or in shell history,
and without overwriting a file that's already there:

```sh
(set -o noclobber; umask 077; read -rsp 'Token: ' t && printf '%s\n' "$t" > ~/.config/eta-publish/<file>)
```

A token is shown only once, so overwriting its file loses it for good;
the only way back is to roll the token for a new value.

## Squarespace

`etany.org` is a Squarespace 7.1 site, and its DNS is hosted there too.
Publications are pasted into it as code blocks;
[Squarespace constraints](../README.md#squarespace-constraints) explains the limits that shape the output.

## Internet Archive

Optional. Keys for an archive.org account in `$SPN2_ACCESS_KEY` and `$SPN2_SECRET_KEY`,
or `ia configure`'s `ia.ini`, make new Wayback Machine captures less rate-limited;
see [Archiving new sources](../README.md#archiving-new-sources-optional).
