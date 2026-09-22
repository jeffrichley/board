import pytest
from typer.testing import CliRunner

from board.cli import app
from board.gh import GhError
from board.model import Backlog, Board


def test_cli_renders_empty_board(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load() -> Board:
        return Board("o/r", 0, [], [], Backlog())

    monkeypatch.setattr("board.cli.load_board", lambda: fake_load())
    result = CliRunner().invoke(app)
    assert result.exit_code == 0
    assert "o/r" in result.stdout
    assert "no open issues" in result.stdout.lower() or "0 open" in result.stdout


def test_cli_reports_gh_failure_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_load() -> Board:
        raise GhError("gh repo view\nnot a git repository")

    monkeypatch.setattr("board.cli.load_board", failing_load)
    result = CliRunner().invoke(app)
    assert result.exit_code == 1
    assert "not a git repository" in result.output
