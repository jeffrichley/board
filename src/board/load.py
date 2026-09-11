from __future__ import annotations

from board.gh import GhClient
from board.model import Board, build_board


def load_board(client: GhClient | None = None) -> Board:
    client = client or GhClient()
    slug = client.repo_slug()
    issues = client.open_issues(slug)
    # Parents we may need children for: maps + anyone with kids_total > 0
    need_kids: set[int] = set()
    for raw in issues:
        labels = [lb["name"] for lb in raw.get("labels", [])]
        kids = (raw.get("sub_issues_summary") or {}).get("total", 0)
        if "wayfinder:map" in labels or kids:
            need_kids.add(raw["number"])
    children_of = {n: client.children(slug, n) for n in need_kids}
    # Blockers for every open issue that reports blocked_by > 0
    blockers_of: dict[int, list[int]] = {}
    for raw in issues:
        deps = (raw.get("issue_dependencies_summary") or {}).get("blocked_by", 0)
        if deps:
            blockers_of[raw["number"]] = client.blockers(slug, raw["number"])
    return build_board(slug, issues, children_of, blockers_of)
