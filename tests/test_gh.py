import json

import pytest

from board.gh import GhClient, GhError, decode_paginated_arrays
from helpers import FakeRun


def test_decode_paginated_arrays() -> None:
    a = json.dumps([{"n": 1}])
    b = json.dumps([{"n": 2}])
    assert decode_paginated_arrays(a + "\n" + b) == [{"n": 1}, {"n": 2}]


def test_repo_slug_and_open_issues_drop_prs() -> None:
    issues = [
        {"number": 1, "title": "i", "labels": []},
        {"number": 2, "title": "pr", "labels": [], "pull_request": {}},
    ]
    run = FakeRun(
        {
            ("gh", "repo", "view", "--json", "nameWithOwner"): (
                0,
                json.dumps({"nameWithOwner": "o/r"}),
                "",
            ),
            ("gh", "api", "repos/o/r/issues?state=open&per_page=100", "--paginate"): (
                0,
                json.dumps(issues),
                "",
            ),
        }
    )
    client = GhClient(runner=run)
    assert client.repo_slug() == "o/r"
    assert [i["number"] for i in client.open_issues("o/r")] == [1]


def test_children_and_blockers_soft_fail() -> None:
    run = FakeRun(
        {
            ("gh", "api", "repos/o/r/issues/1/sub_issues?per_page=100"): (
                0,
                json.dumps([{"number": 2}]),
                "",
            ),
            ("gh", "api", "repos/o/r/issues/2/dependencies/blocked_by"): (
                1,
                "",
                "nope",
            ),
        }
    )
    client = GhClient(runner=run)
    assert client.children("o/r", 1) == [2]
    assert client.blockers("o/r", 2) == []


def test_gh_error_on_hard_failure() -> None:
    run = FakeRun({("gh", "repo", "view", "--json", "nameWithOwner"): (1, "", "boom")})
    client = GhClient(runner=run)
    with pytest.raises(GhError, match="boom"):
        client.repo_slug()
