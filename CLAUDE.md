# board

A Typer + Rich CLI that renders a repo's open GitHub issues as a wayfinding / build / backlog board.

## The standards live in waystation

Board has no rules of its own. It follows its sibling project's, so read these before your first edit:

- **`../waystation/CLAUDE.md`** (on GitHub: `jeffrichley/waystation`) covers the workflow. **Claiming the ticket is your first write**: `gh issue edit <n> --add-assignee @me`. After that: a branch, conventional commits with no `Co-Authored-By` trailer, a PR, and **green means land it**.
- **`../waystation/tests/CLAUDE.md`** covers test idiom: name the behaviour, and move a helper to the shared file on its second use.

Take the workflow, commit and test rules. Waystation's library-specific machinery (ADRs, `CONTEXT.md`, the public-import contract, docker and async test tiers) has no counterpart here.

## Done means CI is green

`just check` is the local signal. CI runs the same recipe on Ubuntu and Windows, and the PR's run decides.

## Tests

Fake `gh` with `FakeRun` from `tests/helpers.py`, passed as `GhClient(runner=...)`. It answers only the calls it's given, so an unexpected `gh` call fails the test. Test rendering through `render_board` with a recording `Console`.
