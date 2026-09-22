import json
from typing import Any

from board.gh import GhClient
from board.load import load_board
from helpers import FakeRun

ISSUES = "repos/o/r/issues?state=open&per_page=100"


def _raw(
    number: int,
    *labels: str,
    kids_total: int = 0,
    blocked_by: int = 0,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": [{"name": n} for n in labels],
        "assignee": None,
        "sub_issues_summary": {"total": kids_total, "completed": 0},
        "issue_dependencies_summary": {"blocked_by": blocked_by},
    }


def test_load_fetches_children_and_blockers_only_where_reported() -> None:
    issues = [
        _raw(10, "wayfinder:map"),
        _raw(11, blocked_by=1),
        _raw(12),
        _raw(20, kids_total=1),
        _raw(21),
    ]
    run = FakeRun(
        {
            ("repo", "view", "--json", "nameWithOwner"): (
                0,
                json.dumps({"nameWithOwner": "o/r"}),
                "",
            ),
            ("api", ISSUES, "--paginate"): (0, json.dumps(issues), ""),
            ("api", "repos/o/r/issues/10/sub_issues?per_page=100"): (
                0,
                json.dumps([{"number": 11}, {"number": 12}]),
                "",
            ),
            ("api", "repos/o/r/issues/20/sub_issues?per_page=100"): (
                0,
                json.dumps([{"number": 21}]),
                "",
            ),
            ("api", "repos/o/r/issues/11/dependencies/blocked_by"): (
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
    assert [p.issue.number for p in board.builds] == [20]
    assert len(run.calls) == 5  # nothing fetched for 12 or 21
