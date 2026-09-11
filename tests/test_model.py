from board.model import (
    Backlog,
    Board,
    blocker_chain,
    build_board,
    short,
    unblock_count,
)


def _issue(
    number: int,
    title: str = "t",
    *,
    labels: list[str] | None = None,
    assignee: str | None = None,
    kids_total: int = 0,
    kids_completed: int = 0,
    blocked_by: int = 0,
    body: str | None = None,
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": n} for n in (labels or [])],
        "assignee": {"login": assignee} if assignee else None,
        "sub_issues_summary": {"total": kids_total, "completed": kids_completed},
        "issue_dependencies_summary": {"blocked_by": blocked_by},
    }


def test_short_truncates():
    assert short("hello world", 5) == "hell…"
    assert short("hi", 5) == "hi"


def test_unblock_count_transitive():
    blocks = {1: [2], 2: [3]}
    assert unblock_count(1, blocks) == 2
    assert unblock_count(2, blocks) == 1
    assert unblock_count(3, blocks) == 0


def test_blocker_chain():
    edges = {3: [2], 2: [1]}
    assert blocker_chain(3, edges) == "<- #2 <- #1"


def test_map_with_nested_tickets_not_in_backlog():
    issues = [
        _issue(10, "Map", labels=["wayfinder:map"], kids_total=2, kids_completed=0),
        _issue(11, "Grill", labels=["wayfinder:grilling"]),
        _issue(12, "Blocked grill", labels=["wayfinder:grilling"], blocked_by=1),
        _issue(20, "Debt", labels=["debt", "P1"]),
    ]
    board = build_board(
        "o/r",
        issues,
        children_of={10: [11, 12]},
        blockers_of={12: [11]},
    )
    assert len(board.maps) == 1
    assert board.maps[0].issue.number == 10
    nums = {t.number for t in board.maps[0].group.takeable + board.maps[0].group.claimed + board.maps[0].group.blocked}
    assert nums == {11, 12}
    assert [i.number for i in board.backlog.p1] == [20]
    assert board.backlog.other == []
    assert board.builds == []


def test_build_parent_vs_nested_parent():
    """A parent that is itself a child is not a BUILD root."""
    issues = [
        _issue(1, "Spec", kids_total=2, kids_completed=1),
        _issue(2, "Child parent", kids_total=1, kids_completed=0),
        _issue(3, "Leaf"),
    ]
    board = build_board(
        "o/r",
        issues,
        children_of={1: [2], 2: [3]},
        blockers_of={},
    )
    assert [p.issue.number for p in board.builds] == [1]
    assert {t.number for t in board.builds[0].group.takeable} == {2}
    # #3 is under #2 in GitHub, but v1 only nests one level under BUILD roots:
    # children of nested parents that aren't themselves roots land in backlog
    # unless listed as open children of the root. Keep #3 out of root kids.
    assert 3 not in {t.number for t in board.builds[0].group.takeable}
    assert [i.number for i in board.backlog.other] == [3]


def test_takeable_sorts_by_unblock_then_number():
    issues = [
        _issue(1, "Map", labels=["wayfinder:map"], kids_total=3),
        _issue(2, "A"),
        _issue(3, "B"),
        _issue(4, "C", blocked_by=1),
    ]
    board = build_board(
        "o/r",
        issues,
        children_of={1: [2, 3, 4]},
        blockers_of={4: [2]},
    )
    takeable_nums = [t.number for t in board.maps[0].group.takeable]
    # #2 unblocks #4; #3 unblocks nothing → #2 first
    assert takeable_nums == [2, 3]


def test_claimed_and_orphan_wayfinder_in_backlog():
    issues = [
        _issue(5, "Orphan", labels=["wayfinder:task"]),
        _issue(6, "Mine", assignee="jeff"),
    ]
    board = build_board("o/r", issues, children_of={}, blockers_of={})
    assert board.maps == []
    assert [i.number for i in board.backlog.other] == [5, 6]


def test_map_not_duplicated_under_build_parent():
    """A map listed as a BUILD child appears only as a map root, not in BUILD tickets."""
    issues = [
        _issue(1, "Build", kids_total=2, kids_completed=0),
        _issue(10, "Map", labels=["wayfinder:map"], kids_total=1, kids_completed=0),
        _issue(11, "Map child", labels=["wayfinder:grilling"]),
        _issue(20, "Plain"),
    ]
    board = build_board(
        "o/r",
        issues,
        children_of={1: [10], 10: [11]},
        blockers_of={},
    )
    assert len(board.maps) == 1
    assert board.maps[0].issue.number == 10
    map_ticket_nums = {
        t.number
        for t in board.maps[0].group.takeable
        + board.maps[0].group.claimed
        + board.maps[0].group.blocked
    }
    assert map_ticket_nums == {11}
    assert len(board.builds) == 1
    build_ticket_nums = {
        t.number
        for t in board.builds[0].group.takeable
        + board.builds[0].group.claimed
        + board.builds[0].group.blocked
    }
    assert 10 not in build_ticket_nums
    assert build_ticket_nums == set()
    assert [i.number for i in board.backlog.other] == [20]
    assert 11 not in {i.number for i in board.backlog.p1 + board.backlog.p2_debt + board.backlog.ready + board.backlog.other}


def test_backlog_buckets():
    issues = [
        _issue(1, "p1", labels=["debt", "P1"]),
        _issue(2, "p2", labels=["debt", "P2"]),
        _issue(3, "agent", labels=["ready-for-agent"]),
        _issue(4, "plain"),
    ]
    board = build_board("o/r", issues, children_of={}, blockers_of={})
    assert [i.number for i in board.backlog.p1] == [1]
    assert [i.number for i in board.backlog.p2_debt] == [2]
    assert [i.number for i in board.backlog.ready] == [3]
    assert [i.number for i in board.backlog.other] == [4]


def test_map_note_ready_for_spec_when_frontier_clear():
    issues = [
        _issue(2, "Map", labels=["wayfinder:map"], kids_total=2, kids_completed=2),
    ]
    board = build_board("o/r", issues, children_of={2: []}, blockers_of={})
    assert board.maps[0].note == "frontier clear — ready for /to-spec"


def test_map_note_ready_to_close_when_part_of_spec_exists():
    issues = [
        _issue(2, "Map", labels=["wayfinder:map"], kids_total=2, kids_completed=2),
        _issue(
            29,
            "Spec: characters cannot converge",
            labels=["ready-for-agent"],
            kids_total=1,
            kids_completed=0,
            body="Part of #2\n## Problem Statement\n…",
        ),
        _issue(31, "First ticket", labels=["ready-for-agent"], body="Part of #29"),
    ]
    board = build_board(
        "o/r",
        issues,
        children_of={29: [31]},
        blockers_of={},
    )
    assert board.maps[0].note is not None
    assert board.maps[0].note.startswith("ready to close — open build:")
    assert "#29" in board.maps[0].note
    assert board.maps[0].group.takeable == []
    assert [p.issue.number for p in board.builds] == [29]


def test_map_note_ready_to_close_when_spec_is_sub_issue():
    issues = [
        _issue(2, "Map", labels=["wayfinder:map"], kids_total=3, kids_completed=2),
        _issue(29, "Spec: done planning", kids_total=1, kids_completed=0),
        _issue(31, "Ticket"),
    ]
    board = build_board(
        "o/r",
        issues,
        children_of={2: [29], 29: [31]},
        blockers_of={},
    )
    # #29 is child of map but also a build root — skipped as map ticket
    assert board.maps[0].note is not None
    assert "ready to close" in board.maps[0].note
    assert "#29" in board.maps[0].note

