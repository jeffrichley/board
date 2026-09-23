import shlex
from typing import Any

import pytest
from typer.testing import Result as CliResult

from helpers import (
    FETCH,
    OPEN_ISSUES,
    REPO_VIEW,
    FakeRun,
    World,
    gh_world,
    invoke,
    porcelain,
    raw_issue,
    tree,
)

ROOT = "/repos/board"
WORKTREE = tree(8)
CLAUDE = shlex.join(
    ["claude", "--dangerously-skip-permissions", "/mattpocock-skills:implement 8"]
)

TMUX_V = ["tmux", "-V"]
CLAUDE_V = ["claude", "--version"]
TOPLEVEL = ["git", "rev-parse", "--show-toplevel"]
WORKTREES = ["git", "worktree", "list", "--porcelain"]
VERIFY = ["git", "rev-parse", "--verify", "--short", "origin/main"]
# What the base has that the checkout's `main` doesn't.
NEW_SINCE = ["git", "rev-list", "--count", "main..origin/main"]
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
MAIN_ONLY = porcelain()
WITH_8 = porcelain(tree(8))
# A clone with no worktree for the ticket yet.
CHECKOUT: World = {
    tuple(TOPLEVEL): (0, f"{ROOT}\n", ""),
    tuple(WORKTREES): (0, MAIN_ONLY, ""),
}
# A fetched origin/main at 892179c, level with the checkout's `main`.
BASE: World = {
    tuple(FETCH): (0, "", ""),
    tuple(VERIFY): (0, "892179c\n", ""),
    tuple(NEW_SINCE): (0, "0\n", ""),
}
# What a started ticket says under its line, aligned beneath "started".
FROM = "from origin/main @ 892179c"
REPO: World = {**CHECKOUT, **BASE, tuple(ADD): (0, "", "")}
RUNNING_SESSION: World = {
    tuple(HAS_SESSION): (0, "", ""),
    tuple(NEW_WINDOW): (0, "", ""),
}
NO_SESSION: World = {
    tuple(HAS_SESSION): (1, "", "no server running"),
    tuple(NEW_SESSION): (0, "", ""),
}


def _work(
    run: FakeRun,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    typed: str | None = None,
) -> CliResult:
    return invoke(run, monkeypatch, "work", *(args or ("8",)), typed=typed)


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
        NEW_SINCE,
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
        NEW_SINCE,
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
    assert result.output == f"{_line(8, 'started')}\n"


def test_work_does_the_same_from_inside_tmux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1234,0")
    run = FakeRun({**TOOLS, **TICKET, **REPO, **RUNNING_SESSION})
    result = _work(run, monkeypatch)

    assert result.exit_code == 0
    assert result.output == f"{_line(8, 'started')}\n"
    assert run.calls[-1] == NEW_WINDOW


def test_work_says_how_far_the_checkout_is_behind_the_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {**TOOLS, **TICKET, **REPO, **RUNNING_SESSION, tuple(NEW_SINCE): (0, "2\n", "")}
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(8, 'started')} (2 new since your checkout)\n"


@pytest.mark.parametrize(
    "counted",
    [(128, "", "fatal: ambiguous argument 'main..origin/main'"), (0, "?\n", "")],
    ids=["no local main", "an unreadable count"],
)
def test_work_reports_the_base_without_a_count_it_cannot_work_out(
    monkeypatch: pytest.MonkeyPatch, counted: tuple[int, str, str]
) -> None:
    run = FakeRun(
        {**TOOLS, **TICKET, **REPO, **RUNNING_SESSION, tuple(NEW_SINCE): counted}
    )
    result = _work(run, monkeypatch)

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(8, 'started')}\n"


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
    new_session = _opens(number, start, ["tmux", "new-session", "-d", "-s", "board"])
    world: World = {
        **CHECKOUT,
        **BASE,
        tuple(_add(number)): (0, "", ""),
        tuple(HAS_SESSION): (1, "", "no server running"),
        tuple(new_session): (0, "", ""),
    }
    return world, new_session


