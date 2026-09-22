from __future__ import annotations

import typer
from rich.console import Console

from board.gh import GhError
from board.load import load_board
from board.render import render_board

app = typer.Typer(
    add_completion=False, help="Show the wayfinding / build / backlog board."
)
err_console = Console(stderr=True)


@app.callback(invoke_without_command=True)
def main() -> None:
    """Show open issues nested by Matt Pocock skill workflows."""
    try:
        board = load_board()
    except GhError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    render_board(board)


if __name__ == "__main__":
    app()
