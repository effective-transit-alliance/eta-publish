"""Upload the drafts site, as built from the working copy, as a preview on Cloudflare Pages.

The drafts site is served by the Pages project `eta-drafts`, behind a sign-in,
and a preview there is a deployment for a branch other than the production one,
served at `<branch>.eta-drafts.pages.dev`.
Each `eta-publish` branch has its preview under its own name,
the branch of `eta-drafts` it mirrors (see `docs/drafts-plan.md`).
What is uploaded, and how it is laid out, is `drafts_site.py`'s.

Uploaded with `wrangler pages deploy`, which Cloudflare's Direct Upload guide names
as the way to upload a folder.
The API it uploads through is in Cloudflare's API reference,
but a deploy through it is several calls: a token, which files are missing by hash,
the files in batches, and a deployment with a manifest of them all,
which is `wrangler` written again here, to be kept in step with it.
Run through `bun x` on demand rather than pinned in `package.json`,
because it brings `workerd`, 160 MB, with it,
and `bun install` would install that for everyone who builds,
and for every run of the Pages workflow, which never uploads to Cloudflare.
"""

import os
import subprocess
from pathlib import Path

from .format import ROOT
from .site import Hosts

PROJECT = "eta-drafts"
"""The Cloudflare Pages project the drafts are served from."""

PRODUCTION_BRANCH = "main"
"""The project's production branch, served at `eta-drafts.pages.dev` itself.

Deployed from CI, from what is committed, never as a preview of a working copy.
"""

PRODUCTION_URL = f"https://{PROJECT}.pages.dev"
"""Where the production branch is served, which the drafts' `[site]` hosts are at."""

ALIAS_LENGTH = 63
"""The most characters in one label of a host name (RFC 1035), so in a branch's alias."""

ACCOUNT_ID = "3b54e32145fe627e6aa1f3d96eb32b4c"
"""The Cloudflare account the project is in.

Named here because the local token cannot list the accounts it can reach,
so `wrangler` cannot find it out. It is in every dashboard URL, and is not a credential.
"""

TOKEN = Path.home() / ".config/eta-publish/cloudflare-token"
"""The local Cloudflare token, which has Pages Edit (see `docs/accounts.md`)."""

WRANGLER = "wrangler@4.166.0"
"""The `wrangler` that uploads, at an exact version, since `bun x` fetches whatever it is told."""


class Refused(Exception):
    """A preview that is not uploaded, and why, said before anything is built."""


def branch() -> str:
    """The branch `eta-publish` is on, which names the preview.

    Not on a branch is refused, since there is no name to give the preview,
    and so is the production branch, since a deploy for it is the drafts site itself.
    """
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    name = result.stdout.strip()
    if result.returncode != 0 or not name:
        raise Refused(
            f"`{ROOT}` is not on a branch, and a preview is named for the branch it previews"
        )
    if name == PRODUCTION_BRANCH:
        raise Refused(
            f"`{name}` is `{PROJECT}`'s production branch, which is deployed from CI,"
            " not previewed; preview from another branch"
        )
    return name


def alias(name: str) -> str:
    """The subdomain Cloudflare Pages serves branch `name`'s preview at.

    Cloudflare's preview deployments page says "Branch name aliases are lowercased
    and non-alphanumeric characters are replaced with a hyphen",
    with `fix/api` becoming `fix-api`.
    It does not say what happens to a name with a non-ASCII letter,
    to a hyphen at either end, or to one too long for a host name's label,
    so those are refused rather than guessed at: a wrong alias is a preview
    whose fragments load from a host that does not exist.
    """
    undocumented = "and what Cloudflare makes of that is not documented"
    if not name.isascii():
        raise Refused(f"`{name}` has a character that is not ASCII, {undocumented}")
    result = "".join(c.lower() if c.isalnum() else "-" for c in name)
    if result.startswith("-") or result.endswith("-"):
        raise Refused(
            f"`{name}` starts or ends with a hyphen, or a character made one, {undocumented}"
        )
    if len(result) > ALIAS_LENGTH:
        raise Refused(f"`{name}` is longer than {ALIAS_LENGTH} characters, {undocumented}")
    return result


def moved(url: str, name: str) -> str:
    """`url`, a place the production site is served, as the branch `name`'s preview serves it.

    The same path on `<alias>.eta-drafts.pages.dev`.
    Anything not at the production host is refused:
    the preview has no assets there, so the fragments would link someone else's.
    """
    if url != PRODUCTION_URL and not url.startswith(f"{PRODUCTION_URL}/"):
        raise Refused(
            f"`{url}` is not at `{PRODUCTION_URL}`,"
            " so a preview cannot tell where its own assets are served"
        )
    return f"https://{alias(name)}.{PROJECT}.pages.dev{url.removeprefix(PRODUCTION_URL)}"


def previewed(hosts: Hosts, name: str) -> Hosts:
    """`hosts`, each moved from the production site to branch `name`'s preview."""
    return Hosts(
        published=moved(hosts.published, name),
        unpublished=moved(hosts.unpublished, name),
    )


def token() -> str:
    """The local Cloudflare token, read once and handed only to `wrangler`."""
    try:
        value = TOKEN.read_text().strip()
    except FileNotFoundError:
        value = ""
    if not value:
        raise Refused(f"no Cloudflare token in `{TOKEN}`; `docs/accounts.md` says which one")
    return value


def upload(directory: Path, branch: str, token: str) -> None:
    """Upload `directory` as the preview for `branch`.

    `wrangler`'s own output is left on the terminal,
    since it says how the upload is going and ends with the preview's address.
    It is run from the repository, so `mise` runs the `bun` that `mise.toml` pins,
    and `wrangler` records the commit the working copy is on and whether it has edits.
    `--bun` runs it on that `bun`, as every npm tool here runs,
    rather than on whichever `node` is on `$PATH`.
    The token is in its environment, never on its command line, where any process can read it.
    """
    environment = {
        **os.environ,
        "CLOUDFLARE_API_TOKEN": token,
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
        "WRANGLER_SEND_METRICS": "false",
    }
    command = [
        "mise",
        "x",
        "--",
        "bun",
        "x",
        "--bun",
        WRANGLER,
        "pages",
        "deploy",
        str(directory.resolve()),
        "--project-name",
        PROJECT,
        "--branch",
        branch,
    ]
    try:
        result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(
            "`mise` is not on PATH, so `wrangler` could not be run. "
            "Install it from https://mise.jdx.dev, then rerun."
        ) from e
    if result.returncode != 0:
        raise RuntimeError(f"`wrangler pages deploy` failed, exit status {result.returncode}")
