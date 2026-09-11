from typer.testing import CliRunner

from board.cli import app


def test_cli_runs():
    result = CliRunner().invoke(app)
    assert result.exit_code == 0
    assert "not implemented" in result.stdout
