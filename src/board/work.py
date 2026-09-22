"""Start a session on each ticket: a worktree, a tmux window, and Claude Code in it.

A ticket that already has a worktree has a session, so board goes back to that
one instead of starting a second. Board neither claims the ticket nor creates a
branch. The agent does both. Each ticket in a batch stands alone: one that can't
start is skipped with its reason, and the others still start.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from board.gh import GhClient
from board.load import load_board
from board.route import Refused, starting_command
from board.run import Result, Runner
from board.worktree import live_windows, worktree_paths


class WorkError(Exception):
    """Something every ticket needs is missing or failed. Reported plainly."""


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


@dataclass(frozen=True)
class Skipped:
    number: int
    reason: str


def start_sessions(
    numbers: Sequence[int], *, runner: Runner
) -> list[Session | Skipped]:
    """Start a session on each of `numbers`, or go back to the one it has.

    What every ticket needs (the tools, the clone, the board, a fresh
    `origin/main`) is checked once, and its failure raises `WorkError` before
    any session is touched. Board never attaches: it opens what's missing and
    says where each session is.
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
    sessions = {
        n: Session(
            number=n,
            worktree=root.parent / f"{root.name}.worktrees" / str(n),
            tmux_session=root.name,
        )
        for n in dict.fromkeys(numbers)
    }

    # A worktree means a session was started, whether or not the agent has
    # claimed the ticket yet, so board goes back to it rather than refusing.
    listing = must(
        "git", "worktree", "list", "--porcelain", why="could not list worktrees"
    )
    existing = set(worktree_paths(listing.stdout))
    # Only a ticket with no worktree yet needs the board to say how it starts.
    new = [n for n, s in sessions.items() if s.worktree not in existing]
    commands: dict[int, str | Refused] = {}
    if new:
        board = load_board(GhClient(runner=runner))
        commands = {n: starting_command(board, n) for n in new}
    if any(isinstance(c, str) for c in commands.values()):
        must("git", "fetch", "origin", why="could not fetch origin")
        if run("git", "rev-parse", "--verify", "origin/main").returncode != 0:
            raise WorkError(
                "This clone has no origin/main for a worktree to start from."
            )

    def open_window(session: Session, *claude: str) -> Result:
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

    def go_back(session: Session) -> Session | Skipped:
        if session.window in live_windows(runner, session.tmux_session):
            return replace(session, status="running")
        window = open_window(session, "--continue")
        if window.returncode != 0:
            # The worktree holds the session's work, so it stays.
            return Skipped(
                session.number,
                f"could not reopen the tmux window for #{session.number}\n"
                f"{window.stderr.strip()}",
            )
        return replace(session, status="resumed")

    def begin(session: Session, command: str | Refused) -> Session | Skipped:
        n = session.number
        if isinstance(command, Refused):
            return Skipped(n, command.reason)
        added = run(
            *["git", "worktree", "add", "--detach", str(session.worktree)],
            "origin/main",
        )
        if added.returncode != 0:
            return Skipped(
                n,
                f"could not make the worktree for #{n}\n"
                f"{added.stderr.strip() or added.stdout.strip()}",
            )
        window = open_window(session, command)
        if window.returncode != 0:
            # A worktree with no session makes the ticket look taken forever, so
            # the empty one goes back before the failure is reported.
            run("git", "worktree", "remove", "--force", str(session.worktree))
            return Skipped(
                n, f"could not open the tmux window for #{n}\n{window.stderr.strip()}"
            )
        return session

    return [
        begin(s, commands[n]) if n in commands else go_back(s)
        for n, s in sessions.items()
    ]
