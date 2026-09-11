import typer

app = typer.Typer(add_completion=False, help="Show the wayfinding / build / backlog board.")


@app.callback(invoke_without_command=True)
def main() -> None:
    """Show open issues nested by Matt Pocock skill workflows."""
    typer.echo("board: not implemented yet")


if __name__ == "__main__":
    app()