def _looked_only(run: FakeRun) -> bool:
    """Board checked its tools, the clone and the tickets, and created nothing."""
    reads = (TMUX_V, CLAUDE_V, TOPLEVEL, WORKTREES)
    return all(c in reads or c[0] == "gh" for c in run.calls)


def _board(*swapped: dict[str, Any]) -> World:
    """A map #10 with children #11 and #12, a spec #20 with children #21 and #22,
    a backlog ticket #30, and an orphan wayfinder ticket #40.

    Each of `swapped` replaces the ticket with its number.
    """
    tickets = {
        n: raw_issue(n, *labels)
        for n, labels in [
            (10, ["wayfinder:map"]),
            (11, ["wayfinder:grilling"]),
            (12, ["wayfinder:grilling"]),
            (20, []),
            (21, []),
            (22, []),
            (30, []),
            (40, ["wayfinder:grilling"]),
        ]
    }
    tickets.update({t["number"]: t for t in swapped})
    return gh_world(*tickets.values(), children={10: [11, 12], 20: [21, 22]})


BOARD: World = _board()


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
    world = gh_world(raw_issue(6), raw_issue(7), raw_issue(8), blockers={8: [7, 6, 5]})
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


def _opens(number: int, start: str, where: list[str]) -> list[str]:
    """The tmux call that opens #number's window, `where` saying in what."""
    claude = shlex.join(["claude", "--dangerously-skip-permissions", start])
    return [*where, *["-n", f"#{number}", "-c", tree(number), claude]]


def _window(number: int) -> list[str]:
    """The window board opens for backlog ticket #number in the running session."""
    start = f"/mattpocock-skills:implement {number}"
    return _opens(number, start, ["tmux", "new-window", "-t", "=board"])


def _add(number: int) -> list[str]:
    return ["git", "worktree", "add", "--detach", tree(number), "origin/main"]


def _batch(*tickets: int | tuple[int, str]) -> World:
    """A clone and a running repo session in which each ticket can start.

    A ticket is a backlog ticket's number, or a (number, starting command) pair.
    """
    world: World = {
        **CHECKOUT,
        **BASE,
        tuple(HAS_SESSION): (0, "", ""),
    }
    for t in tickets:
        n, start = (
            t if isinstance(t, tuple) else (t, f"/mattpocock-skills:implement {t}")
        )
        world[tuple(_add(n))] = (0, "", "")
        world[tuple(_opens(n, start, ["tmux", "new-window", "-t", "=board"]))] = (
            0,
            "",
            "",
        )
    return world


def _line(number: int, status: str) -> str:
    """What board says about #number; a started one says its base on a second line."""
    where = f"#{number}  {status} in {tree(number)}   tmux board:#{number}"
    indent = " " * len(f"#{number}  ")
    return f"{where}\n{indent}{FROM}" if status == "started" else where


def test_work_on_several_tickets_starts_each_and_says_where_each_one_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **_batch(8, 9), **gh_world(raw_issue(8), raw_issue(9))})
    result = _work(run, monkeypatch, "8", "9")

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(8, 'started')}\n{_line(9, 'started')}\n"


def test_work_on_a_mixed_batch_starts_what_it_can_and_skips_the_rest_with_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #8 already has a live session, #9 can start, #6 is claimed, #7 is blocked.
    tickets = gh_world(
        raw_issue(5),
        raw_issue(6, assignee="alice"),
        raw_issue(7),
        raw_issue(9),
        blockers={7: [5]},
    )
    run = FakeRun({**TOOLS, **_batch(9), **tickets, **STARTED, **WINDOW_ALIVE})
    result = _work(run, monkeypatch, "8", "9", "6", "7")

    assert result.exit_code == 1
    assert _line(8, "running") in result.output
    assert _line(9, "started") in result.output
    assert "#6 is claimed by @alice." in result.output
    assert "#7 is blocked by #5." in result.output
    assert _add(6) not in run.calls
    assert _add(7) not in run.calls


