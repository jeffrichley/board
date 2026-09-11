from __future__ import annotations

from rich.console import Console
from rich.tree import Tree
from rich.text import Text

from board.model import Board, Issue, ParentNode, blocker_chain, short, unblock_count


def _lbl(issue: Issue) -> str:
    keep = [
        lb
        for lb in issue.labels
        if lb.startswith(("ready", "wayfinder", "debt", "P", "bug", "enhancement"))
    ]
    return ",".join(keep)


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
        chain = blocker_chain(issue.number, parent.edges)
        if chain:
            extra.append(f"  {chain}", style="red dim")
    t.append(extra)
    return t


def _add_parent(tree: Tree, parent: ParentNode, title_style: str) -> None:
    head = Text()
    head.append(f"#{parent.issue.number}  ", style=title_style)
    head.append(short(parent.issue.title, 56))
    head.append(
        f"  {parent.issue.kids_completed}/{parent.issue.kids_total} done",
        style="dim",
    )
    node = tree.add(head)
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
    if b.p1 or b.p2_debt or b.ready or b.other:
        root = Tree(Text("BACKLOG", style="bold cyan"))
        if b.p1:
            sub = root.add(Text("P1", style="bold bright_red"))
            for issue in b.p1:
                line = Text(f"#{issue.number}  {short(issue.title, 56)}")
                labs = _lbl(issue)
                if labs:
                    line.append(f"  {labs}", style="dim")
                sub.add(line)
        if b.p2_debt:
            sub = root.add(Text("P2 / debt", style="bold dark_orange"))
            for issue in b.p2_debt:
                line = Text(f"#{issue.number}  {short(issue.title, 56)}")
                labs = _lbl(issue)
                if labs:
                    line.append(f"  {labs}", style="dim")
                sub.add(line)
        if b.ready:
            sub = root.add(Text("ready-for-agent", style="bold bright_green"))
            for issue in b.ready:
                sub.add(Text(f"#{issue.number}  {short(issue.title, 56)}"))
        if b.other:
            sub = root.add(Text("other", style="dim"))
            for issue in b.other:
                line = Text(f"#{issue.number}  {short(issue.title, 56)}")
                labs = _lbl(issue)
                if labs:
                    line.append(f"  {labs}", style="dim")
                sub.add(line)
        console.print(root)
        console.print()
