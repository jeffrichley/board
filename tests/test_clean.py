import json
from pathlib import Path

import pytest
from typer.testing import Result as CliResult

from helpers import FETCH, REPO_VIEW, SLUG, FakeRun, World, invoke

LIST = ["git", "worktree", "list", "--porcelain"]
WINDOWS = ["tmux", "list-windows", "-t", "=board", "-F", "#{window_name}"]


def _porcelain(*paths: str) -> str:
    """`git worktree list --porcelain` for the main checkout and these worktrees."""
    main = "worktree /repos/board\nHEAD abc\nbranch refs/heads/main\n\n"
    rest = "".join(f"worktree {p}\nHEAD def\ndetached\n\n" for p in paths)
    return main + rest


def _tree(name: int | str) -> str:
    return str(Path(f"/repos/board.worktrees/{name}"))


def _status(name: int | str) -> list[str]:
    return ["git", "-C", _tree(name), "status", "--porcelain"]


def _unpushed(name: int | str) -> list[str]:
    return ["git", "-C", _tree(name), "rev-list", "HEAD", "--not", "--remotes"]


def _remove(name: int | str) -> list[str]:
    return ["git", "worktree", "remove", _tree(name)]


def _issue(number: int) -> list[str]:
    return ["gh", "api", f"repos/{SLUG}/issues/{number}"]


def _world(
    *numbers: int,
    open_: tuple[int, ...] = (),
    dirty: tuple[int, ...] = (),
    unpushed: tuple[int, ...] = (),
    windows: tuple[int, ...] = (),
) -> World:
    """A repo with a worktree per number, each safe unless named otherwise."""
    world: World = {
        tuple(LIST): (
            0,
            _porcelain(*(f"/repos/board.worktrees/{n}" for n in numbers)),
            "",
        ),
        tuple(FETCH): (0, "", ""),
        tuple(REPO_VIEW): (0, json.dumps({"nameWithOwner": SLUG}), ""),
        tuple(WINDOWS): (0, "".join(f"#{n}\n" for n in windows), ""),
    }
    for n in numbers:
        state = "open" if n in open_ else "closed"
        world[tuple(_issue(n))] = (0, json.dumps({"state": state}), "")
        world[tuple(_status(n))] = (0, " M a.py\n" if n in dirty else "", "")
        world[tuple(_unpushed(n))] = (0, "fed123\n" if n in unpushed else "", "")
        world[tuple(_remove(n))] = (0, "", "")
    return world


def _clean(run: FakeRun, monkeypatch: pytest.MonkeyPatch) -> CliResult:
    return invoke(run, monkeypatch, "clean")


def test_clean_removes_the_worktree_of_a_finished_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(_world(8))
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert run.calls[-1] == _remove(8)
    assert "#8" in result.output
    assert "removed" in result.output


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ({"open_": (8,)}, "ticket still open"),
        ({"dirty": (8,)}, "uncommitted changes"),
        ({"unpushed": (8,)}, "unpushed commits"),
        ({"windows": (8,)}, "session still running"),
    ],
    ids=["open ticket", "dirty", "unpushed", "live window"],
)
def test_clean_keeps_a_worktree_that_fails_a_condition_and_says_why(
    monkeypatch: pytest.MonkeyPatch, setup: dict[str, tuple[int, ...]], reason: str
) -> None:
    run = FakeRun(_world(8, **setup))
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert _remove(8) not in run.calls
    assert "#8" in result.output
    assert reason in result.output


def test_clean_names_every_reason_a_worktree_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(_world(8, open_=(8,), dirty=(8,), unpushed=(8,), windows=(8,)))
    result = _clean(run, monkeypatch)

    for reason in [
        "ticket still open",
        "uncommitted changes",
        "unpushed commits",
        "session still running",
    ]:
        assert reason in result.output


def test_clean_judges_each_worktree_on_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(_world(8, 9, open_=(9,)))
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert _remove(8) in run.calls
    assert _remove(9) not in run.calls


def test_clean_with_no_worktrees_says_so_and_asks_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({tuple(LIST): (0, _porcelain(), "")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0
    assert "no worktrees" in result.output.lower()
    assert run.calls == [LIST]


def test_clean_leaves_worktrees_board_did_not_make_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({tuple(LIST): (0, _porcelain("/elsewhere/spike"), "")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0
    assert run.calls == [LIST]


def test_clean_counts_no_tmux_server_as_no_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**_world(8), tuple(WINDOWS): (1, "", "no server running")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert run.calls[-1] == _remove(8)


def test_clean_reports_a_failed_removal_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**_world(8), tuple(_remove(8)): (128, "", "is locked")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 1
    assert "is locked" in result.output


def test_clean_reports_a_failed_fetch_before_removing_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**_world(8), tuple(FETCH): (128, "", "no remote named origin")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 1
    assert "no remote named origin" in result.output
    assert _remove(8) not in run.calls


def test_clean_reports_a_failed_gh_before_removing_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**_world(8), tuple(REPO_VIEW): (1, "", "gh: not logged in")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 1
    assert "not logged in" in result.output
    assert _remove(8) not in run.calls
    assert _issue(8) not in run.calls


def test_clean_keeps_a_worktree_whose_ticket_it_cannot_find(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**_world(8), tuple(_issue(8)): (1, "", "HTTP 404: Not Found")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert _remove(8) not in run.calls
    assert "ticket not found" in result.output


def test_clean_keeps_a_worktree_git_cannot_read_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **_world(8),
            tuple(_status(8)): (128, "", "not a git repository"),
            tuple(_unpushed(8)): (128, "", "not a git repository"),
        }
    )
    result = _clean(run, monkeypatch)

    assert _remove(8) not in run.calls
    assert "could not read git status" in result.output
    assert "could not check for unpushed commits" in result.output
    assert "uncommitted changes" not in result.output


def test_clean_keeps_a_worktree_not_named_for_a_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world: World = {
        tuple(LIST): (0, _porcelain("/repos/board.worktrees/spike"), ""),
        tuple(FETCH): (0, "", ""),
        tuple(WINDOWS): (1, "", "no server running"),
        tuple(_status("spike")): (0, "", ""),
        tuple(_unpushed("spike")): (0, "", ""),
    }
    run = FakeRun(world)
    result = _clean(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "not named for a ticket" in result.output


def test_clean_reports_a_failed_worktree_list(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun({tuple(LIST): (128, "", "not a git repository")})
    result = _clean(run, monkeypatch)

    assert result.exit_code == 1
    assert "not a git repository" in result.output