def test_work_reports_no_base_for_a_session_it_went_back_to_beside_one_it_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #8's worktree was cut when its session began, not from this call's fetch.
    run = FakeRun(
        {
            **TOOLS,
            **_batch(9),
            **gh_world(raw_issue(9)),
            **STARTED,
            **WINDOW_GONE,
            **REOPENS,
        }
    )
    result = _work(run, monkeypatch, "8", "9")

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(8, 'resumed')}\n{_line(9, 'started')}\n"


def test_work_on_a_batch_skips_a_ticket_whose_worktree_fails_and_starts_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **_batch(8, 9),
            **gh_world(raw_issue(8), raw_issue(9)),
            tuple(_add(8)): (128, "", "directory already exists"),
        }
    )
    result = _work(run, monkeypatch, "8", "9")

    assert result.exit_code == 1
    assert "directory already exists" in result.output
    assert _line(9, "started") in result.output


def test_work_on_a_batch_looks_at_the_board_and_fetches_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **_batch(7, 8, 9),
            **gh_world(raw_issue(7), raw_issue(8), raw_issue(9)),
        }
    )
    result = _work(run, monkeypatch, "7", "8", "9")

    assert result.exit_code == 0, result.output
    assert run.calls.count(FETCH) == 1
    assert run.calls.count(OPEN_ISSUES) == 1


def test_work_on_a_batch_does_not_fetch_when_nothing_in_it_can_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = gh_world(raw_issue(6, assignee="alice"), raw_issue(7, assignee="bob"))
    run = FakeRun({**TOOLS, **CHECKOUT, **claimed})
    result = _work(run, monkeypatch, "6", "7")

    assert result.exit_code == 1
    assert _looked_only(run)


def test_work_on_a_ticket_named_twice_starts_it_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **_batch(8), **gh_world(raw_issue(8))})
    result = _work(run, monkeypatch, "8", "8")

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(8, 'started')}\n"


def test_work_on_a_batch_attaches_to_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1234,0")
    run = FakeRun(
        {
            **TOOLS,
            **_batch(9),
            **gh_world(raw_issue(9)),
            **STARTED,
            **WINDOW_GONE,
            **REOPENS,
        }
    )
    result = _work(run, monkeypatch, "8", "9")

    assert result.exit_code == 0, result.output
    verbs = {c[1] for c in run.calls if c[0] == "tmux"}
    assert not verbs & {"attach-session", "attach", "switch-client"}


def test_work_on_a_batch_opens_the_repo_session_for_the_first_ticket_and_joins_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _opens(
        8,
        "/mattpocock-skills:implement 8",
        ["tmux", "new-session", "-d", "-s", "board"],
    )
    run = FakeRun(
        {
            **TOOLS,
            **_batch(8, 9),
            **gh_world(raw_issue(8), raw_issue(9)),
            tuple(HAS_SESSION): [(1, "", "no server running"), (0, "", "")],
            tuple(first): (0, "", ""),
        }
    )
    result = _work(run, monkeypatch, "8", "9")

    assert result.exit_code == 0, result.output
    opened = [c for c in run.calls if c[1] in ("new-session", "new-window")]
    assert opened == [first, _window(9)]


MAP_11 = (11, "/mattpocock-skills:wayfinder 10 11")
MAP_12 = (12, "/mattpocock-skills:wayfinder 10 12")
ASKS = "[y/N]"


def test_work_asks_before_a_second_session_on_a_map_whose_child_has_a_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **_board(),
            **_batch(MAP_12),
            tuple(WORKTREES): (0, porcelain(tree(11)), ""),
        }
    )
    result = _work(run, monkeypatch, "12", typed="y\n")

    assert result.exit_code == 0, result.output
    assert "Map #10 already has work in progress: #11 has a worktree." in result.output
    assert ASKS in result.output
    assert _line(12, "started") in result.output


def test_work_asks_before_a_session_on_a_map_whose_child_is_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _board(raw_issue(11, assignee="alice"))
    run = FakeRun({**TOOLS, **world, **_batch(MAP_12)})
    result = _work(run, monkeypatch, "12", typed="y\n")

    assert result.exit_code == 0, result.output
    assert "#11 is claimed by @alice" in result.output
    assert _line(12, "started") in result.output


