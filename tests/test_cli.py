from typer.testing import CliRunner

from board.cli import app
from board.model import Backlog, Board


def test_cli_renders_empty_board(monkeypatch):
    def fake_load():
        return Board("o/r", 0, [], [], Backlog())

    monkeypatch.setattr("board.cli.load_board", lambda: fake_load())
    result = CliRunner().invoke(app)
    assert result.exit_code == 0
    assert "o/r" in result.stdout
    assert "no open issues" in result.stdout.lower() or "0 open" in result.stdout
