from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from board.run import Runner, default_runner


class GhError(Exception):
    pass


# A page of sub-issues or blockers: each one's state, so a closed one is left out.
_LINKED = "pageInfo{hasNextPage endCursor} nodes{number state}"

# The whole board in one call per hundred open issues. GraphQL's `issues` has no
# pull requests in it, and a list longer than its page is followed by FOLLOW_QUERY.
BOARD_QUERY = f"""query($owner:String!,$name:String!,$cursor:String){{
  repository(owner:$owner,name:$name){{
    issues(states:OPEN,first:100,after:$cursor){{
      pageInfo{{hasNextPage endCursor}}
      nodes{{
        number title body
        labels(first:100){{nodes{{name}}}}
        assignees(first:1){{nodes{{login}}}}
        subIssuesSummary{{total completed}}
        subIssues(first:100){{{_LINKED}}}
        blockedBy(first:100){{{_LINKED}}}
      }}
    }}
  }}
}}"""

# The rest of one issue's sub-issues or blockers, from a cursor.
FOLLOW_QUERY = {
    field: f"""query($owner:String!,$name:String!,$number:Int!,$cursor:String){{
  repository(owner:$owner,name:$name){{
    issue(number:$number){{
      {field}(first:100,after:$cursor){{{_LINKED}}}
    }}
  }}
}}"""
    for field in ("subIssues", "blockedBy")
}


@dataclass(frozen=True)
class OpenIssues:
    """A repo's open issues, shaped as the model reads them, and how they link."""

    issues: list[dict[str, Any]]
    children_of: dict[int, list[int]]  # every sub-issue, open or closed
    blockers_of: dict[int, list[int]]  # open blockers only


def _as_rest_issue(node: dict[str, Any], open_blockers: int) -> dict[str, Any]:
    """A GraphQL issue in the shape `Issue.from_raw` reads.

    The board shows one assignee, so the first stands for all of them.
    """
    assignees = node["assignees"]["nodes"]
    return {
        "number": node["number"],
        "title": node["title"],
        "body": node["body"],
        "labels": node["labels"]["nodes"],
        "assignee": assignees[0] if assignees else None,
        "sub_issues_summary": node["subIssuesSummary"],
        "issue_dependencies_summary": {"blocked_by": open_blockers},
    }


class GhClient:
    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or default_runner

    def _gh(self, *args: str) -> str:
        r = self._run(["gh", *args])
        if r.returncode != 0:
            raise GhError(f"gh {' '.join(args)}\n{r.stderr.strip()}")
        return r.stdout

    def _gh_soft(self, *args: str) -> str | None:
        r = self._run(["gh", *args])
        if r.returncode != 0:
            return None
        return r.stdout

    def repo_slug(self) -> str:
        view = json.loads(self._gh("repo", "view", "--json", "nameWithOwner"))
        slug: str = view["nameWithOwner"]
        return slug

    def _graphql(self, query: str, *fields: str) -> dict[str, Any]:
        r = self._run(["gh", "api", "graphql", "-f", f"query={query}", *fields])
        if r.returncode != 0:
            raise GhError(f"gh api graphql\n{r.stderr.strip()}")
        answer = json.loads(r.stdout)
        if errors := answer.get("errors"):
            messages = "\n".join(e["message"] for e in errors)
            raise GhError(f"gh api graphql\n{messages}")
        data: dict[str, Any] = answer["data"]
        return data

    def open_issues(self, slug: str) -> OpenIssues:
        owner, name = slug.split("/", 1)
        repo = ["-f", f"owner={owner}", "-f", f"name={name}"]
        issues: list[dict[str, Any]] = []
        children_of: dict[int, list[int]] = {}
        blockers_of: dict[int, list[int]] = {}
        after: list[str] = []
        while True:
            data = self._graphql(BOARD_QUERY, *repo, *after)
            page = data["repository"]["issues"]
            for node in page["nodes"]:
                num = node["number"]
                kids = self._every_linked(node, "subIssues", repo)
                blockers = self._every_linked(node, "blockedBy", repo)
                # GraphQL lists blockers oldest first; the board names the newest
                # first, as the REST list it was built on did.
                open_blockers = [
                    b["number"] for b in reversed(blockers) if b["state"] == "OPEN"
                ]
                if kids:
                    children_of[num] = [k["number"] for k in kids]
                if open_blockers:
                    blockers_of[num] = open_blockers
                issues.append(_as_rest_issue(node, len(open_blockers)))
            if not page["pageInfo"]["hasNextPage"]:
                return OpenIssues(issues, children_of, blockers_of)
            after = ["-f", f"cursor={page['pageInfo']['endCursor']}"]

    def _every_linked(
        self, node: dict[str, Any], field: str, repo: list[str]
    ) -> list[dict[str, Any]]:
        """Every entry in `node`'s `field` list, following it past its first page."""
        page = node[field]
        linked = list(page["nodes"])
        while page["pageInfo"]["hasNextPage"]:
            data = self._graphql(
                FOLLOW_QUERY[field],
                *repo,
                *["-F", f"number={node['number']}"],
                *["-f", f"cursor={page['pageInfo']['endCursor']}"],
            )
            page = data["repository"]["issue"][field]
            linked += page["nodes"]
        return linked

    def issue_state(self, slug: str, num: int) -> str | None:
        """`open` or `closed`, or None when the issue can't be found."""
        raw = self._gh_soft("api", f"repos/{slug}/issues/{num}")
        if raw is None:
            return None
        state: str = json.loads(raw)["state"]
        return state
