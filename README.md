# board

Terminal board for GitHub issues shaped like Matt Pocock's skills:
WAYFINDING maps, SPECS and their tickets, and BACKLOG (debt / triage).

## Install

```bash
uv tool install -e E:/workspaces/ai/agents/board
```

Then run `board` inside any git clone with `gh` authenticated. It shows the
board; `board show` is the same command by name, for its `--help`.

## Working a ticket

```bash
board work 120
```

`board work <n>` starts an interactive Claude Code session on ticket #120 and
leaves you at your prompt. It fetches `origin`, adds a worktree for the ticket detached
at `origin/main` under `../<repo>.worktrees/<n>/`, opens a tmux window named
`#<n>` in the tmux session named for the repo, and runs Claude Code there with
the starting command for where the ticket sits:

| Ticket | Starting command |
|---|---|
| a map | `/mattpocock-skills:wayfinder <map>` |
| a map's child | `/mattpocock-skills:wayfinder <map> <child>` |
| a spec's child, or a backlog ticket | `/mattpocock-skills:implement <n>` |
| a spec itself | refused: work its tickets |
| an orphan wayfinder ticket | refused: there's no map to work it through |

It also refuses a ticket that is claimed (naming the assignee) or blocked
(naming its open blockers). A refusal creates nothing and exits non-zero.

Board never claims the ticket and never creates a branch — the session's agent
does both, by the repo's own rules.

Board doesn't attach you to the session. It says where it is, in one line:

```
#120  started in /repos/board.worktrees/120   tmux board:#120
```

so you can start another ticket straight away.

Run `board work <n>` again on a ticket that already has a worktree and it goes
back to that session rather than starting a second, even once the agent has
claimed the ticket. If the ticket's window is still open, board creates nothing
and says `#120  running in …`. If the window is gone, board opens a new `#120`
window in the worktree running `claude --dangerously-skip-permissions --continue`
and says `#120  resumed in …`.

A map gets one session at a time. Before starting a session on a map or one of
its children, board asks if that map already has work in progress: the map or
another of its children has a worktree, another child is claimed, or another
ticket on the map is starting in the same `board work` call. The map's own
claim doesn't count, since a map is often assigned to its owner while it's open.
The question names the ticket in progress and why:

```
Map #10 already has work in progress: #11 has a worktree. Start #12 too? [y/N]:
```

Answer `y` to start it anyway. `n`, or just Enter, skips it with that reason.
`board work --yes` starts it without asking. A spec's children and backlog
tickets are never asked about, because they're sliced to run side by side.

Name several tickets to start them all in one go:

```bash
board work 120 121 122
```

Each ticket is handled on its own. Every one that can start or resume does, and
gets the same one line it would get alone. Every one that can't is skipped, and
board prints it with its reason:

```
#120  started in /repos/board.worktrees/120   tmux board:#120
#121  skipped: #121 is claimed by @alice.
#122  running in /repos/board.worktrees/122   tmux board:#122
```

Started and running tickets print to stdout, skipped ones to stderr. The exit
code is non-zero if any ticket was skipped, so a script can tell. Board reads
the board and fetches `origin` once for the whole batch. If something every
ticket needs is missing, such as `tmux` or `origin/main`, board stops before
touching any ticket.

To reach and end sessions (with
`board` standing for your repo's name):

| To | Run |
|---|---|
| get into the repo's sessions from a plain terminal | `tmux attach -t board` |
| pick a ticket's window, once inside tmux | `Ctrl-b w`, then arrow keys and Enter |
| leave tmux with every session still running | `Ctrl-b d` |
| end one ticket's session | `tmux kill-window -t board:#120` |

`Ctrl-b w` means: press `Ctrl` and `b` together, let go, then press `w`.
`Ctrl-b` is tmux's prefix, and every tmux shortcut starts with it.

It needs `tmux` and `claude` on PATH and an `origin/main` to start from, and it
says so plainly if one is missing. macOS and Linux only.

Scrolling and clicking between windows is easier with mouse mode on — put this
in `~/.tmux.conf`:

```tmux
set -g mouse on
```

## Cleaning up worktrees

```bash
board clean
```

`board clean` removes each worktree under `../<repo>.worktrees/` that is safe to
remove, with `git worktree remove`. It removes one only when its ticket is
closed, it has no uncommitted changes, every commit in it is on some remote
branch (after fetching `origin`), and no tmux window is alive for it. Every
worktree it keeps is listed with its reasons:

```
#120  removed  /repos/board.worktrees/120
#121  kept: ticket still open, session still running
```

Nothing else in board ever removes a worktree.

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
