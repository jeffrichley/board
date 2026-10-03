"""What git and tmux say about the worktrees and windows board has made."""

from __future__ import annotations

from pathlib import Path

from board.run import Runner


def worktree_paths(porcelain: str) -> list[Path]:
    """Every worktree in `git worktree list --porcelain`, the main checkout first."""
    return [
        Path(line.removeprefix("worktree "))
        for line in porcelain.splitlines()
        if line.startswith("worktree ")
    ]


def worktree_home(main: Path) -> Path:
    """Where board puts the worktrees of the clone whose main checkout is `main`."""
    return main.parent / f"{main.name}.worktrees"


def ticket_worktrees(porcelain: str) -> set[int]:
    """The tickets with a worktree board made, from `git worktree list --porcelain`."""
    main, *others = worktree_paths(porcelain)
    return {
        int(w.name)
        for w in others
        if w.parent == worktree_home(main) and w.name.isdigit()
    }


def live_windows(runner: Runner, tmux_session: str) -> set[str]:
    """The window names alive in `tmux_session`; none when it or tmux isn't running.

    `=` makes tmux match the session name exactly, so a sibling repo's
    `board-web` is never taken for `board`.
    """
    windows = runner(
        ["tmux", "list-windows", "-t", f"={tmux_session}", "-F", "#{window_name}"]
    )
    return set(windows.stdout.splitlines()) if windows.returncode == 0 else set()
