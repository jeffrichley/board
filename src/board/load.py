from __future__ import annotations

from collections.abc import Collection

from board.gh import GhClient
from board.model import Board, build_board


def load_board(
    client: GhClient | None = None, worktrees: Collection[int] = ()
) -> Board:
    """The repo's board; a ticket in `worktrees` has a worktree, so it is taken."""
    client = client or GhClient()
    slug = client.repo_slug()
    open_issues = client.open_issues(slug)
    return build_board(
        slug,
        open_issues.issues,
        open_issues.children_of,
        open_issues.blockers_of,
        worktrees,
    )
