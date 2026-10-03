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


def test_board_show_takes_lanes_in_any_case_and_order_and_once_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = shown(raw_issue(7, "ready-for-agent"), raw_issue(8, "P1"))
    named = invoke(
        FakeRun(world), monkeypatch, "show", "backlog", "WAYFINDING", "Backlog"
    )
    assert named.exit_code == 0
    assert "o/r — 2 of 2 open (wayfinding, backlog)" in plain(named.stdout)
    assert "issue 7" in named.stdout


def test_board_show_with_no_lanes_shows_the_whole_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(FakeRun(shown(raw_issue(7))), monkeypatch, "show")
    assert "o/r — 1 open" in plain(result.stdout)


def test_board_show_refuses_an_unknown_lane_before_fetching_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({})
    result = invoke(run, monkeypatch, "show", "backlog", "todo")
    assert result.exit_code == 2
    assert run.calls == []
    message = plain(result.output)
    assert "todo" in message
    for lane in ("wayfinding", "specs", "backlog"):
        assert lane in message


def test_bare_board_takes_no_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun({})
    result = invoke(run, monkeypatch, "backlog")
    assert result.exit_code == 2
    assert run.calls == []


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


# Something of every kind in every lane. Takeable: #11 under map #10, #31 under
# spec #30, and #1 and #6 in the backlog. Everything else is taken, blocked, a map
# or spec with nothing takeable, or (#5) a wayfinder ticket with no map to work it.
EVERY_KIND = [
    *(raw_issue(n, "wayfinder:map") for n in (10, 20, 50)),
    raw_issue(11),
    raw_issue(12, assignee="jeff"),
    raw_issue(13),
    raw_issue(21, assignee="jeff"),
    *(raw_issue(n) for n in (30, 31, 32, 40, 41)),
    raw_issue(1, "P1"),
    raw_issue(2, "P1", assignee="jeff"),
    raw_issue(3),
    raw_issue(4, "ready-for-agent"),
    raw_issue(5, "wayfinder:decision"),
    raw_issue(6, "P2"),
]
EVERY_KIND_WORLD = shown(
    *EVERY_KIND,
    worktrees=(4, 32),
    children={10: [11, 12, 13], 20: [21], 30: [31, 32], 40: [41]},
    blockers={13: [11], 41: [1], 3: [1]},
)


def numbers(output: str) -> set[int]:
    """Every ticket number a rendered board lists, headings among them."""
    return {int(n) for n in re.findall(r"#(\d+)  ", plain(output))}


@pytest.mark.parametrize("flag", ["--takeable", "-t"])
def test_takeable_shows_only_takeable_tickets_under_the_parents_that_hold_them(
    flag: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = invoke(FakeRun(EVERY_KIND_WORLD), monkeypatch, "show", flag)
    assert result.exit_code == 0
    assert numbers(result.output) == {10, 11, 30, 31, 1, 6}
    text = plain(result.output)
    assert "o/r — 6 of 18 open (takeable)" in text
    for gone in ("CLAIMED", "BLOCKED", "frontier clear", "ready-for-agent"):
        assert gone not in text
    assert "orphan wayfinder" not in text


def test_bare_board_takeable_is_board_show_takeable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bare = invoke(FakeRun(EVERY_KIND_WORLD), monkeypatch, "-t")
    show = invoke(FakeRun(EVERY_KIND_WORLD), monkeypatch, "show", "-t")
    assert "issue 31" in show.output
    assert (bare.exit_code, bare.output) == (show.exit_code, show.output)


def test_takeable_with_lanes_narrows_by_both_and_names_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(FakeRun(EVERY_KIND_WORLD), monkeypatch, "show", "-t", "backlog")
    assert result.exit_code == 0
    assert numbers(result.output) == {1, 6}
    assert "o/r — 2 of 18 open (backlog, takeable)" in plain(result.output)


def test_takeable_before_a_command_is_refused_before_fetching_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({})
    result = invoke(run, monkeypatch, "-t", "show")
    assert result.exit_code == 2
    assert run.calls == []
    assert "board show -t" in plain(result.output)
