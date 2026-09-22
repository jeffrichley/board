from rich.console import Console

from board.model import Backlog, Board, Issue, ParentNode, TicketGroup
from board.render import render_board


def _issue(n: int, title: str, *labels: str, assignee: str | None = None) -> Issue:
    return Issue(n, title, labels, assignee, 0, 0, 0)


def test_render_includes_lanes_and_colors():
    board = Board(
        slug="o/r",
        open_count=3,
        maps=[
            ParentNode(
                issue=Issue(10, "The Map", ("wayfinder:map",), None, 0, 1, 0),
                group=TicketGroup(
                    takeable=[_issue(11, "Do thing", "wayfinder:grilling")],
                    claimed=[],
                    blocked=[_issue(12, "Wait", "wayfinder:grilling")],
                ),
                edges={12: [11]},
                blocks={11: [12]},
            )
        ],
        builds=[],
        backlog=Backlog(p1=[_issue(20, "Fix", "debt", "P1")]),
    )
    console = Console(record=True, width=120, force_terminal=True)
    render_board(board, console=console)
    text = console.export_text(clear=False)
    assert "WAYFINDING" in text
    assert "#10" in text and "The Map" in text
    assert "TAKEABLE" in text and "#11" in text
    assert "BLOCKED" in text and "#12" in text
    assert "<- #11" in text
    assert "<- #11 <-" not in text  # no transitive tail
    assert "BACKLOG" in text and "P1" in text and "#20" in text
    html = console.export_html(clear=False)
    assert "WAYFINDING" in html
