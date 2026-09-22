from __future__ import annotations

from rich.console import Console
from rich.text import Text
from rich.tree import Tree

from board.model import (
    Board,
    Issue,
    ParentNode,
    blocker_status,
    direct_blockers,
    short,
    unblock_count,
)


def _lbl(issue: Issue) -> str:
    keep = [
        lb
        for lb in issue.labels
        if lb.startswith(("ready", "wayfinder", "debt", "P", "bug", "enhancement"))
    ]
    return ",".join(keep)


_BLOCKER_STYLE = {
    "takeable": "green",
    "claimed": "yellow",
    "blocked": "red",
}


def _blocker_line(issue: Issue, parent: ParentNode) -> Text:
    blockers = direct_blockers(issue.number, parent.edges)
    if not blockers:
        return Text()
    line = Text("  <- ", style="dim")
    for i, b in enumerate(blockers):
        if i:
            line.append(", ", style="dim")
        line.append(f"#{b}", style=_BLOCKER_STYLE[blocker_status(b, parent)])
    return line


def _ticket_line(issue: Issue, *, kind: str, parent: ParentNode | None = None) -> Text:
    t = Text()
    color = {"takeable": "green", "claimed": "yellow", "blocked": "red"}[kind]
    t.append(f"#{issue.number}  ", style=color)
    t.append(short(issue.title, 52))
    extra = Text()
    if kind == "takeable" and parent is not None:
        u = unblock_count(issue.number, parent.blocks)
        labs = _lbl(issue)
        if labs:
            extra.append(f"  {labs}", style="dim")
        if u:
            extra.append(f"  unblocks {u}", style="dim")
    elif kind == "claimed":
        who = issue.assignee or "?"
        extra.append(f"  @{who}", style="yellow")
    elif kind == "blocked" and parent is not None:
        extra.append_text(_blocker_line(issue, parent))
    t.append(extra)
    return t


def _backlog_line(issue: Issue, *, show_labels: bool) -> Text:
    line = Text()
    claimed = _BLOCKER_STYLE["claimed"]
    line.append(f"#{issue.number}  ", style=claimed if issue.assignee else "")
    line.append(short(issue.title, 56))
    labs = _lbl(issue) if show_labels else ""
    if labs:
        line.append(f"  {labs}", style="dim")
    if issue.assignee:
        line.append(f"  @{issue.assignee}", style=claimed)
    return line


def _add_parent(tree: Tree, parent: ParentNode, title_style: str) -> None:
    head = Text()
    head.append(f"#{parent.issue.number}  ", style=title_style)
    head.append(short(parent.issue.title, 56))
    head.append(
        f"  {parent.issue.kids_completed}/{parent.issue.kids_total} done",
        style="dim",
    )
    node = tree.add(head)
    if parent.note:
        node.add(Text(parent.note, style="dim italic"))
    g = parent.group
    if g.takeable:
        sub = node.add(Text("TAKEABLE", style="bold green"))
        for issue in g.takeable:
            sub.add(_ticket_line(issue, kind="takeable", parent=parent))
    if g.claimed:
        sub = node.add(Text("CLAIMED", style="bold yellow"))
        for issue in g.claimed:
            sub.add(_ticket_line(issue, kind="claimed", parent=parent))
    if g.blocked:
        sub = node.add(Text("BLOCKED", style="bold red"))
        for issue in g.blocked:
            sub.add(_ticket_line(issue, kind="blocked", parent=parent))


def render_board(board: Board, console: Console | None = None) -> None:
    console = console or Console()
    if board.open_count == 0:
        console.print(f"[bold]{board.slug}[/bold] — no open issues")
        return

    console.print()
    console.print(f"[bold]{board.slug}[/bold] — {board.open_count} open")
    console.print()

    if board.maps:
        root = Tree(Text("WAYFINDING", style="bold cyan"))
        for p in board.maps:
            _add_parent(root, p, "magenta")
        console.print(root)
        console.print()

    if board.builds:
        root = Tree(Text("BUILD", style="bold cyan"))
        for p in board.builds:
            _add_parent(root, p, "blue")
        console.print(root)
        console.print()

    b = board.backlog
    groups = [
        ("P1", "bold bright_red", b.p1, True),
        ("P2 / debt", "bold dark_orange", b.p2_debt, True),
        ("ready-for-agent", "bold bright_green", b.ready, False),
        ("orphan wayfinder", "bold yellow", b.orphan_wayfinder, True),
        ("other", "dim", b.other, True),
    ]
    if any(issues for _, _, issues, _ in groups):
        root = Tree(Text("BACKLOG", style="bold cyan"))
        for name, style, issues, show_labels in groups:
            if issues:
                sub = root.add(Text(name, style=style))
                for issue in issues:
                    sub.add(_backlog_line(issue, show_labels=show_labels))
        console.print(root)
        console.print()
