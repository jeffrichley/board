import re
from typing import Any

import pytest

from helpers import (
    NO_SUCH_REPO,
    OPEN_ISSUES,
    REPO_VIEW,
    WORKTREES,
    FakeRun,
    World,
    gh_world,
    invoke,
    porcelain,
    raw_issue,
    tree,
)

# Bare `board` and `board show` are one command reached two ways.
ENTRY_POINTS = pytest.mark.parametrize("args", [[], ["show"]], ids=["bare", "show"])


def plain(text: str) -> str:
    """`text` without its ANSI styling: CI forces colour on, a local run doesn't."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def shown(
    *issues: dict[str, Any],
    worktrees: tuple[int, ...] = (),
    children: dict[int, list[int]] | None = None,
    blockers: dict[int, list[int]] | None = None,
) -> World:
    """What `board show` asks of the world: `gh_world`, and the clone's worktrees,
    with one made by board for each ticket in `worktrees`."""
    listing = porcelain(*(tree(n) for n in worktrees))
    return {
        **gh_world(*issues, children=children, blockers=blockers),
        tuple(WORKTREES): (0, listing, ""),
    }


def section(output: str, heading: str) -> str:
    """The lines under `heading` in a rendered parent, up to the next heading."""
    lines = plain(output).splitlines()
    start = next(i for i, ln in enumerate(lines) if heading in ln)
    rest = lines[start + 1 :]
    headings = ("TAKEABLE", "CLAIMED", "BLOCKED")
    end = next(
        (i for i, ln in enumerate(rest) if any(h in ln for h in headings)), len(rest)
    )
    return "\n".join(rest[:end])


@ENTRY_POINTS
def test_board_renders_empty_board(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = invoke(FakeRun(shown()), monkeypatch, *args)
    assert result.exit_code == 0
    assert "o/r — no open issues" in plain(result.stdout)


def test_bare_board_and_board_show_print_the_same_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = shown(raw_issue(7, "ready-for-agent"), raw_issue(8, "P1"))
    bare = invoke(FakeRun(world), monkeypatch)
    show = invoke(FakeRun(world), monkeypatch, "show")
    assert "issue 7" in show.output
    assert (bare.exit_code, bare.output) == (show.exit_code, show.output)


@ENTRY_POINTS
def test_board_reports_gh_failure_and_exits_nonzero(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = FakeRun({**shown(), tuple(REPO_VIEW): (1, "", "not a git repository")})
    result = invoke(run, monkeypatch, *args)
    assert result.exit_code == 1
    assert "not a git repository" in result.output


def test_board_help_lists_show_as_the_default_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(FakeRun({}), monkeypatch, "--help")
    assert result.exit_code == 0
    marked = [line for line in plain(result.output).splitlines() if "(default)" in line]
    assert len(marked) == 1
    assert marked[0].strip("│| ").startswith("show ")


def test_board_show_help_describes_the_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(FakeRun({}), monkeypatch, "show", "--help")
    assert result.exit_code == 0
    assert "show [OPTIONS]" in result.output
    assert "wayfinding / specs / backlog board" in result.output


@ENTRY_POINTS
def test_board_reports_a_graphql_error_and_exits_nonzero(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    world = {**shown(), tuple(OPEN_ISSUES): NO_SUCH_REPO}
    result = invoke(FakeRun(world), monkeypatch, *args)
    assert result.exit_code == 1
    assert "Could not resolve to a Repository" in result.output


# A spec, #1, with three child tickets: #3 waits on #2, and #4 stands alone.
SPEC = [raw_issue(n) for n in (1, 2, 3, 4)]
CHILDREN = {1: [2, 3, 4]}
BLOCKERS = {3: [2]}


@ENTRY_POINTS
def test_an_unclaimed_ticket_with_a_worktree_shows_as_claimed_not_takeable(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    world = shown(*SPEC, worktrees=(4,), children=CHILDREN, blockers=BLOCKERS)
    result = invoke(FakeRun(world), monkeypatch, *args)
    assert result.exit_code == 0
    assert "#4" not in section(result.output, "TAKEABLE")
    claimed = section(result.output, "CLAIMED")
    assert "#4" in claimed and "has a worktree" in claimed


def test_a_ticket_with_no_worktree_shows_as_takeable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = shown(*SPEC, children=CHILDREN, blockers=BLOCKERS)
    result = invoke(FakeRun(world), monkeypatch, "show")
    takeable = section(result.output, "TAKEABLE")
    assert "#2" in takeable and "#4" in takeable
    assert "CLAIMED" not in plain(result.output)
    assert "has a worktree" not in plain(result.output)


def test_a_blocked_ticket_with_a_worktree_stays_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = shown(*SPEC, worktrees=(3,), children=CHILDREN, blockers=BLOCKERS)
    result = invoke(FakeRun(world), monkeypatch, "show")
    assert "#3" in section(result.output, "BLOCKED")
    assert "CLAIMED" not in plain(result.output)


def test_a_worktree_board_did_not_make_leaves_the_ticket_takeable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = shown(*SPEC, children=CHILDREN, blockers=BLOCKERS)
    world[tuple(WORKTREES)] = (0, porcelain("/elsewhere/4"), "")
    result = invoke(FakeRun(world), monkeypatch, "show")
    assert "#4" in section(result.output, "TAKEABLE")


@ENTRY_POINTS
def test_board_reports_worktrees_it_cannot_list_and_exits_nonzero(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    world = {**shown(), tuple(WORKTREES): (128, "", "fatal: not a git repository")}
    result = invoke(FakeRun(world), monkeypatch, *args)
    assert result.exit_code == 1
    assert "could not list worktrees" in result.output
    assert "not a git repository" in result.output
