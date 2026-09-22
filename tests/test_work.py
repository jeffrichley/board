import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner
from typer.testing import Result as CliResult

from board.cli import app
from helpers import OPEN_ISSUES, REPO_VIEW, FakeRun, World, gh_world, raw_issue

ROOT = "/repos/board"
WORKTREE = str(Path("/repos/board.worktrees/8"))
CLAUDE = shlex.join(
    ["claude", "--dangerously-skip-permissions", "/mattpocock-skills:implement 8"]
)

TMUX_V = ["tmux", "-V"]
CLAUDE_V = ["claude", "--version"]
TOPLEVEL = ["git", "rev-parse", "--show-toplevel"]
WORKTREES = ["git", "worktree", "list", "--porcelain"]
FETCH = ["git", "fetch", "origin"]
VERIFY = ["git", "rev-parse", "--verify", "origin/main"]
ADD = ["git", "worktree", "add", "--detach", WORKTREE, "origin/main"]
# `=board`, so a sibling repo's `board-web` session is never taken for this one.
HAS_SESSION = ["tmux", "has-session", "-t", "=board"]
NEW_SESSION = [
    *["tmux", "new-session", "-d", "-s", "board"],
    *["-n", "#8", "-c", WORKTREE, CLAUDE],
]
NEW_WINDOW = [
    *["tmux", "new-window", "-t", "=board"],
    *["-n", "#8", "-c", WORKTREE, CLAUDE],
]
REMOVE = ["git", "worktree", "remove", "--force", WORKTREE]
LIST_WINDOWS = ["tmux", "list-windows", "-t", "=board", "-F", "#{window_name}"]
CONTINUE = shlex.join(["claude", "--dangerously-skip-permissions", "--continue"])
RESUME_WINDOW = [
    *["tmux", "new-window", "-t", "=board"],
    *["-n", "#8", "-c", WORKTREE, CONTINUE],
]
RESUME_SESSION = [
    *["tmux", "new-session", "-d", "-s", "board"],
    *["-n", "#8", "-c", WORKTREE, CONTINUE],
]

TOOLS: World = {
    tuple(TMUX_V): (0, "tmux 3.4\n", ""),
    tuple(CLAUDE_V): (0, "2.0.0\n", ""),
}
# #8 as a plain backlog ticket: takeable, and started with /implement.
TICKET: World = gh_world(raw_issue(8, "ready-for-agent"))
LOOK = [REPO_VIEW, OPEN_ISSUES]
# git's own listing, as `git worktree list --porcelain` prints it.
MAIN_ONLY = f"worktree {ROOT}\nHEAD abc123\nbranch refs/heads/main\n\n"
WITH_8 = f"{MAIN_ONLY}worktree /repos/board.worktrees/8\nHEAD abc123\ndetached\n\n"
# A clone with no worktree for the ticket yet.
CHECKOUT: World = {
    tuple(TOPLEVEL): (0, f"{ROOT}\n", ""),
    tuple(WORKTREES): (0, MAIN_ONLY, ""),
}
REPO: World = {
    **CHECKOUT,
    tuple(FETCH): (0, "", ""),
    tuple(VERIFY): (0, "abc123\n", ""),
    tuple(ADD): (0, "", ""),
}
RUNNING_SESSION: World = {
    tuple(HAS_SESSION): (0, "", ""),
    tuple(NEW_WINDOW): (0, "", ""),
}
NO_SESSION: World = {
    tuple(HAS_SESSION): (1, "", "no server running"),
    tuple(NEW_SESSION): (0, "", ""),
}


def _work(run: FakeRun, monkeypatch: pytest.MonkeyPatch, *args: str) -> CliResult:
    monkeypatch.setattr("board.cli.default_runner", run)
    return CliRunner().invoke(app, ["work", *(args or ("8",))])


def test_work_makes_the_worktree_then_the_tmux_session_and_stops_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **TICKET, **REPO, **NO_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert run.calls == [
        TMUX_V,
        CLAUDE_V,
        TOPLEVEL,
        WORKTREES,
        *LOOK,
        FETCH,
        VERIFY,
        ADD,
        HAS_SESSION,
        NEW_SESSION,
    ]


def test_work_opens_a_window_when_the_repo_session_is_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **TICKET, **REPO, **RUNNING_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert run.calls == [
        TMUX_V,
        CLAUDE_V,
        TOPLEVEL,
        WORKTREES,
        *LOOK,
        FETCH,
        VERIFY,
        ADD,
        HAS_SESSION,
        NEW_WINDOW,
    ]


