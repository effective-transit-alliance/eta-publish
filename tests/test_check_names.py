"""Each check's name: one to a check, written the way a comment shows it."""

import ast
from collections import defaultdict
from pathlib import Path

from eta_publish.check_names import Check

PACKAGE = Path(__file__).parent.parent / "eta_publish"


def _sites() -> dict[Check, set[str]]:
    """Every check a call in the package warns of, with the templates it warns in.

    A template is its source, so an f-string's is the same at every build."""
    found: defaultdict[Check, set[str]] = defaultdict(set)
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            for n, arg in enumerate(node.args):
                if (
                    isinstance(arg, ast.Attribute)
                    and isinstance(arg.value, ast.Name)
                    and arg.value.id == "Check"
                ):
                    found[Check[arg.attr]].add(ast.unparse(node.args[n + 1]))
    return found


def test_each_name_is_kebab_case_and_says_its_member() -> None:
    for check in Check:
        words = check.value.split("-")
        assert all(word and word.isascii() and word.isalnum() for word in words), check
        assert check.value == check.value.lower(), check
        assert check.name == "_".join(words).upper(), check


def test_names_are_unique() -> None:
    assert len({check.value for check in Check}) == len(Check)


def test_every_name_is_warned_somewhere() -> None:
    assert set(_sites()) == set(Check)


def test_two_different_warnings_never_share_a_name() -> None:
    """Shared only by sites saying the same thing, which is the same template."""
    shared = {check: templates for check, templates in _sites().items() if len(templates) > 1}
    assert shared == {}
