"""Remove the worktrees of finished tickets, and say why each other one stays.

A worktree goes only when its ticket is closed, it has nothing uncommitted,
every commit in it is on some remote branch, and no tmux window is alive for it.
Nothing else in board ever removes a worktree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from board.gh import GhClient
from board.run import Result, Runner


class CleanError(Exception):
    """Board could not look safely, so it removed nothing. Reported plainly."""


@dataclass(frozen=True)
class Outcome:
    name: str
    worktree: Path
    kept_because: list[str] = field(default_factory=list)
    # Set when every condition held but git would not remove it.
    error: str = ""

    @property
    def removed(self) -> bool:
        return not self.kept_because and not self.error


def _worktrees(porcelain: str) -> list[Path]:
    """Every worktree git lists, the main checkout first."""
    prefix = "worktree "
    return [
        Path(line[len(prefix) :])
        for line in porcelain.splitlines()
        if line.startswith(prefix)
    ]


def clean(*, runner: Runner) -> list[Outcome]:
    """Judge every worktree board made, removing the ones safe to remove."""

    def run(*args: str) -> Result:
        return runner(list(args))

    listed = run("git", "worktree", "list", "--porcelain")
    if listed.returncode != 0:
        raise CleanError(f"could not list worktrees\n{listed.stderr.strip()}")
    main, *others = _worktrees(listed.stdout)
    home = main.parent / f"{main.name}.worktrees"
    ours = [w for w in others if w.parent == home]
    if not ours:
        return []

    # Fetch first, so a commit already pushed from elsewhere isn't counted as unpushed.
    fetch = run("git", "fetch", "origin")
    if fetch.returncode != 0:
        raise CleanError(f"could not fetch origin\n{fetch.stderr.strip()}")
    gh = GhClient(runner=runner)
    slug = gh.repo_slug() if any(w.name.isdigit() for w in ours) else ""
    # No tmux server, or no session for this repo, means no window is alive.
    # `=` makes tmux match the session name exactly, not as a prefix.
    windows = run("tmux", "list-windows", "-t", f"={main.name}", "-F", "#{window_name}")
    alive = set(windows.stdout.split()) if windows.returncode == 0 else set()

    outcomes = []
    for tree in ours:
        reasons = []
        if not tree.name.isdigit():
            reasons.append("not named for a ticket")
        else:
            # Asked one by one: a number missing from the open list may be a
            # transferred or deleted issue, and that is not a closed ticket.
            state = gh.issue_state(slug, int(tree.name))
            if state is None:
                reasons.append("ticket not found")
            elif state != "closed":
                reasons.append("ticket still open")
        status = run("git", "-C", str(tree), "status", "--porcelain")
        if status.returncode != 0:
            reasons.append("could not read git status")
        elif status.stdout.strip():
            reasons.append("uncommitted changes")
        unpushed = run("git", "-C", str(tree), "rev-list", "HEAD", "--not", "--remotes")
        if unpushed.returncode != 0:
            reasons.append("could not check for unpushed commits")
        elif unpushed.stdout.strip():
            reasons.append("unpushed commits")
        if f"#{tree.name}" in alive:
            reasons.append("session still running")
        error = ""
        if not reasons:
            removal = run("git", "worktree", "remove", str(tree))
            if removal.returncode != 0:
                error = f"git worktree remove failed: {removal.stderr.strip()}"
        outcomes.append(Outcome(tree.name, tree, reasons, error))
    return outcomes
