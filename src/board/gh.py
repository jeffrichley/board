from __future__ import annotations

import json
from typing import Any

from board.run import Runner, default_runner


class GhError(Exception):
    pass


def decode_paginated_arrays(raw: str) -> list[Any]:
    out: list[Any] = []
    dec = json.JSONDecoder()
    idx = 0
    while idx < len(raw):
        while idx < len(raw) and raw[idx] in " \t\r\n":
            idx += 1
        if idx >= len(raw):
            break
        val, idx = dec.raw_decode(raw, idx)
        out.extend(val)
    return out


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

    def open_issues(self, slug: str) -> list[dict[str, Any]]:
        raw = self._gh(
            "api", f"repos/{slug}/issues?state=open&per_page=100", "--paginate"
        )
        return [i for i in decode_paginated_arrays(raw) if "pull_request" not in i]

    def children(self, slug: str, num: int) -> list[int]:
        raw = self._gh_soft("api", f"repos/{slug}/issues/{num}/sub_issues?per_page=100")
        if raw is None:
            return []
        return [c["number"] for c in json.loads(raw)]

    def blockers(self, slug: str, num: int) -> list[int]:
        raw = self._gh_soft("api", f"repos/{slug}/issues/{num}/dependencies/blocked_by")
        if raw is None:
            return []
        return [b["number"] for b in json.loads(raw)]

    def issue_state(self, slug: str, num: int) -> str | None:
        """`open` or `closed`, or None when the issue can't be found."""
        raw = self._gh_soft("api", f"repos/{slug}/issues/{num}")
        if raw is None:
            return None
        state: str = json.loads(raw)["state"]
        return state