def test_work_asks_before_a_session_on_a_map_itself_while_a_child_has_a_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = (10, "/mattpocock-skills:wayfinder 10")
    run = FakeRun(
        {
            **TOOLS,
            **_board(),
            **_batch(start),
            tuple(WORKTREES): (0, porcelain(tree(12)), ""),
        }
    )
    result = _work(run, monkeypatch, "10", typed="y\n")

    assert result.exit_code == 0, result.output
    assert "#12 has a worktree" in result.output
    assert _line(10, "started") in result.output


def test_work_asks_before_the_second_of_two_tickets_in_one_call_on_the_same_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **_board(), **_batch(MAP_11, MAP_12)})
    result = _work(run, monkeypatch, "11", "12", typed="y\n")

    assert result.exit_code == 0, result.output
    assert result.output.count(ASKS) == 1
    assert "#11 is starting in this call" in result.output
    assert _line(11, "started") in result.output
    assert _line(12, "started") in result.output


@pytest.mark.parametrize("typed", ["n\n", "\n"], ids=["n", "enter"])
def test_work_skips_the_second_session_on_a_map_unless_you_say_yes(
    monkeypatch: pytest.MonkeyPatch, typed: str
) -> None:
    run = FakeRun({**TOOLS, **CHECKOUT, **_board(raw_issue(11, assignee="alice"))})
    result = _work(run, monkeypatch, "12", typed=typed)

    assert result.exit_code == 1
    assert (
        "#12  skipped: map #10 already has work in progress: "
        "#11 is claimed by @alice." in result.output
    )
    assert _looked_only(run)


def test_work_on_a_batch_skips_only_the_ticket_you_said_no_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **_board(), **_batch(MAP_11)})
    result = _work(run, monkeypatch, "11", "12", typed="n\n")

    assert result.exit_code == 1
    assert _line(11, "started") in result.output
    assert "#12  skipped: map #10 already has work in progress" in result.output
    assert _add(12) not in run.calls


def test_work_with_yes_starts_a_second_session_on_a_map_without_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **_board(),
            **_batch(MAP_12),
            tuple(WORKTREES): (0, porcelain(tree(11)), ""),
        }
    )
    result = _work(run, monkeypatch, "--yes", "12")

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(12, 'started')}\n"


@pytest.mark.parametrize(
    ("numbers", "starts"),
    [
        ((21, 22), [(21, "/mattpocock-skills:implement 21")]),
        ((30,), [(30, "/mattpocock-skills:implement 30")]),
    ],
    ids=["a spec's child", "a backlog ticket"],
)
def test_work_never_asks_about_spec_children_or_backlog_tickets(
    monkeypatch: pytest.MonkeyPatch,
    numbers: tuple[int, ...],
    starts: list[tuple[int, str]],
) -> None:
    # #22 is #21's sibling under spec #20, and already has a worktree.
    listing = (0, porcelain(tree(22)), "")
    run = FakeRun(
        {
            **TOOLS,
            **_board(raw_issue(22, assignee="alice")),
            **_batch(*starts),
            tuple(WORKTREES): listing,
            tuple(LIST_WINDOWS): (0, "#22\n", ""),
        }
    )
    result = _work(run, monkeypatch, *(str(n) for n in numbers))

    assert result.exit_code == 0, result.output
    assert ASKS not in result.output


def test_work_asks_before_a_session_on_a_map_child_while_the_map_has_a_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **BOARD,
            **_batch(MAP_12),
            tuple(WORKTREES): (0, porcelain(tree(10)), ""),
        }
    )
    result = _work(run, monkeypatch, "12", typed="y\n")

    assert result.exit_code == 0, result.output
    assert "Map #10 already has work in progress: #10 has a worktree." in result.output


