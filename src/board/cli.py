from __future__ import annotations

import typer
from rich.console import Console

from board.clean import CleanError, clean
from board.gh import GhError
from board.load import load_board
from board.render import render_board
from board.run import default_runner
from board.work import Skipped, WorkError, start_sessions

app = typer.Typer(
    add_completion=False, help="Show the wayfinding / specs / backlog board."
)
err_console = Console(stderr=True)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Show open issues nested by Matt Pocock skill workflows."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        board = load_board()
    except GhError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    render_board(board)


@app.command()
def work(numbers: list[int]) -> None:
    """Start a Claude Code session on each ticket, or go back to the one it has.

    Exits non-zero if any ticket was skipped.
    """
    try:
        outcomes = start_sessions(numbers, runner=default_runner)
    except (WorkError, GhError) as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    skipped = False
    for outcome in outcomes:
        if isinstance(outcome, Skipped):
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
    if skipped:
        raise typer.Exit(code=1)


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
