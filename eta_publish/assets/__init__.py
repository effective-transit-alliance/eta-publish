"""The files a build ships and emits as they are.

A stylesheet, a script, and the Typst template: none of them is Python,
and each was easier to write, read, and edit as itself than as a string
inside a module. An editor knows what a `.css` file is;
it knows a triple-quoted string is a string.

Read through `importlib.resources` rather than by path,
because a wheel is not a directory:
these have to come out of wherever the package was installed to,
which is not somewhere any code here can name.
"""

from importlib import resources


def read(name: str) -> str:
    """The asset called `name`, verbatim.

    No caching. A build reads each of these once,
    and a cache would be a thing to invalidate for no time saved.
    """
    return resources.files(__name__).joinpath(name).read_text(encoding="utf-8")
