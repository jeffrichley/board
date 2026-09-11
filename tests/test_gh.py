import json

import pytest

from board.gh import GhClient, GhError, decode_paginated_arrays


class FakeRun:
    def __init__(self, mapping: dict[tuple[str, ...], tuple[int, str, str]]):
        self.mapping = mapping
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]):
        self.calls.append(args)
        key = tuple(args)
        if key not in self.mapping:
            raise AssertionError(f"unexpected call {args}")
        code, out, err = self.mapping[key]
        return type("R", (), {"returncode": code, "stdout": out, "stderr": err})()


def test_decode_paginated_arrays():
    a = json.dumps([{"n": 1}])
    b = json.dumps([{"n": 2}])
    assert decode_paginated_arrays(a + "\n" + b) == [{"n": 1}, {"n": 2}]


def test_repo_slug_and_open_issues_drop_prs():
    issues = [
        {"number": 1, "title": "i", "labels": []},
        {"number": 2, "title": "pr", "labels": [], "pull_request": {}},
    ]
    run = FakeRun(
        {
            ("repo", "view", "--json", "nameWithOwner"): (
                0,
                json.dumps({"nameWithOwner": "o/r"}),
                "",
            ),
            ("api", "repos/o/r/issues?state=open&per_page=100", "--paginate"): (
                0,
                json.dumps(issues),
                "",
            ),
        }
    )
    client = GhClient(runner=run)
    assert client.repo_slug() == "o/r"
    assert [i["number"] for i in client.open_issues("o/r")] == [1]


def test_children_and_blockers_soft_fail():
    run = FakeRun(
        {
            ("api", "repos/o/r/issues/1/sub_issues?per_page=100"): (
                0,
                json.dumps([{"number": 2}]),
                "",
            ),
            ("api", "repos/o/r/issues/2/dependencies/blocked_by"): (1, "", "nope"),
        }
    )
    client = GhClient(runner=run)
    assert client.children("o/r", 1) == [2]
    assert client.blockers("o/r", 2) == []


def test_gh_error_on_hard_failure():
    run = FakeRun({("repo", "view", "--json", "nameWithOwner"): (1, "", "boom")})
    client = GhClient(runner=run)
    with pytest.raises(GhError, match="boom"):
        client.repo_slug()
