from __future__ import annotations

from board.gh import GhClient
from board.model import Board, build_board


def load_board(client: GhClient | None = None) -> Board:
    client = client or GhClient()
    slug = client.repo_slug()
    got = client.open_issues(slug)
    return build_board(slug, got.issues, got.children_of, got.blockers_of)
