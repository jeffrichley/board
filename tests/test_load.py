import json

from board.gh import GhClient
from board.load import load_board
from helpers import OPEN_ISSUES, REPO_VIEW, FakeRun, raw_issue


def test_load_fetches_children_and_blockers_only_where_reported() -> None:
    issues = [
        raw_issue(10, "wayfinder:map"),
        raw_issue(11, blocked_by=1),
        raw_issue(12),
        raw_issue(20, kids_total=1),
        raw_issue(21),
    ]
    run = FakeRun(
        {
            tuple(REPO_VIEW): (
                0,
                json.dumps({"nameWithOwner": "o/r"}),
                "",
            ),
            tuple(OPEN_ISSUES): (0, json.dumps(issues), ""),
            ("gh", "api", "repos/o/r/issues/10/sub_issues?per_page=100"): (
                0,
                json.dumps([{"number": 11}, {"number": 12}]),
                "",
            ),
            ("gh", "api", "repos/o/r/issues/20/sub_issues?per_page=100"): (
                0,
                json.dumps([{"number": 21}]),
                "",
            ),
            ("gh", "api", "repos/o/r/issues/11/dependencies/blocked_by"): (
                0,
                json.dumps([{"number": 12}]),
                "",
            ),
        }
    )

    board = load_board(GhClient(runner=run))

    assert board.slug == "o/r"
    assert board.open_count == 5
    [the_map] = board.maps
    assert the_map.issue.number == 10
    assert [i.number for i in the_map.group.takeable] == [12]
    assert [i.number for i in the_map.group.blocked] == [11]
    assert the_map.edges == {11: [12]}
    assert [p.issue.number for p in board.specs] == [20]
    assert len(run.calls) == 5  # nothing fetched for 12 or 21
