# board

A terminal view of one repo's open GitHub issues, laid out by how work flows through them, and a place to start working a ticket from.

## The board

**Repo**:
The one GitHub repository a board shows: the one the current directory belongs to.
_Avoid_: project, workspace

**Ticket**:
An open GitHub issue on the board.
_Avoid_: card, task, issue (in the UI)

**Lane**:
One of the board's three top-level sections: Wayfinding, Specs and Backlog.
_Avoid_: column, swimlane, section

**Map**:
A ticket labelled `wayfinder:map`. It heads the Wayfinding lane, with its child tickets beneath it.
_Avoid_: plan, roadmap, epic

**Spec**:
A ticket that is not a map but has open child tickets: usually what `/to-spec` wrote, with the tickets `/to-tickets` sliced from it as children. It heads the Specs lane, with its child tickets beneath it.
_Avoid_: build, feature, parent

**Backlog**:
Every ticket that sits under no map or spec, grouped by label: P1, P2 / debt, ready-for-agent, orphan wayfinder, other.
_Avoid_: todo, icebox

## Taking work

**Claim**:
The assignee on a ticket. A claimed ticket is taken.
_Avoid_: lock, owner, reservation

**Takeable**:
A ticket that is unclaimed, has no open blockers, and has no worktree, wherever it sits on the board. Only a takeable ticket can have a session started on it.
_Avoid_: ready, available, free

**Blocked**:
A ticket with at least one open blocker.
_Avoid_: waiting, stuck

**Range**:
Two ticket numbers joined by a dash, `30-35`, standing for the tickets numbered within it: the open issues in the span, with pull requests, closed issues and gaps dropped silently. A range is worked exactly as if its tickets were named one by one.
_Avoid_: span, batch, interval

**Frontier**:
All the takeable tickets under one map or spec.
_Avoid_: queue, ready list

## Working a ticket

**Session**:
One interactive Claude Code conversation working one ticket, in that ticket's worktree. You can watch and answer it while it runs.
_Avoid_: run, job, agent, worker

**Worktree**:
A git worktree board makes for one ticket, so its session is isolated from your checkout and from other sessions. The session's work leaves it through the repo's normal route to `main`.
_Avoid_: workspace, sandbox, clone

**Checkout**:
The clone you work in yourself, and the one you run board from. A session never touches it, and its branches and its `main` say nothing about where a session starts.
_Avoid_: repo, local, working copy

**Base**:
The commit a worktree starts from: `origin/main`, as of the fetch board makes when it starts a session. Never the checkout's `main`, so a stale checkout can't hold a session back — and work that hasn't merged isn't in a new session's base, however finished it is.
_Avoid_: head, latest, trunk
