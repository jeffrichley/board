from __future__ import annotations

import typer
from rich.console import Console

from board.gh import GhError
from board.load import load_board
from board.render import render_board
from board.run import default_runner
from board.work import WorkError, start_session

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
def work(number: int) -> None:
    """Start a Claude Code session on ticket NUMBER, or go back to the one it has."""
    try:
        session = start_session(number, runner=default_runner)
    except (WorkError, GhError) as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    typer.echo(
        f"{session.window}  {session.status} in {session.worktree}"
        f"   tmux {session.target}"
    )


if __name__ == "__main__":
    app()
