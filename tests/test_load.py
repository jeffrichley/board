import json

import pytest

from board.gh import GhClient, GhError
from board.load import load_board
from helpers import (
    IN_REPO,
    NO_SUCH_REPO,
    OPEN_ISSUES,
    REPO_VIEW,
    FakeRun,
    board_query,
    follow_query,
    gh_world,
    issues_page,
    linked,
    raw_issue,
)


def test_load_asks_github_once_for_the_whole_board() -> None:
    run = FakeRun(
        gh_world(
            raw_issue(10, "wayfinder:map"),
            raw_issue(11),
            raw_issue(12),
            raw_issue(20),
            raw_issue(21),
            raw_issue(30, "P1"),
            children={10: [11, 12], 20: [21]},
            blockers={11: [12]},
        )
    )

    board = load_board(GhClient(runner=run))

    assert run.calls == [REPO_VIEW, OPEN_ISSUES]
    assert (board.slug, board.open_count) == ("o/r", 6)
    [the_map] = board.maps
    assert the_map.issue.number == 10
    assert [i.number for i in the_map.group.takeable] == [12]
    assert [i.number for i in the_map.group.blocked] == [11]
    assert the_map.edges == {11: [12]}
    assert [p.issue.number for p in board.specs] == [20]
    assert [i.number for i in board.backlog.p1] == [30]


def test_load_takes_the_first_assignee_as_the_claim() -> None:
    issue = raw_issue(8)
    issue["assignees"]["nodes"] = [{"login": "alice"}, {"login": "bob"}]
    board = load_board(GhClient(runner=FakeRun(gh_world(issue))))

    [claimed] = board.backlog.other
    assert claimed.assignee == "alice"


def test_load_leaves_closed_blockers_undrawn() -> None:
    # #5 and #6 are closed: #8 still has #7, and #9 has nothing left.
    world = gh_world(
        raw_issue(1, "wayfinder:map"),
        *(raw_issue(n) for n in (7, 8, 9)),
        children={1: [7, 8, 9]},
        blockers={8: [5, 7], 9: [6]},
    )
    board = load_board(GhClient(runner=FakeRun(world)))

    [the_map] = board.maps
    assert the_map.edges == {8: [7]}
    assert [i.number for i in the_map.group.blocked] == [8]
    assert [i.number for i in the_map.group.takeable] == [7, 9]
    assert board.open_blockers == {8: [7]}


def test_load_names_the_latest_blocker_first() -> None:
    # GraphQL lists blockers oldest first; the board has always shown them newest first.
    world = gh_world(*(raw_issue(n) for n in (5, 6, 7, 8)), blockers={8: [5, 7, 6]})
    board = load_board(GhClient(runner=FakeRun(world)))

    assert board.open_blockers == {8: [6, 7, 5]}


def test_load_pages_through_more_than_a_hundred_open_issues() -> None:
    run = FakeRun(
        {
            tuple(REPO_VIEW): IN_REPO,
            tuple(board_query()): (0, issues_page(raw_issue(1), after="c1"), ""),
            tuple(board_query("c1")): (0, issues_page(raw_issue(2), after="c2"), ""),
            tuple(board_query("c2")): (0, issues_page(raw_issue(3)), ""),
        }
    )

    board = load_board(GhClient(runner=run))

    assert [i.number for i in board.backlog.other] == [1, 2, 3]
    assert len(run.calls) == 4


def test_load_follows_a_sub_issue_list_longer_than_one_page() -> None:
    parent = raw_issue(10, "wayfinder:map")
    parent["subIssues"] = linked(11, after="k1")
    rest = {"data": {"repository": {"issue": {"subIssues": linked(12)}}}}
    run = FakeRun(
        {
            tuple(REPO_VIEW): IN_REPO,
            tuple(OPEN_ISSUES): (
                0,
                issues_page(parent, raw_issue(11), raw_issue(12)),
                "",
            ),
            tuple(follow_query("subIssues", 10, "k1")): (0, json.dumps(rest), ""),
        }
    )

    board = load_board(GhClient(runner=run))

    [the_map] = board.maps
    assert [i.number for i in the_map.group.takeable] == [11, 12]
    assert len(run.calls) == 3


def test_load_follows_a_blocker_list_longer_than_one_page() -> None:
    blocked = raw_issue(10)
    blocked["blockedBy"] = linked(11, after="k1")
    rest = {"data": {"repository": {"issue": {"blockedBy": linked(12)}}}}
    run = FakeRun(
        {
            tuple(REPO_VIEW): IN_REPO,
            tuple(OPEN_ISSUES): (
                0,
                issues_page(blocked, raw_issue(11), raw_issue(12)),
                "",
            ),
            tuple(follow_query("blockedBy", 10, "k1")): (0, json.dumps(rest), ""),
        }
    )

    board = load_board(GhClient(runner=run))

    assert board.open_blockers == {10: [12, 11]}
    assert len(run.calls) == 3


def test_load_reports_a_graphql_error_in_the_answer() -> None:
    run = FakeRun({tuple(REPO_VIEW): IN_REPO, tuple(OPEN_ISSUES): NO_SUCH_REPO})

    with pytest.raises(GhError, match="Could not resolve to a Repository"):
        load_board(GhClient(runner=run))


def test_load_reports_a_failed_graphql_call_without_the_query() -> None:
    run = FakeRun(
        {tuple(REPO_VIEW): IN_REPO, tuple(OPEN_ISSUES): (1, "", "gh: API rate limit")}
    )

    with pytest.raises(GhError, match="API rate limit") as caught:
        load_board(GhClient(runner=run))
    assert "repository(" not in str(caught.value)
