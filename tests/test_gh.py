import json

import pytest

from board.gh import GhClient, GhError
from helpers import REPO_VIEW, FakeRun


def test_repo_slug_is_the_repo_gh_is_in() -> None:
    run = FakeRun({tuple(REPO_VIEW): (0, json.dumps({"nameWithOwner": "o/r"}), "")})
    assert GhClient(runner=run).repo_slug() == "o/r"


def test_gh_error_on_hard_failure() -> None:
    run = FakeRun({tuple(REPO_VIEW): (1, "", "boom")})
    client = GhClient(runner=run)
    with pytest.raises(GhError, match="boom"):
        client.repo_slug()