def test_work_says_where_the_session_is_and_leaves_you_at_your_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **TICKET, **REPO, **RUNNING_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert result.output == f"#8  started in {WORKTREE}   tmux board:#8\n"


def test_work_does_the_same_from_inside_tmux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1234,0")
    run = FakeRun({**TOOLS, **TICKET, **REPO, **RUNNING_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert result.output == f"#8  started in {WORKTREE}   tmux board:#8\n"
    assert run.calls[-1] == NEW_WINDOW


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
    run = FakeRun(
        {**TOOLS, **TICKET, **REPO, tuple(VERIFY): (128, "", "unknown revision")}
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "origin/main" in result.output
    assert ADD not in run.calls


def test_work_reports_a_failed_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(
        {**TOOLS, **TICKET, **REPO, tuple(FETCH): (128, "", "no remote named origin")}
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "no remote named origin" in result.output


def test_work_reports_a_failed_worktree_add(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(
        {**TOOLS, **TICKET, **REPO, tuple(ADD): (128, "", "directory already exists")}
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "directory already exists" in result.output


def test_work_puts_the_worktree_back_when_the_tmux_window_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **TICKET,
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


def test_work_says_so_when_a_tool_is_on_path_but_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({tuple(TMUX_V): (1, "", "dyld: library not loaded")})
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "not on PATH" not in result.output
    assert "library not loaded" in result.output


def _launching(number: int, start: str) -> tuple[World, list[str]]:
    """The git and tmux world for starting #number, and the window it opens."""
    worktree = str(Path(f"/repos/board.worktrees/{number}"))
    claude = shlex.join(["claude", "--dangerously-skip-permissions", start])
    new_session = [
        *["tmux", "new-session", "-d", "-s", "board"],
        *["-n", f"#{number}", "-c", worktree, claude],
    ]
    world: World = {
        **CHECKOUT,
        tuple(FETCH): (0, "", ""),
        tuple(VERIFY): (0, "abc123\n", ""),
        ("git", "worktree", "add", "--detach", worktree, "origin/main"): (0, "", ""),
        tuple(HAS_SESSION): (1, "", "no server running"),
        tuple(new_session): (0, "", ""),
    }
    return world, new_session


def _looked_only(run: FakeRun) -> bool:
    """Board checked its tools, the clone and the tickets, and created nothing."""
    reads = (TMUX_V, CLAUDE_V, TOPLEVEL, WORKTREES)
    return all(c in reads or c[0] == "gh" for c in run.calls)


# A map #10 with children #11 and #12, a spec #20 with child #21, a backlog
# ticket #30, and an orphan wayfinder ticket #40.
BOARD: World = gh_world(
    raw_issue(10, "wayfinder:map"),
    raw_issue(11, "wayfinder:grilling"),
    raw_issue(12, "wayfinder:grilling"),
    raw_issue(20),
    raw_issue(21),
    raw_issue(30),
    raw_issue(40, "wayfinder:grilling"),
    children={10: [11, 12], 20: [21]},
)


@pytest.mark.parametrize(
    ("number", "start"),
    [
        (10, "/mattpocock-skills:wayfinder 10"),
        (11, "/mattpocock-skills:wayfinder 10 11"),
        (21, "/mattpocock-skills:implement 21"),
        (30, "/mattpocock-skills:implement 30"),
    ],
    ids=["a map", "a map's child", "a spec's child", "a backlog ticket"],
)
def test_work_starts_claude_with_the_command_for_where_the_ticket_sits(
    monkeypatch: pytest.MonkeyPatch, number: int, start: str
) -> None:
    launch, new_session = _launching(number, start)
    run = FakeRun({**TOOLS, **BOARD, **launch})
    result = _work(run, monkeypatch, str(number))

    assert result.exit_code == 0, result.output
    assert new_session in run.calls


@pytest.mark.parametrize(
    ("number", "reason"),
    [
        (20, "#20 is a spec: work its tickets instead."),
        (40, "there's no map to work it through"),
        (99, "#99 is not an open ticket"),
    ],
    ids=["a spec", "an orphan wayfinder ticket", "not an open ticket"],
)
def test_work_refuses_a_ticket_no_session_should_start_on(
    monkeypatch: pytest.MonkeyPatch, number: int, reason: str
) -> None:
    run = FakeRun({**TOOLS, **CHECKOUT, **BOARD})
    result = _work(run, monkeypatch, str(number))

    assert result.exit_code == 1
    assert reason in result.output
    assert _looked_only(run)


def test_work_refuses_a_claimed_ticket_naming_the_assignee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **CHECKOUT, **gh_world(raw_issue(8, assignee="alice"))})
    result = _work(run, monkeypatch, "8")

    assert result.exit_code == 1
    assert "#8 is claimed by @alice." in result.output
    assert _looked_only(run)


def test_work_refuses_a_blocked_ticket_naming_its_open_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #5 blocked #8 but is closed, so only #6 and #7 are named.
    world = gh_world(raw_issue(6), raw_issue(7), raw_issue(8), blockers={8: [5, 6, 7]})
    run = FakeRun({**TOOLS, **CHECKOUT, **world})
    result = _work(run, monkeypatch, "8")

    assert result.exit_code == 1
    assert "#8 is blocked by #6, #7." in result.output
    assert _looked_only(run)


def test_work_refuses_a_blocked_map_child_naming_its_open_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = gh_world(
        raw_issue(10, "wayfinder:map"),
        raw_issue(11),
        raw_issue(12),
        children={10: [11, 12]},
        blockers={12: [11]},
    )
    run = FakeRun({**TOOLS, **CHECKOUT, **world})
    result = _work(run, monkeypatch, "12")

    assert result.exit_code == 1
    assert "#12 is blocked by #11." in result.output
    assert _looked_only(run)


def test_work_reports_a_failed_gh_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun({**TOOLS, **CHECKOUT, tuple(REPO_VIEW): (1, "", "gh: not logged in")})
    result = _work(run, monkeypatch, "8")

    assert result.exit_code == 1
    assert "not logged in" in result.output
    assert _looked_only(run)


# #8 already has a worktree: someone ran `board work 8` before.
STARTED: World = {**CHECKOUT, tuple(WORKTREES): (0, WITH_8, "")}
WINDOW_ALIVE: World = {tuple(LIST_WINDOWS): (0, "#3\n#8\nzsh\n", "")}
WINDOW_GONE: World = {tuple(LIST_WINDOWS): (0, "#3\n#80\nzsh\n", "")}
REOPENS: World = {tuple(HAS_SESSION): (0, "", ""), tuple(RESUME_WINDOW): (0, "", "")}


def test_work_on_a_ticket_with_a_live_session_creates_nothing_and_says_where_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **STARTED, **WINDOW_ALIVE})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert result.output == f"#8  running in {WORKTREE}   tmux board:#8\n"
    assert run.calls == [TMUX_V, CLAUDE_V, TOPLEVEL, WORKTREES, LIST_WINDOWS]


def test_work_reopens_a_closed_window_continuing_the_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **STARTED,
            **WINDOW_GONE,
            **REOPENS,
        }
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert result.output == f"#8  resumed in {WORKTREE}   tmux board:#8\n"
    assert run.calls == [
        TMUX_V,
        CLAUDE_V,
        TOPLEVEL,
        WORKTREES,
        LIST_WINDOWS,
        HAS_SESSION,
        RESUME_WINDOW,
    ]


def test_work_reopens_the_repo_tmux_session_when_it_is_gone_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **STARTED,
            tuple(LIST_WINDOWS): (1, "", "can't find session: board"),
            tuple(HAS_SESSION): (1, "", "no server running"),
            tuple(RESUME_SESSION): (0, "", ""),
        }
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert run.calls[-1] == RESUME_SESSION


