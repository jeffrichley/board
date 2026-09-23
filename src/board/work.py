"""Start a session on each ticket: a worktree, a tmux window, and Claude Code in it.

A ticket that already has a worktree has a session, so board goes back to that
one instead of starting a second. A map gets one session at a time: before
starting another on it, board asks. Board neither claims the ticket nor creates a
branch. The agent does both. Each ticket in a batch stands alone: one that can't
start is skipped with its reason, and the others still start. A range stands for
the open tickets numbered within it, and they go through the same rules.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from board.gh import GhClient
from board.load import load_board
from board.model import Board, Issue
from board.route import (
    Refused,
    map_children,
    map_of,
    starting_command,
    ticket_numbers,
)
from board.run import Result, Runner
from board.worktree import live_windows, worktree_paths


class WorkError(Exception):
    """Something every ticket needs is missing or failed. Reported plainly."""


@dataclass(frozen=True)
class Range:
    """`first-last` on the command line: the open tickets numbered within it.

    GitHub numbers issues and pull requests from one counter, so a range drops
    its pull requests, closed issues and gaps without a word.
    """

    first: int
    last: int

    def __str__(self) -> str:
        return f"{self.first}-{self.last}"


def parse_ticket_or_range(text: str) -> int | Range:
    """A ticket number, or a range like `30-35`. A malformed one raises ValueError."""
    parts = re.fullmatch(r"(\d+)(?:(-)(\d*))?", text, re.ASCII)
    if parts is None:
        raise ValueError(f"{text} is not a ticket number or a range like 30-35.")
    first, dash, last = parts.groups()
    if not dash:
        return int(first)
    if not last:
        raise ValueError(
            f"{text} has no end: a range names its last ticket, as in 30-35."
        )
    if int(first) > int(last):
        raise ValueError(f"{text} runs backwards: write it {last}-{first}.")
    return Range(int(first), int(last))


@dataclass(frozen=True)
class Base:
    """The commit a new worktree starts from: `origin/main` as board fetched it."""

    commit: str  # abbreviated, as git abbreviates it
    # Commits in the base that the checkout's `main` lacks; None when git couldn't
    # say, as in a checkout with no local `main`.
    new_since_checkout: int | None


@dataclass(frozen=True)
class Session:
    number: int
    worktree: Path
    tmux_session: str
    # What board did: opened a new session, reopened the window of an existing
    # one, or found it already running.
    status: Literal["started", "resumed", "running"] = "started"
    # Only a session started now has one: a resumed worktree was cut back then.
    base: Base | None = None

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


@dataclass(frozen=True)
class Empty:
    """A range with no open tickets in it: nothing in it started, which fails the
    call as a skip does."""

    range: Range


def _in_progress(ticket: Issue, *, has_worktree: bool) -> list[str]:
    """Why `ticket` counts as work in progress, if it does."""
    n = ticket.number
    return [
        *([f"#{n} has a worktree"] if has_worktree else []),
        *([f"#{n} is claimed by @{ticket.assignee}"] if ticket.assignee else []),
    ]


def _one_session_per_map(
    board: Board,
    commands: dict[int, str | Refused],
    *,
    has_worktree: Callable[[int], bool],
    confirm: Callable[[str], bool],
) -> dict[int, str | Refused]:
    """`commands`, with each start you declined on a busy map refused instead.

    Parallel sessions on one map share no context and ask the same questions
    twice, so a second one starts only if you say so. A spec's children are
    sliced to run side by side, so they're never asked about.
    """
    out = dict(commands)
    starting: dict[int, list[int]] = {}  # map -> its tickets starting in this call
    for n, command in commands.items():
        node = map_of(board, n)
        if node is None or isinstance(command, Refused):
            continue
        m = node.issue.number
        # The map's worktree is a session on it, but its claim doesn't count: a
        # map is often assigned to its owner for as long as it's open.
        busy = [f"#{m} has a worktree"] if m != n and has_worktree(m) else []
        busy += [
            why
            for t in map_children(node)
            if t.number != n
            for why in _in_progress(t, has_worktree=has_worktree(t.number))
        ]
        busy += [f"#{t} is starting in this call" for t in starting.get(m, [])]
        if busy:
            why = f"already has work in progress: {'; '.join(busy)}."
            if not confirm(f"Map #{m} {why} Start #{n} too?"):
                out[n] = Refused(f"map #{m} {why}")
                continue
        starting.setdefault(m, []).append(n)
    return out


def _new_since_checkout(run: Callable[..., Result]) -> int | None:
    """How many commits `origin/main` has that the checkout's `main` doesn't.

    Advisory only: when git can't say, the count is dropped, never the session.
    """
    counted = run("git", "rev-list", "--count", "main..origin/main")
    count = counted.stdout.strip()
    return int(count) if counted.returncode == 0 and count.isdigit() else None


def _expand(
    tickets: Sequence[int | Range], on_board: set[int]
) -> tuple[list[int], list[Empty]]:
    """Each ticket in turn, a range giving way to the open tickets within it, and
    the ranges that held none. A bare number stands, open or not."""
    numbers: list[int] = []
    empty: list[Empty] = []
    for t in tickets:
        if isinstance(t, int):
            numbers.append(t)
            continue
        within = [n for n in sorted(on_board) if t.first <= n <= t.last]
        numbers += within
        if not within:
            empty.append(Empty(t))
    return numbers, empty


def start_sessions(
    tickets: Sequence[int | Range],
    *,
    runner: Runner,
    confirm: Callable[[str], bool],
) -> list[Session | Skipped | Empty]:
    """Start a session on each of `tickets`, or go back to the one it has.

    A range stands for the open tickets numbered within it; one with none is
    reported as `Empty`, ahead of the sessions.

    What every ticket needs (the tools, the clone, the board, a fresh
    `origin/main`) is checked once, and its failure raises `WorkError` before
    any session is touched. Board never attaches: it opens what's missing and
    says where each session is.

    `confirm` is asked, before anything is created, whether to start a session
    on a map that already has work in progress; a no skips that ticket.
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

    def tree(n: int) -> Path:
        return root.parent / f"{root.name}.worktrees" / str(n)

    # Only a range needs the board before the worktrees are looked at.
    board = (
        load_board(GhClient(runner=runner))
        if any(isinstance(t, Range) for t in tickets)
        else None
    )
    numbers, empty = _expand(tickets, ticket_numbers(board) if board else set())

    sessions = {
        n: Session(number=n, worktree=tree(n), tmux_session=root.name)
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
        board = board or load_board(GhClient(runner=runner))
        commands = {n: starting_command(board, n) for n in new}
        commands = _one_session_per_map(
            board,
            commands,
            has_worktree=lambda t: tree(t) in existing,
            confirm=confirm,
        )
    base: Base | None = None
    if any(isinstance(c, str) for c in commands.values()):
        must("git", "fetch", "origin", why="could not fetch origin")
        verified = run("git", "rev-parse", "--verify", "--short", "origin/main")
        if verified.returncode != 0:
            raise WorkError(
                "This clone has no origin/main for a worktree to start from."
            )
        base = Base(verified.stdout.strip(), _new_since_checkout(run))

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
        return replace(session, base=base)

    return [
        *empty,
        *(
            begin(s, commands[n]) if n in commands else go_back(s)
            for n, s in sessions.items()
        ),
    ]
