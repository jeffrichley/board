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
) -> dict:
    return {
        "number": number,
        "title": title,
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
