from functools import cache
from importlib.metadata import metadata

PACKAGE_NAME = __name__.replace("_", "-")
"""`eta_publish` spelled the way the distribution and the command are.

Derived rather than read back with `importlib.metadata.packages_distributions`,
which knows nothing of an editable install, which is how this is run.
"""


@cache
def repository() -> str:
    """Where this code lives, as `pyproject.toml`'s `[project.urls] Repository` says.

    Read from the installed metadata rather than written here,
    so moving the repository is that one line.
    """
    for entry in metadata(PACKAGE_NAME).get_all("Project-URL") or []:
        label, _, url = entry.partition(", ")
        if label == "Repository":
            return url
    raise LookupError(f"`pyproject.toml` names no `Repository` for {PACKAGE_NAME}")
