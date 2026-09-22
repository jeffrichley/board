"""The one seam to the outside world.

Every external call board makes — `gh`, `git`, `tmux`, `claude` — goes through a
`Runner`, so a test can describe the whole world in one place.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def __call__(self, args: list[str]) -> Result:
        """Run a command, program first, capturing its output."""
        ...


def default_runner(args: list[str]) -> Result:
    try:
        out = subprocess.run(args, capture_output=True, text=True)
        return Result(out.returncode, out.stdout, out.stderr)
    except FileNotFoundError:
        # What a shell reports for a command that isn't on PATH.
        return Result(127, "", f"{args[0]}: command not found")
