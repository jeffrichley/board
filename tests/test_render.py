import dataclasses

import pytest
from rich.console import Console

from board.model import Backlog, Board, Issue, Lane, ParentNode, TicketGroup
from board.render import render_board


def _issue(n: int, title: str, *labels: str, assignee: str | None = None) -> Issue:
    return Issue(n, title, labels, assignee, 0, 0, 0)


def test_render_includes_lanes_and_colors() -> None:
    board = Board(
        slug="o/r",
        open_count=3,
        maps=[
            ParentNode(
                issue=Issue(10, "The Map", ("wayfinder:map",), None, 0, 1, 0),
                group=TicketGroup(
                    takeable=[_issue(11, "Do thing", "wayfinder:grilling")],
                    claimed=[],
                    blocked=[_issue(12, "Wait", "wayfinder:grilling")],
                ),
                edges={12: [11]},
                blocks={11: [12]},
            )
        ],
        specs=[],
        backlog=Backlog(p1=[_issue(20, "Fix", "debt", "P1")]),
    )
    console = Console(record=True, width=120, force_terminal=True)
    render_board(board, console=console)
    text = console.export_text(clear=False)
    assert "WAYFINDING" in text
    assert "#10" in text and "The Map" in text
    assert "TAKEABLE" in text and "#11" in text
    assert "BLOCKED" in text and "#12" in text
    assert "<- #11" in text
    assert "<- #11 <-" not in text  # no transitive tail
    assert "BACKLOG" in text and "P1" in text and "#20" in text
    html = console.export_html(clear=False)
    assert "WAYFINDING" in html


def _render(board: Board) -> str:
    console = Console(record=True, width=120, force_terminal=True)
    render_board(board, console=console)
    return console.export_text(clear=False)


def test_spec_lane_shows_note_claimed_and_what_takeable_unblocks() -> None:
    board = Board(
        slug="o/r",
        open_count=4,
        maps=[],
        specs=[
            ParentNode(
                issue=Issue(30, "The Spec", (), None, 1, 4, 0),
                group=TicketGroup(
                    takeable=[_issue(31, "Start", "ready-for-agent")],
                    claimed=[_issue(32, "Mine", assignee="jeff")],
                    blocked=[_issue(33, "Later")],
                ),
                edges={33: [31]},
                blocks={31: [33]},
                note="frontier clear",
            )
        ],
        backlog=Backlog(),
    )
    text = _render(board)
    assert "SPECS" in text and "#30" in text and "1/4 done" in text
    assert "frontier clear" in text
    assert "ready-for-agent" in text and "unblocks 1" in text
    assert "CLAIMED" in text and "#32" in text and "@jeff" in text
    assert "BACKLOG" not in text


def test_backlog_shows_each_group_it_holds() -> None:
    board = Board(
        slug="o/r",
        open_count=5,
        maps=[],
        specs=[],
        backlog=Backlog(
            p1=[_issue(1, "Urgent", "P1")],
            p2_debt=[_issue(2, "Cleanup", "debt")],
            ready=[_issue(3, "Go", "ready-for-agent")],
            orphan_wayfinder=[_issue(4, "Lost", "wayfinder:grilling")],
            other=[_issue(5, "Misc")],
        ),
    )
    text = _render(board)
    for heading in ("P1", "P2 / debt", "ready-for-agent", "orphan wayfinder", "other"):
        assert heading in text
    for n in range(1, 6):
        assert f"#{n}  " in text
    assert "wayfinder:grilling" in text


BACKLOG_GROUPS = [f.name for f in dataclasses.fields(Backlog)]


def _rendered_backlog_line(group: str, issue: Issue) -> str:
    board = Board(
        slug="o/r",
        open_count=1,
        maps=[],
        specs=[],
        backlog=Backlog(**{group: [issue]}),
    )
    console = Console(record=True, width=120, force_terminal=True)
    render_board(board, console=console)
    ansi = console.export_text(clear=False, styles=True)
    return next(ln for ln in ansi.splitlines() if f"#{issue.number}" in ln)


@pytest.mark.parametrize("group", BACKLOG_GROUPS)
def test_backlog_claimed_ticket_is_yellow_with_assignee(group: str) -> None:
    line = _rendered_backlog_line(group, _issue(120, "Taken", "P1", assignee="jeff"))
    assert "@jeff" in line
    assert "\x1b[33m#120" in line  # yellow number, as under a map


@pytest.mark.parametrize("group", BACKLOG_GROUPS)
def test_backlog_unclaimed_ticket_renders_plain(group: str) -> None:
    line = _rendered_backlog_line(group, _issue(121, "Free", "P1"))
    assert "@" not in line
    assert "\x1b[33m" not in line


def _one_of_each_lane() -> Board:
    """A board with one map of two tickets, one spec of one, and two in backlog."""
    return Board(
        slug="o/r",
        open_count=7,
        maps=[
            ParentNode(
                issue=_issue(10, "The Map", "wayfinder:map"),
                group=TicketGroup(takeable=[_issue(11, "Decide")]),
                edges={},
                blocks={},
            )
        ],
        specs=[
            ParentNode(
                issue=_issue(30, "The Spec"),
                group=TicketGroup(claimed=[_issue(31, "Build", assignee="jeff")]),
                edges={},
                blocks={},
            )
        ],
        backlog=Backlog(p1=[_issue(1, "Urgent", "P1")], other=[_issue(2, "Misc")]),
    )


def test_an_unfiltered_board_counts_only_what_is_open() -> None:
    text = _render(_one_of_each_lane())
    assert "o/r — 7 open\n" in text
    assert " of " not in text


def test_a_lane_filter_shows_only_that_lane_and_counts_it_against_the_repo() -> None:
    text = _render(_one_of_each_lane().only([Lane.BACKLOG]))
    assert "o/r — 2 of 7 open (backlog)" in text
    assert "BACKLOG" in text and "#1  " in text
    assert "WAYFINDING" not in text and "SPECS" not in text


def test_lanes_render_in_board_order_and_count_their_parents() -> None:
    text = _render(_one_of_each_lane().only([Lane.SPECS, Lane.WAYFINDING]))
    assert "o/r — 4 of 7 open (wayfinding, specs)" in text
    assert text.index("WAYFINDING") < text.index("SPECS")
    assert "BACKLOG" not in text


def test_every_lane_is_no_filter_at_all() -> None:
    board = _one_of_each_lane()
    assert _render(board.only(list(Lane))) == _render(board)


def test_a_filter_that_matches_nothing_still_prints_its_header() -> None:
    board = _one_of_each_lane()
    board.specs = []
    assert _render(board.only([Lane.SPECS])).strip() == "o/r — 0 of 7 open (specs)"


def test_a_repo_with_no_open_issues_says_so_whatever_the_filter() -> None:
    board = Board(slug="o/r", open_count=0, maps=[], specs=[], backlog=Backlog())
    assert _render(board.only([Lane.SPECS])).strip() == "o/r — no open issues"
