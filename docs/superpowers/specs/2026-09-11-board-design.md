# Board CLI — design

Date: 2026-09-11

## Problem

`board` prints open GitHub issues for the current repo, but as flat sibling sections (MAPS, SPECS, TAKEABLE, CLAIMED, BLOCKED). That fights how Matt Pocock’s skills actually structure work: wayfinding maps own decision tickets; specs own build tickets; debt and triage sit outside either tree. The script is also a bare `~/.local/bin/board.py` with hand-rolled ANSI and no declared deps.

## Goal

A Typer + Rich CLI, managed with `uv`, that shows the issue board as three lanes matching those workflows, with color that encodes role at a glance.

## Output layout

```
owner/repo — N open

WAYFINDING
  #240  Idle Thread factory                         3/14 done
    TAKEABLE
      #245  …                    wayfinder:grilling   unblocks 2
    CLAIMED
      #252  …                    @user
    BLOCKED
      #247  …                    <- #245

BUILD
  #163  Foundation execution spec                   12/20 done
    TAKEABLE / CLAIMED / BLOCKED  (same nesting)

BACKLOG
  P1
    #100  …
  P2 / other debt
    …
  ready-for-agent (no parent)
    …
  other
    …
```

### Classification

| Lane | Rule |
|---|---|
| **WAYFINDING** | Open issues labelled `wayfinder:map`. Children = that map’s GitHub sub-issues that are still open. |
| **BUILD** | Open issues with at least one open sub-issue, that are not maps and not themselves a child of another open parent. |
| **BACKLOG** | Open issues that are neither a map/build parent nor a child listed under one — debt, triage, unlabeled, orphan `wayfinder:*` tickets. |

Omit empty lanes. Always show an open map or build parent, even if it has no takeable children. An issue appears in at most one place on the board.

### Ticket ordering under a parent

1. **TAKEABLE** — open, no open blockers, unassigned. Sort by transitive unblock count (desc), then number.
2. **CLAIMED** — open, no open blockers, assigned. Sort by number.
3. **BLOCKED** — open with open blockers. Sort by number; show a short blocker chain (`<- #a <- #b`).

Blocker edges come from GitHub’s native `dependencies/blocked_by` API only — not from body prose.

## Color language

| Style | Meaning |
|---|---|
| Cyan bold | Lane headers (`WAYFINDING`, `BUILD`, `BACKLOG`) |
| Magenta | Map titles |
| Blue | Build-parent (spec) titles |
| Green | Takeable |
| Yellow | Claimed |
| Red | Blocked; dim red for blocker chains |
| Default | Ticket titles |
| Dim | Labels, progress counts, `unblocks N` |
| Bright red / orange | `P1` / `P2` in backlog |
| Bright green | `ready-for-agent` accent in backlog |

Render with Rich `Tree` for parent → ticket groups. Optional one-line legend is fine; not required for v1.

## Stack & project shape

- **Language:** Python 3
- **CLI:** Typer — single command `board` in v1 (no subcommands)
- **UI:** Rich
- **Package manager:** `uv` (`pyproject.toml`, lockfile, `uv sync`)
- **Install:** `uv tool install -e .` so `board` is on PATH; retire the old `~/.local/bin/board{.py,.cmd}` shims after that works
- **Repo:** `E:\workspaces\ai\agents\board`

```
board/
  pyproject.toml
  src/board/
    cli.py      # Typer app
    gh.py       # gh subprocess + pagination
    model.py    # fetch, classify, blocker graph
    render.py   # Rich trees and styles
```

## Data flow

1. Resolve repo slug via `gh repo view --json nameWithOwner`
2. List open issues (API, paginated); drop PRs
3. Classify into maps, build parents, backlog
4. For each parent, fetch `sub_issues`; for blocked tickets, fetch `blocked_by`
5. Build blocker graph among open issues only
6. Render with Rich

`gh` failures: print a Rich error on stderr and exit non-zero.

## Out of scope (v1)

- Subcommands (`board map 240`, claim/assign)
- Config files
- Writing to GitHub
- Parsing `Blocked by:` body prose
- Local-markdown issue trackers

## Success

Running `board` inside a clone shows wayfinding and build work nested under their real parents, backlog items in a separate lane, and status readable by color without reading labels first.
