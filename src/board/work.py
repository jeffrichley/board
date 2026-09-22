"""Start a session on a ticket: a worktree, a tmux window, and Claude Code in it.

A ticket that already has a worktree has a session, so board goes back to that
one instead of starting a second. Board neither claims the ticket nor creates a
branch. The agent does both.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from board.gh import GhClient
from board.load import load_board
from board.route import Refused, starting_command
from board.run import Result, Runner
from board.worktree import live_windows, worktree_paths


class WorkError(Exception):
    """Something board needs is missing or refused. Reported plainly."""


@dataclass(frozen=True)
class Session:
    number: int
    worktree: Path
    tmux_session: str
    # What board did: opened a new session, reopened the window of an existing
    # one, or found it already running.
    status: Literal["started", "resumed", "running"] = "started"

    @property
    def window(self) -> str:
        return f"#{self.number}"

    @property
    def exact(self) -> str:
        """The tmux session as a target that can't prefix-match `board-web`."""
        return f"={self.tmux_session}"

    @property
    def target(self) -> str:
        return f"{self.tmux_session}:{self.window}"


def start_session(number: int, *, runner: Runner) -> Session:
    """Start a session on `number`, or go back to the one it has.

    Board never attaches: it opens what's missing and says where the session is.
    """

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

    root = Path(
        must("git", "rev-parse", "--show-toplevel", why="not a git repo").stdout.strip()
    )
    session = Session(
        number=number,
        worktree=root.parent / f"{root.name}.worktrees" / str(number),
        tmux_session=root.name,
    )

    def open_window(*claude: str) -> Result:
        command = shlex.join(["claude", "--dangerously-skip-permissions", *claude])
        alive = run("tmux", "has-session", "-t", session.exact).returncode == 0
        where = (
            ["tmux", "new-window", "-t", session.exact]
            if alive
            else ["tmux", "new-session", "-d", "-s", session.tmux_session]
        )
        return run(
            *where, *["-n", session.window, "-c", str(session.worktree)], command
        )

    # A worktree means a session was started, whether or not the agent has
    # claimed the ticket yet, so board goes back to it rather than refusing.
    listing = must(
        "git", "worktree", "list", "--porcelain", why="could not list worktrees"
    )
    if session.worktree in worktree_paths(listing.stdout):
        if session.window in live_windows(runner, session.tmux_session):
            return replace(session, status="running")
        window = open_window("--continue")
        if window.returncode != 0:
            # The worktree holds the session's work, so it stays.
            raise WorkError(
                f"could not reopen the tmux window for #{number}\n"
                f"{window.stderr.strip()}"
            )
        return replace(session, status="resumed")

    start = starting_command(load_board(GhClient(runner=runner)), number)
    if isinstance(start, Refused):
        raise WorkError(start.reason)

    must("git", "fetch", "origin", why="could not fetch origin")
    if run("git", "rev-parse", "--verify", "origin/main").returncode != 0:
        raise WorkError("This clone has no origin/main for a worktree to start from.")
    must(
        *["git", "worktree", "add", "--detach", str(session.worktree), "origin/main"],
        why=f"could not make the worktree for #{number}",
    )

    window = open_window(start)
    if window.returncode != 0:
        # A worktree with no session makes the ticket look taken forever, so the
        # empty one goes back before the failure is reported.
        run("git", "worktree", "remove", "--force", str(session.worktree))
        raise WorkError(
            f"could not open the tmux window for #{number}\n{window.stderr.strip()}"
        )
    return session
