import copy
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner
from typer.testing import Result as CliResult

from board.cli import app
from board.gh import BOARD_QUERY
from board.run import Result

Answer = tuple[int, str, str]
# A list answers a call that is made more than once, one entry per call in turn.
World = dict[tuple[str, ...], Answer | list[Answer]]

SLUG = "o/r"
REPO_VIEW = ["gh", "repo", "view", "--json", "nameWithOwner"]


def board_query(after: str | None = None) -> list[str]:
    """The one GraphQL call that loads `o/r`'s board, from the page `after`."""
    call = ["gh", "api", "graphql", "-f", f"query={BOARD_QUERY}"]
    call += ["-f", "owner=o", "-f", "name=r"]
    return call + (["-f", f"cursor={after}"] if after else [])


OPEN_ISSUES = board_query()

FETCH = ["git", "fetch", "origin"]


class FakeRun:
    """A runner that answers only the calls it was given, and records them.

    A key is the whole command, program first: ``("gh", "repo", "view")``,
    ``("tmux", "-V")``. Any other call fails the test. A list of answers is
    given out in turn, the last one repeating once the list runs out.
    """

    def __init__(self, mapping: World):
        self.mapping = mapping
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> Result:
        self.calls.append(args)
        key = tuple(args)
        if key not in self.mapping:
            raise AssertionError(f"unexpected call {args}")
        answer = self.mapping[key]
        if isinstance(answer, list):
            asked = sum(tuple(c) == key for c in self.calls) - 1
            answer = answer[min(asked, len(answer) - 1)]
        return Result(*answer)


def tree(number: int | str) -> str:
    """Where board puts ticket `number`'s worktree in the `/repos/board` clone."""
    return str(Path(f"/repos/board.worktrees/{number}"))


def porcelain(*paths: str) -> str:
    """`git worktree list --porcelain` for the `/repos/board` clone and `paths`."""
    main = "worktree /repos/board\nHEAD abc123\nbranch refs/heads/main\n\n"
    rest = "".join(f"worktree {p}\nHEAD abc123\ndetached\n\n" for p in paths)
    return main + rest


def raw_issue(number: int, *labels: str, assignee: str | None = None) -> dict[str, Any]:
    """An open issue as board's GraphQL query returns it, with no sub-issues or
    blockers: `gh_world` gives it those."""
    return {
        "number": number,
        "title": f"issue {number}",
        "body": "",
        "labels": {"nodes": [{"name": n} for n in labels]},
        "assignees": {"nodes": [{"login": assignee}] if assignee else []},
        "subIssuesSummary": {"total": 0, "completed": 0},
        "subIssues": connection(),
        "blockedBy": connection(),
    }


def connection(*nodes: dict[str, Any], after: str | None = None) -> dict[str, Any]:
    """One page of a GraphQL connection, followed by another page `after`."""
    info = {"hasNextPage": after is not None, "endCursor": after}
    return {"pageInfo": info, "nodes": list(nodes)}


def issues_page(*issues: dict[str, Any], after: str | None = None) -> str:
    """One page of the board query's answer, followed by another page `after`."""
    page = connection(*issues, after=after)
    return json.dumps({"data": {"repository": {"issues": page}}})


def gh_world(
    *issues: dict[str, Any],
    children: dict[int, list[int]] | None = None,
    blockers: dict[int, list[int]] | None = None,
) -> World:
    """The `gh` calls `load_board` makes, answered for these open issues.

    Each issue's sub-issues and blockers are set from `children` and `blockers`.
    One that isn't among `issues` is closed, as it would be in a one-repo world.
    Blockers are listed as GitHub's GraphQL lists them: oldest first.
    """
    children = children or {}
    blockers = blockers or {}
    open_nums = {i["number"] for i in issues}

    def linked(nums: list[int]) -> dict[str, Any]:
        states = {n: "OPEN" if n in open_nums else "CLOSED" for n in nums}
        return connection(*({"number": n, "state": s} for n, s in states.items()))

    nodes = copy.deepcopy(issues)
    for node in nodes:
        kids = children.get(node["number"], [])
        node["subIssues"] = linked(kids)
        node["subIssuesSummary"] = {
            "total": len(kids),
            "completed": sum(k not in open_nums for k in kids),
        }
        node["blockedBy"] = linked(blockers.get(node["number"], []))
    return {
        tuple(REPO_VIEW): (0, json.dumps({"nameWithOwner": SLUG}), ""),
        tuple(OPEN_ISSUES): (0, issues_page(*nodes), ""),
    }


def invoke(
    run: "FakeRun",
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    typed: str | None = None,
) -> CliResult:
    """Run `board *args` with every outside call answered by `run`.

    `typed` is what you type at board's prompts, each answer ending in a newline.
    """
    monkeypatch.setattr("board.cli.default_runner", run)
    return CliRunner().invoke(app, list(args), input=typed)
