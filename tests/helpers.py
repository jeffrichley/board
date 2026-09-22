import copy
import json
from typing import Any

import pytest
from typer.testing import CliRunner
from typer.testing import Result as CliResult

from board.cli import app
from board.run import Result

World = dict[tuple[str, ...], tuple[int, str, str]]

SLUG = "o/r"
REPO_VIEW = ["gh", "repo", "view", "--json", "nameWithOwner"]
OPEN_ISSUES = [
    "gh",
    "api",
    f"repos/{SLUG}/issues?state=open&per_page=100",
    "--paginate",
]

FETCH = ["git", "fetch", "origin"]


class FakeRun:
    """A runner that answers only the calls it was given, and records them.

    A key is the whole command, program first: ``("gh", "repo", "view")``,
    ``("tmux", "-V")``. Any other call fails the test.
    """

    def __init__(self, mapping: World):
        self.mapping = mapping
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> Result:
        self.calls.append(args)
        key = tuple(args)
        if key not in self.mapping:
            raise AssertionError(f"unexpected call {args}")
        return Result(*self.mapping[key])


def raw_issue(
    number: int,
    *labels: str,
    assignee: str | None = None,
    kids_total: int = 0,
    blocked_by: int = 0,
) -> dict[str, Any]:
    """An open issue as the `gh` issues API returns it."""
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": [{"name": n} for n in labels],
        "assignee": {"login": assignee} if assignee else None,
        "sub_issues_summary": {"total": kids_total, "completed": 0},
        "issue_dependencies_summary": {"blocked_by": blocked_by},
    }


def gh_world(
    *issues: dict[str, Any],
    children: dict[int, list[int]] | None = None,
    blockers: dict[int, list[int]] | None = None,
) -> World:
    """The `gh` calls `load_board` makes, answered for these open issues.

    Each issue's sub-issue and blocker summaries are set from `children` and
    `blockers`, so the board fetches exactly the lists given here.
    """
    children = children or {}
    blockers = blockers or {}
    issues = copy.deepcopy(issues)
    for raw in issues:
        n = raw["number"]
        raw["sub_issues_summary"]["total"] = len(children.get(n, []))
        raw["issue_dependencies_summary"]["blocked_by"] = len(blockers.get(n, []))
    world: World = {
        tuple(REPO_VIEW): (0, json.dumps({"nameWithOwner": SLUG}), ""),
        tuple(OPEN_ISSUES): (0, json.dumps(list(issues)), ""),
    }
    for n, kids in children.items():
        key = ("gh", "api", f"repos/{SLUG}/issues/{n}/sub_issues?per_page=100")
        world[key] = (0, json.dumps([{"number": k} for k in kids]), "")
    for n, bs in blockers.items():
        key = ("gh", "api", f"repos/{SLUG}/issues/{n}/dependencies/blocked_by")
        world[key] = (0, json.dumps([{"number": b} for b in bs]), "")
    return world


def invoke(run: "FakeRun", monkeypatch: pytest.MonkeyPatch, *args: str) -> CliResult:
    """Run `board *args` with every outside call answered by `run`."""
    monkeypatch.setattr("board.cli.default_runner", run)
    return CliRunner().invoke(app, list(args))
