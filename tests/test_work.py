import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner
from typer.testing import Result as CliResult

from board.cli import app
from helpers import FakeRun

ROOT = "/repos/board"
WORKTREE = str(Path("/repos/board.worktrees/8"))
CLAUDE = shlex.join(
    ["claude", "--dangerously-skip-permissions", "/mattpocock-skills:implement 8"]
)

TMUX_V = ["tmux", "-V"]
CLAUDE_V = ["claude", "--version"]
TOPLEVEL = ["git", "rev-parse", "--show-toplevel"]
FETCH = ["git", "fetch", "origin"]
VERIFY = ["git", "rev-parse", "--verify", "origin/main"]
ADD = ["git", "worktree", "add", "--detach", WORKTREE, "origin/main"]
HAS_SESSION = ["tmux", "has-session", "-t", "board"]
NEW_SESSION = [
    *["tmux", "new-session", "-d", "-s", "board"],
    *["-n", "#8", "-c", WORKTREE, CLAUDE],
]
NEW_WINDOW = [
    *["tmux", "new-window", "-t", "board"],
    *["-n", "#8", "-c", WORKTREE, CLAUDE],
]
ATTACH = ["tmux", "attach-session", "-t", "board:#8"]
REMOVE = ["git", "worktree", "remove", "--force", WORKTREE]

World = dict[tuple[str, ...], tuple[int, str, str]]

TOOLS: World = {
    tuple(TMUX_V): (0, "tmux 3.4\n", ""),
    tuple(CLAUDE_V): (0, "2.0.0\n", ""),
}
REPO: World = {
    tuple(TOPLEVEL): (0, f"{ROOT}\n", ""),
    tuple(FETCH): (0, "", ""),
    tuple(VERIFY): (0, "abc123\n", ""),
    tuple(ADD): (0, "", ""),
}
RUNNING_SESSION: World = {
    tuple(HAS_SESSION): (0, "", ""),
    tuple(NEW_WINDOW): (0, "", ""),
    tuple(ATTACH): (0, "", ""),
}
NO_SESSION: World = {
    tuple(HAS_SESSION): (1, "", "no server running"),
    tuple(NEW_SESSION): (0, "", ""),
    tuple(ATTACH): (0, "", ""),
}


def _work(run: FakeRun, monkeypatch: pytest.MonkeyPatch, *args: str) -> CliResult:
    monkeypatch.setattr("board.cli.default_runner", run)
    return CliRunner().invoke(app, ["work", *(args or ("8",))])


def test_work_makes_the_worktree_then_the_tmux_session_then_attaches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **REPO, **NO_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert run.calls == [
        TMUX_V,
        CLAUDE_V,
        TOPLEVEL,
        FETCH,
        VERIFY,
        ADD,
        HAS_SESSION,
        NEW_SESSION,
        ATTACH,
    ]


def test_work_opens_a_window_when_the_repo_session_is_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **REPO, **RUNNING_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert run.calls == [
        TMUX_V,
        CLAUDE_V,
        TOPLEVEL,
        FETCH,
        VERIFY,
        ADD,
        HAS_SESSION,
        NEW_WINDOW,
        ATTACH,
    ]


def test_work_attaches_without_capturing_the_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **REPO, **RUNNING_SESSION})
    _work(run, monkeypatch)

    assert run.captures[-1] is False
    assert all(run.captures[:-1])


def test_work_reports_a_missing_tmux_before_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({tuple(TMUX_V): (127, "", "command not found: tmux")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "tmux" in result.output
    assert run.calls == [TMUX_V]


def test_work_reports_a_missing_claude_before_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, tuple(CLAUDE_V): (127, "", "command not found: claude")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "claude" in result.output
    assert run.calls == [TMUX_V, CLAUDE_V]


def test_work_reports_a_missing_origin_main_before_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **REPO, tuple(VERIFY): (128, "", "unknown revision")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "origin/main" in result.output
    assert ADD not in run.calls


def test_work_reports_a_failed_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun({**TOOLS, **REPO, tuple(FETCH): (128, "", "no remote named origin")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "no remote named origin" in result.output


def test_work_reports_a_failed_worktree_add(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun({**TOOLS, **REPO, tuple(ADD): (128, "", "directory already exists")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "directory already exists" in result.output


def test_work_puts_the_worktree_back_when_the_tmux_window_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **REPO,
            **RUNNING_SESSION,
            tuple(NEW_WINDOW): (1, "", "can't find session: board"),
            tuple(REMOVE): (0, "", ""),
        }
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "can't find session" in result.output
    assert run.calls[-1] == REMOVE
    assert ATTACH not in run.calls


def test_work_says_so_when_a_tool_is_on_path_but_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({tuple(TMUX_V): (1, "", "dyld: library not loaded")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "not on PATH" not in result.output
    assert "library not loaded" in result.output
