# board

Terminal board for GitHub issues shaped like Matt Pocock's skills:
WAYFINDING maps, BUILD specs, and BACKLOG (debt / triage).

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
