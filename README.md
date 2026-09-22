# board

Terminal board for GitHub issues shaped like Matt Pocock's skills:
WAYFINDING maps, SPECS and their tickets, and BACKLOG (debt / triage).

## Install

```bash
uv tool install -e E:/workspaces/ai/agents/board
```

Then run `board` inside any git clone with `gh` authenticated.

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
| Blue | Spec parent |
| Green | Takeable |
| Yellow | Claimed |
| Red | Blocked |
| Bright red / orange | P1 / P2 |
| Bright green | ready-for-agent |
