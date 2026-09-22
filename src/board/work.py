"""Start a session on a ticket: a worktree, a tmux window, and Claude Code in it.

Board neither claims the ticket nor creates a branch. The agent does both.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from board.gh import GhClient
from board.load import load_board
from board.route import Refused, starting_command
from board.run import Result, Runner


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
    """Make the worktree for `number` and open its window. Board never attaches."""

    def run(*args: str) -> Result:
        return runner(list(args))

    def must(*args: str, why: str) -> Result:
        r = run(*args)
        if r.returncode != 0:
            raise WorkError(f"{why}\n{r.stderr.strip() or r.stdout.strip()}")
        return r

    def require(tool: str, *args: str, need: str) -> None:
        r = run(tool, *args)
        if r.returncode == 127:  # what a shell reports for a command not on PATH
            raise WorkError(f"{tool} is not on PATH. {need}")
        if r.returncode != 0:
            raise WorkError(f"{tool} is on PATH but failed.\n{r.stderr.strip()}")

    require("tmux", "-V", need="board work needs tmux to hold a session.")
    require("claude", "--version", need="Install Claude Code to work a ticket.")

    start = starting_command(load_board(GhClient(runner=runner)), number)
    if isinstance(start, Refused):
        raise WorkError(start.reason)

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

    command = shlex.join(["claude", "--dangerously-skip-permissions", start])
    alive = run("tmux", "has-session", "-t", session.tmux_session).returncode == 0
    open_window = (
        ["tmux", "new-window", "-t", session.tmux_session]
        if alive
        else ["tmux", "new-session", "-d", "-s", session.tmux_session]
    )
    window = run(
        *open_window, *["-n", session.window, "-c", str(session.worktree), command]
    )
    if window.returncode != 0:
        # A worktree with no session makes the ticket look taken forever, so the
        # empty one goes back before the failure is reported.
        run("git", "worktree", "remove", "--force", str(session.worktree))
        raise WorkError(
            f"could not open the tmux window for #{number}\n{window.stderr.strip()}"
        )
    return session
