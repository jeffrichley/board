import sys

from board.run import default_runner


def test_default_runner_captures_stdout_and_the_exit_code() -> None:
    r = default_runner([sys.executable, "-c", "print('hi'); raise SystemExit(3)"])

    assert r.returncode == 3
    assert r.stdout.strip() == "hi"


def test_default_runner_leaves_the_terminal_alone_when_not_capturing() -> None:
    r = default_runner([sys.executable, "-c", "pass"], capture=False)

    assert r.returncode == 0
    assert r.stdout == ""


def test_default_runner_reports_a_command_that_is_not_on_path() -> None:
    r = default_runner(["board-no-such-command"])

    assert r.returncode == 127
    assert "not found" in r.stderr
