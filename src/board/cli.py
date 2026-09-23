from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from board.clean import CleanError, clean
from board.gh import GhClient, GhError
from board.load import load_board
from board.render import render_board
from board.run import default_runner
from board.work import (
    Base,
    Empty,
    Skipped,
    WorkError,
    parse_ticket,
    start_sessions,
)

app = typer.Typer(
    add_completion=False, help="Show the wayfinding / specs / backlog board."
)
err_console = Console(stderr=True)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Bare `board` shows the board."""
    if ctx.invoked_subcommand is None:
        show()


@app.command(short_help="Show the wayfinding / specs / backlog board. (default)")
def show() -> None:
    """Show the wayfinding / specs / backlog board.

    Open tickets nested by Matt Pocock skill workflows. Bare `board` does the same.
    """
    try:
        board = load_board(GhClient(runner=default_runner))
    except GhError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    render_board(board)


@app.command()
def work(
    tickets: Annotated[
        list[str],
        typer.Argument(
            metavar="TICKET...",
            help="Ticket numbers, or ranges like 30-35, in any mix.",
        ),
    ],
    yes: bool = typer.Option(
        False, "--yes", help="Start a second session on a map without asking."
    ),
) -> None:
    """Start a Claude Code session on each ticket, or go back to the one it has.

    A range like 30-35 means the open tickets numbered within it. Before a second
    session on one map, asks [y/N]. Exits non-zero if any ticket was skipped.
    """

    def confirm(question: str) -> bool:
        return yes or typer.confirm(question, default=False)

    try:
        parsed = [parse_ticket(t) for t in tickets]
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="TICKET") from e
    try:
        outcomes = start_sessions(parsed, runner=default_runner, confirm=confirm)
    except (WorkError, GhError) as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    skipped = False
    for outcome in outcomes:
        if isinstance(outcome, Empty):
            skipped = True
            err_console.print(f"[red]no open tickets in {outcome.span}[/red]")
        elif isinstance(outcome, Skipped):
            skipped = True
            # Unwrapped: board adds no line breaks of its own to a reason.
            err_console.print(
                f"[red]#{outcome.number}  skipped: {outcome.reason}[/red]",
                soft_wrap=True,
            )
        else:
            typer.echo(
                f"{outcome.window}  {outcome.status} in {outcome.worktree}"
                f"   tmux {outcome.target}"
            )
            if outcome.base is not None:
                typer.echo(
                    f"{' ' * (len(outcome.window) + 2)}{_base_line(outcome.base)}"
                )
    if skipped:
        raise typer.Exit(code=1)


def _base_line(base: Base) -> str:
    """Where a started session's worktree was cut, and what your checkout lacks."""
    new = base.new_since_checkout
    behind = f" ({new} new since your checkout)" if new else ""
    return f"from origin/main @ {base.commit}{behind}"


@app.command(name="clean")
def clean_worktrees() -> None:
    """Remove the worktrees of closed tickets that hold nothing unsaved."""
    try:
        outcomes = clean(runner=default_runner)
    except (CleanError, GhError) as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    if not outcomes:
        typer.echo("No worktrees to clean.")
        return
    for o in outcomes:
        if o.removed:
            typer.echo(f"#{o.name}  removed  {o.worktree}")
        elif o.error:
            typer.echo(f"#{o.name}  kept: {o.error}")
        else:
            typer.echo(f"#{o.name}  kept: {', '.join(o.kept_because)}")
    if any(o.error for o in outcomes):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
