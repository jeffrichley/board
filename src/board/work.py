"""Start a session on a ticket: a worktree, a tmux window, and Claude Code in it.

Board neither claims the ticket nor creates a branch. The agent does both.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from board.run import Result, Runner

IMPLEMENT = "/mattpocock-skills:implement"


class WorkError(Exception):
    """Something board needs is missing or refused. Reported plainly."""


@dataclass(frozen=True)
class Session:
    number: int
    worktree: Path
    tmux_session: str

    @property
    def window(self) -> str:
        return f"#{self.number}"

    @property
    def target(self) -> str:
        return f"{self.tmux_session}:{self.window}"


def start_session(number: int, *, runner: Runner) -> Session:
    """Make the worktree for `number`, open its window, and attach to it."""

    def run(*args: str, capture: bool = True) -> Result:
        return runner(list(args), capture=capture)

    def must(*args: str, why: str) -> Result:
        r = run(*args)
        if r.returncode != 0:
            raise WorkError(f"{why}\n{r.stderr.strip() or r.stdout.strip()}")
        return r

    if run("tmux", "-V").returncode != 0:
        raise WorkError("tmux is not on PATH. board work needs tmux to hold a session.")
    if run("claude", "--version").returncode != 0:
        raise WorkError("claude is not on PATH. Install Claude Code to work a ticket.")

    root = Path(
        must("git", "rev-parse", "--show-toplevel", why="not a git repo").stdout.strip()
    )
    must("git", "fetch", "origin", why="could not fetch origin")
    if run("git", "rev-parse", "--verify", "origin/main").returncode != 0:
        raise WorkError("This clone has no origin/main for a worktree to start from.")

    session = Session(
        number=number,
        worktree=root.parent / f"{root.name}.worktrees" / str(number),
        tmux_session=root.name,
    )
    must(
        *["git", "worktree", "add", "--detach", str(session.worktree), "origin/main"],
        why=f"could not make the worktree for #{number}",
    )

    command = shlex.join(
        ["claude", "--dangerously-skip-permissions", f"{IMPLEMENT} {number}"]
    )
    alive = run("tmux", "has-session", "-t", session.tmux_session).returncode == 0
    open_window = (
        ["tmux", "new-window", "-t", session.tmux_session]
        if alive
        else ["tmux", "new-session", "-d", "-s", session.tmux_session]
    )
    must(
        *open_window,
        *["-n", session.window, "-c", str(session.worktree), command],
        why=f"could not open the tmux window for #{number}",
    )
    run("tmux", "attach-session", "-t", session.target, capture=False)
    return session
