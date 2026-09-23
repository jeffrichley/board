from __future__ import annotations

from board.gh import GhClient
from board.model import Board, build_board


def load_board(client: GhClient | None = None) -> Board:
    client = client or GhClient()
    slug = client.repo_slug()
    open_issues = client.open_issues(slug)
    return build_board(
        slug, open_issues.issues, open_issues.children_of, open_issues.blockers_of
    )
