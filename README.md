# board

Terminal board for GitHub issues shaped like Matt Pocock's skills:
WAYFINDING maps, SPECS and their tickets, and BACKLOG (debt / triage).

## Install

```bash
uv tool install -e E:/workspaces/ai/agents/board
```

Then run `board` inside any git clone with `gh` authenticated.

## Working a ticket

```bash
board work 120
```

`board work <n>` starts an interactive Claude Code session on ticket #120 and
attaches you to it. It fetches `origin`, adds a worktree for the ticket detached
at `origin/main` under `../<repo>.worktrees/<n>/`, opens a tmux window named
`#<n>` in the tmux session named for the repo, and runs Claude Code there on
`/mattpocock-skills:implement <n>`.

Board never claims the ticket and never creates a branch — the session's agent
does both, by the repo's own rules. Detach with `Ctrl-b d` and the session keeps
running; `Ctrl-b w` lists every ticket running on the repo.

It needs `tmux` and `claude` on PATH and an `origin/main` to start from, and it
says so plainly if one is missing. macOS and Linux only.

Scrolling and clicking between windows is easier with mouse mode on — put this
in `~/.tmux.conf`:

```tmux
set -g mouse on
```

## Develop

```bash
uv sync --group dev
uv run pytest
```

## Colors

| Color | Meaning |
|---|---|
| Cyan | Lane headers |
| Magenta | Map |
| Blue | Spec |
| Green | Takeable |
| Yellow | Claimed |
| Red | Blocked |
| Bright red / orange | P1 / P2 |
| Bright green | ready-for-agent |
