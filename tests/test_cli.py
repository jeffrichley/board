import pytest

from helpers import REPO_VIEW, FakeRun, gh_world, invoke, raw_issue

# Bare `board` and `board show` are one command reached two ways.
ENTRY_POINTS = pytest.mark.parametrize("args", [[], ["show"]], ids=["bare", "show"])


@ENTRY_POINTS
def test_board_renders_empty_board(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = invoke(FakeRun(gh_world()), monkeypatch, *args)
    assert result.exit_code == 0
    assert "o/r — no open issues" in result.stdout


@ENTRY_POINTS
def test_board_renders_open_tickets(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = invoke(FakeRun(gh_world(raw_issue(7))), monkeypatch, *args)
    assert result.exit_code == 0
    assert "o/r — 1 open" in result.stdout
    assert "issue 7" in result.stdout


def test_bare_board_and_board_show_print_the_same_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = gh_world(raw_issue(7, "ready-for-agent"), raw_issue(8, "P1"))
    bare = invoke(FakeRun(world), monkeypatch)
    show = invoke(FakeRun(world), monkeypatch, "show")
    assert (bare.exit_code, bare.output) == (show.exit_code, show.output)


@ENTRY_POINTS
def test_board_reports_gh_failure_and_exits_nonzero(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = FakeRun({tuple(REPO_VIEW): (1, "", "not a git repository")})
    result = invoke(run, monkeypatch, *args)
    assert result.exit_code == 1
    assert "not a git repository" in result.output


def test_board_help_lists_show_as_the_default_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(FakeRun({}), monkeypatch, "--help")
    assert result.exit_code == 0
    assert "show" in result.output
    assert "(default)" in result.output
    # Listed first, ahead of the commands that act on tickets.
    assert result.output.index("show") < result.output.index("work")


def test_board_show_help_describes_the_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(FakeRun({}), monkeypatch, "show", "--help")
    assert result.exit_code == 0
    assert "show [OPTIONS]" in result.output
    assert "wayfinding / specs / backlog board" in result.output