def test_work_keeps_the_worktree_when_reopening_its_window_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **STARTED,
            **WINDOW_GONE,
            tuple(HAS_SESSION): (0, "", ""),
            tuple(RESUME_WINDOW): (1, "", "server exited unexpectedly"),
        }
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 1
    assert "server exited unexpectedly" in result.output
    assert REMOVE not in run.calls


@pytest.mark.parametrize("inside_tmux", [False, True], ids=["outside", "inside"])
@pytest.mark.parametrize("window", [WINDOW_ALIVE, WINDOW_GONE], ids=["alive", "gone"])
def test_work_never_attaches_to_a_session_it_goes_back_to(
    monkeypatch: pytest.MonkeyPatch, window: World, inside_tmux: bool
) -> None:
    if inside_tmux:
        monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1234,0")
    run = FakeRun({**TOOLS, **STARTED, **window, **REOPENS})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    verbs = {c[1] for c in run.calls if c[0] == "tmux"}
    assert not verbs & {"attach-session", "attach", "switch-client"}


def test_work_resumes_a_claimed_ticket_that_has_a_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The agent claimed #8 after the first `board work 8`; going back is not
    # starting a second session, so the claim doesn't refuse it.
    claimed = gh_world(raw_issue(8, assignee="alice"))
    run = FakeRun({**TOOLS, **claimed, **STARTED, **WINDOW_ALIVE})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "claimed" not in result.output
    assert ADD not in run.calls