def test_work_does_not_ask_because_the_map_itself_is_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A map is often assigned to its owner for as long as it's open.
    world = _board(raw_issue(10, "wayfinder:map", assignee="alice"))
    run = FakeRun({**TOOLS, **world, **_batch(MAP_12)})
    result = _work(run, monkeypatch, "12")

    assert result.exit_code == 0, result.output
    assert ASKS not in result.output


def test_work_on_a_range_starts_its_open_tickets_and_says_nothing_of_the_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #31 and #34 are PRs or closed issues, #33 was never made: none is open.
    open_ = [30, 32, 35]
    run = FakeRun({**TOOLS, **_batch(*open_), **gh_world(*map(raw_issue, open_))})
    result = _work(run, monkeypatch, "30-35")

    assert result.exit_code == 0, result.output
    assert result.output == "".join(f"{_line(n, 'started')}\n" for n in open_)


def test_work_on_a_range_of_one_number_starts_that_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **_batch(30), **gh_world(raw_issue(30))})
    result = _work(run, monkeypatch, "30-30")

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(30, 'started')}\n"


@pytest.mark.parametrize(
    "args",
    [("33", "30-35"), ("30-35", "34-40"), ("30", "30-34", "34")],
    ids=["a number inside a range", "overlapping ranges", "numbers at the ends"],
)
def test_work_on_ranges_and_numbers_together_starts_each_ticket_once(
    monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...]
) -> None:
    open_ = [30, 33, 34]
    run = FakeRun({**TOOLS, **_batch(*open_), **gh_world(*map(raw_issue, open_))})
    result = _work(run, monkeypatch, *args)

    assert result.exit_code == 0, result.output
    started = [c[-2] for c in run.calls if c[:3] == ["git", "worktree", "add"]]
    assert sorted(started) == [tree(n) for n in open_]
    assert run.calls.count(OPEN_ISSUES) == 1


def test_work_on_a_range_skips_a_ticket_that_cannot_start_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tickets = gh_world(
        raw_issue(5), raw_issue(6, assignee="alice"), raw_issue(7), blockers={7: [5]}
    )
    run = FakeRun({**TOOLS, **_batch(5), **tickets})
    result = _work(run, monkeypatch, "5-7")

    assert result.exit_code == 1
    assert _line(5, "started") in result.output
    assert "#6 is claimed by @alice." in result.output
    assert "#7 is blocked by #5." in result.output
    assert _add(6) not in run.calls
    assert _add(7) not in run.calls


def test_work_on_a_range_goes_back_to_a_ticket_that_has_a_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(
        {
            **TOOLS,
            **_batch(9),
            **gh_world(raw_issue(8), raw_issue(9)),
            **STARTED,
            **WINDOW_ALIVE,
        }
    )
    result = _work(run, monkeypatch, "8-9")

    assert result.exit_code == 0, result.output
    assert result.output == f"{_line(8, 'running')}\n{_line(9, 'started')}\n"


def test_work_on_a_range_with_no_open_tickets_says_so_and_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **CHECKOUT, **BOARD})
    result = _work(run, monkeypatch, "300-305")

    assert result.exit_code == 1
    assert "no open tickets in 300-305" in result.output
    assert _looked_only(run)


def test_work_says_which_range_was_empty_and_still_starts_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun({**TOOLS, **_batch(8), **gh_world(raw_issue(8))})
    result = _work(run, monkeypatch, "8", "300-305")

    assert result.exit_code == 1
    assert "no open tickets in 300-305" in result.output
    assert _line(8, "started") in result.output


@pytest.mark.parametrize(
    ("arg", "reason"),
    [
        ("35-30", "35-30 runs backwards"),
        ("30-", "30- has no end"),
        ("thirty", "thirty is not a ticket number"),
    ],
    ids=["reversed", "open-ended", "not a number"],
)
def test_work_refuses_what_is_neither_a_ticket_nor_a_range_before_calling_anything(
    monkeypatch: pytest.MonkeyPatch, arg: str, reason: str
) -> None:
    run = FakeRun({})
    result = _work(run, monkeypatch, "8", arg)

    assert result.exit_code == 2
    assert reason in result.output
    assert run.calls == []
