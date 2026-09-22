from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Any]


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


def _default_runner(args: list[str]) -> _Result:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return _Result(r.returncode, r.stdout, r.stderr)


class GhClient:
    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or _default_runner

    def _gh(self, *args: str) -> str:
        r = self._run(list(args))
        if r.returncode != 0:
            raise GhError(f"gh {' '.join(args)}\n{r.stderr.strip()}")
        return r.stdout

    def _gh_soft(self, *args: str) -> str | None:
        r = self._run(list(args))
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
