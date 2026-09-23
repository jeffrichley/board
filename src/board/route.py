"""Which command starts a session on a ticket, worked out from where it sits.

A ticket that isn't takeable, or sits somewhere no session should start, is
refused with a reason instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from board.model import Board, Issue, ParentNode, TicketGroup


@dataclass(frozen=True)
class Refused:
    reason: str


class Place(Enum):
    MAP = auto()
    MAP_CHILD = auto()
    SPEC = auto()
    SPEC_CHILD = auto()
    BACKLOG = auto()
    ORPHAN_WAYFINDER = auto()


# The one table. `{n}` is the ticket, `{map}` the map it sits under.
STARTS: dict[Place, str | Refused] = {
    Place.MAP: "/mattpocock-skills:wayfinder {map}",
    Place.MAP_CHILD: "/mattpocock-skills:wayfinder {map} {n}",
    Place.SPEC_CHILD: "/mattpocock-skills:implement {n}",
    Place.BACKLOG: "/mattpocock-skills:implement {n}",
    Place.SPEC: Refused("#{n} is a spec: work its tickets instead."),
    Place.ORPHAN_WAYFINDER: Refused(
        "#{n} is a wayfinder ticket with no map: there's no map to work it through."
    ),
}


def _members(group: TicketGroup) -> list[Issue]:
    return [*group.takeable, *group.claimed, *group.blocked]


Placed = tuple[Place, Issue, int | None]


def _placed(board: Board) -> Iterator[Placed]:
    """Every ticket on the board: where it sits, the ticket, and its map if any."""
    for m in board.maps:
        yield Place.MAP, m.issue, m.issue.number
        for t in _members(m.group):
            yield Place.MAP_CHILD, t, m.issue.number
    for s in board.specs:
        yield Place.SPEC, s.issue, None
        for t in _members(s.group):
            yield Place.SPEC_CHILD, t, None
    b = board.backlog
    for t in b.orphan_wayfinder:
        yield Place.ORPHAN_WAYFINDER, t, None
    for t in [*b.p1, *b.p2_debt, *b.ready, *b.other]:
        yield Place.BACKLOG, t, None


def _locate(board: Board, number: int) -> Placed | None:
    """Where `number` sits, the ticket itself, and the map it sits under."""
    return next((p for p in _placed(board) if p[1].number == number), None)


def starting_command(board: Board, number: int) -> str | Refused:
    """The command a session on `number` starts with, or why it can't start."""
    found = _locate(board, number)
    if found is None:
        return Refused(f"#{number} is not an open ticket on {board.slug}.")
    place, ticket, map_number = found
    if ticket.assignee:
        return Refused(f"#{number} is claimed by @{ticket.assignee}.")
    if blockers := board.open_blockers.get(number):
        by = ", ".join(f"#{b}" for b in blockers)
        return Refused(f"#{number} is blocked by {by}.")
    start = STARTS[place]
    if isinstance(start, Refused):
        return Refused(start.reason.format(n=number))
    return start.format(n=number, map=map_number)


def map_of(board: Board, number: int) -> ParentNode | None:
    """The map `number` is or sits under, or None if it's neither."""
    found = _locate(board, number)
    if found is None or found[2] is None:
        return None
    return next(m for m in board.maps if m.issue.number == found[2])


def map_children(node: ParentNode) -> list[Issue]:
    """Every open child ticket under the map."""
    return _members(node.group)


def ticket_numbers(board: Board) -> set[int]:
    """The number of every ticket on the board, wherever it sits."""
    return {ticket.number for _, ticket, _ in _placed(board)}
