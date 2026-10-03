from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

MAP_LABEL = "wayfinder:map"
PART_OF_RE = re.compile(r"(?i)\bPart of #(\d+)\b")


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    labels: tuple[str, ...]
    assignee: str | None
    kids_completed: int
    kids_total: int
    blocked_by_count: int
    has_worktree: bool = False

    @property
    def taken(self) -> bool:
        """Claimed, or with a worktree: either way, not takeable."""
        return self.assignee is not None or self.has_worktree

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Issue:
        labels = tuple(lb["name"] for lb in raw.get("labels", []))
        assignee = (raw.get("assignee") or {}).get("login")
        kids = raw.get("sub_issues_summary") or {}
        deps = raw.get("issue_dependencies_summary") or {}
        return cls(
            number=raw["number"],
            title=raw["title"],
            labels=labels,
            assignee=assignee,
            kids_completed=int(kids.get("completed", 0)),
            kids_total=int(kids.get("total", 0)),
            blocked_by_count=int(deps.get("blocked_by", 0)),
        )


@dataclass
class TicketGroup:
    takeable: list[Issue] = field(default_factory=list)
    claimed: list[Issue] = field(default_factory=list)
    blocked: list[Issue] = field(default_factory=list)

    def count(self) -> int:
        return len(self.takeable) + len(self.claimed) + len(self.blocked)


@dataclass
class ParentNode:
    issue: Issue
    group: TicketGroup
    edges: dict[int, list[int]]  # child -> open blockers
    blocks: dict[int, list[int]]  # blocker -> children it blocks
    note: str | None = None


@dataclass
class Backlog:
    p1: list[Issue] = field(default_factory=list)
    p2_debt: list[Issue] = field(default_factory=list)
    ready: list[Issue] = field(default_factory=list)
    orphan_wayfinder: list[Issue] = field(default_factory=list)
    other: list[Issue] = field(default_factory=list)

    def count(self) -> int:
        groups = (self.p1, self.p2_debt, self.ready, self.orphan_wayfinder, self.other)
        return sum(len(g) for g in groups)


class Lane(StrEnum):
    """The board's three lanes, in the order it shows them."""

    WAYFINDING = "wayfinding"
    SPECS = "specs"
    BACKLOG = "backlog"


@dataclass
class Board:
    slug: str
    open_count: int
    maps: list[ParentNode]
    specs: list[ParentNode]
    backlog: Backlog
    open_blockers: dict[int, list[int]] = field(default_factory=dict)
    # What the board has been narrowed by, in words for its header. Empty: not at all.
    filters: tuple[str, ...] = ()

    def ticket_count(self) -> int:
        """How many tickets the board holds, each map and spec among them."""
        parents = self.maps + self.specs
        return sum(1 + p.group.count() for p in parents) + self.backlog.count()

    def only(self, lanes: Collection[Lane]) -> Board:
        """This board holding only `lanes`. Every lane leaves it as it is."""
        if set(lanes) >= set(Lane):
            return self
        return replace(
            self,
            maps=self.maps if Lane.WAYFINDING in lanes else [],
            specs=self.specs if Lane.SPECS in lanes else [],
            backlog=self.backlog if Lane.BACKLOG in lanes else Backlog(),
            filters=self.filters + tuple(lane for lane in Lane if lane in lanes),
        )

    def takeable(self) -> Board:
        """This board holding only what `board work` would start a session on.

        A map or spec stays as the heading over its takeable tickets, and goes,
        note and all, when it has none. A wayfinder ticket with no map is
        refused by `board work`, so its backlog group goes too.
        """

        def frontiers(parents: list[ParentNode]) -> list[ParentNode]:
            return [
                replace(p, group=TicketGroup(takeable=p.group.takeable))
                for p in parents
                if p.group.takeable
            ]

        def takeable_in(issues: list[Issue]) -> list[Issue]:
            return [
                i
                for i in issues
                if not i.taken and not self.open_blockers.get(i.number)
            ]

        b = self.backlog
        return replace(
            self,
            maps=frontiers(self.maps),
            specs=frontiers(self.specs),
            backlog=Backlog(
                p1=takeable_in(b.p1),
                p2_debt=takeable_in(b.p2_debt),
                ready=takeable_in(b.ready),
                other=takeable_in(b.other),
            ),
            filters=(*self.filters, "takeable"),
        )


def labels_of(raw: dict[str, Any]) -> list[str]:
    return [lb["name"] for lb in raw.get("labels", [])]


def parse_part_of(body: str | None) -> int | None:
    """First `Part of #N` in the body, if any (map/spec convention)."""
    if not body:
        return None
    m = PART_OF_RE.search(body)
    return int(m.group(1)) if m else None


def _group_empty(group: TicketGroup) -> bool:
    return not (group.takeable or group.claimed or group.blocked)


def _map_note(
    map_num: int,
    group: TicketGroup,
    *,
    children_of: dict[int, list[int]],
    spec_nums: set[int],
    by_num: dict[int, Issue],
    issues: list[dict[str, Any]],
) -> str | None:
    """Status under a map with no open decision tickets left."""
    if not _group_empty(group):
        return None
    related: list[Issue] = []
    seen: set[int] = set()
    for n in children_of.get(map_num, []):
        if n in spec_nums and n not in seen:
            related.append(by_num[n])
            seen.add(n)
    for raw in issues:
        n = raw["number"]
        if n not in spec_nums or n in seen:
            continue
        if parse_part_of(raw.get("body")) == map_num:
            related.append(by_num[n])
            seen.add(n)
    if related:
        bits = ", ".join(f"#{b.number} {short(b.title, 40)}" for b in related)
        return f"ready to close — open spec: {bits}"
    return "frontier clear — ready for /to-spec"


def short(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def unblock_count(num: int, blocks: dict[int, list[int]]) -> int:
    seen: set[int] = set()
    stack = list(blocks.get(num, []))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(blocks.get(n, []))
    return len(seen)


def direct_blockers(num: int, edges: dict[int, list[int]]) -> list[int]:
    """Open issues that directly block `num` (no transitive chain)."""
    return list(edges.get(num, []))


def blocker_status(num: int, parent: ParentNode) -> str:
    """How a direct blocker should read: takeable | claimed | blocked."""
    if parent.edges.get(num):
        return "blocked"
    if any(t.number == num for t in parent.group.claimed):
        return "claimed"
    if any(t.number == num for t in parent.group.takeable):
        return "takeable"
    if any(t.number == num for t in parent.group.blocked):
        return "blocked"
    # Outside this parent's groups but no open edge recorded → treat as live
    return "takeable"


def _group_tickets(
    tickets: list[Issue],
    edges: dict[int, list[int]],
    blocks: dict[int, list[int]],
) -> TicketGroup:
    takeable, claimed, blocked = [], [], []
    for t in tickets:
        if t.blocked_by_count > 0 and edges.get(t.number):
            blocked.append(t)
        elif t.blocked_by_count > 0 and not edges.get(t.number):
            # summary says blocked but no open blockers left — treat as unblocked
            if t.taken:
                claimed.append(t)
            else:
                takeable.append(t)
        elif t.taken:
            claimed.append(t)
        else:
            takeable.append(t)
    takeable.sort(key=lambda t: (-unblock_count(t.number, blocks), t.number))
    claimed.sort(key=lambda t: t.number)
    blocked.sort(key=lambda t: t.number)
    return TicketGroup(takeable=takeable, claimed=claimed, blocked=blocked)


def _backlog_for(issues: list[Issue]) -> Backlog:
    b = Backlog()
    for i in sorted(issues, key=lambda x: x.number):
        labs = set(i.labels)
        if any(lb.startswith("wayfinder:") for lb in i.labels):
            b.orphan_wayfinder.append(i)
        elif "P1" in labs:
            b.p1.append(i)
        elif "P2" in labs or "debt" in labs:
            b.p2_debt.append(i)
        elif "ready-for-agent" in labs:
            b.ready.append(i)
        else:
            b.other.append(i)
    return b


def build_board(
    slug: str,
    issues: list[dict[str, Any]],
    children_of: dict[int, list[int]],
    blockers_of: dict[int, list[int]],
    worktrees: Collection[int] = (),
) -> Board:
    by_num = {
        i["number"]: replace(Issue.from_raw(i), has_worktree=i["number"] in worktrees)
        for i in issues
    }
    open_nums = set(by_num)

    maps_raw = [i for i in issues if MAP_LABEL in labels_of(i)]
    map_nums = {i["number"] for i in maps_raw}

    # Anyone listed as an open child of a non-map parent cannot be a SPECS root
    # (nested under a spec). Children of maps may still be SPECS roots (spec handoff).
    is_child_of_non_map: set[int] = set()
    for parent, kids in children_of.items():
        if parent in map_nums:
            continue
        is_child_of_non_map.update(n for n in kids if n in open_nums)

    # Candidate specs: open, have open children, not maps,
    # not nested under a spec
    spec_nums: set[int] = set()
    for num, kids in children_of.items():
        if num not in open_nums or num in map_nums or num in is_child_of_non_map:
            continue
        if any(k in open_nums for k in kids):
            spec_nums.add(num)

    placed: set[int] = set(map_nums) | set(spec_nums)

    def make_parent(num: int, note: str | None = None) -> ParentNode:
        child_nums = [
            k for k in children_of.get(num, []) if k in open_nums and k not in placed
        ]
        placed.update(child_nums)
        tickets = [by_num[k] for k in child_nums]
        edges: dict[int, list[int]] = {}
        for t in tickets:
            raw_blockers = [b for b in blockers_of.get(t.number, []) if b in open_nums]
            if raw_blockers or t.blocked_by_count:
                edges[t.number] = raw_blockers
        blocks: dict[int, list[int]] = defaultdict(list)
        for n, bs in edges.items():
            for b in bs:
                blocks[b].append(n)
        # Refresh blocked_by_count semantics using open edges for grouping
        adjusted = [
            replace(t, blocked_by_count=len(edges.get(t.number, []))) for t in tickets
        ]
        group = _group_tickets(adjusted, edges, dict(blocks))
        return ParentNode(
            issue=by_num[num],
            group=group,
            edges=edges,
            blocks=dict(blocks),
            note=note,
        )

    maps: list[ParentNode] = []
    for i in sorted(maps_raw, key=lambda x: x["number"]):
        node = make_parent(i["number"])
        note = _map_note(
            i["number"],
            node.group,
            children_of=children_of,
            spec_nums=spec_nums,
            by_num=by_num,
            issues=issues,
        )
        if note:
            node.note = note
        maps.append(node)
    specs = [make_parent(n) for n in sorted(spec_nums)]

    leftover = [by_num[n] for n in sorted(open_nums - placed)]
    return Board(
        slug=slug,
        open_count=len(issues),
        maps=maps,
        specs=specs,
        backlog=_backlog_for(leftover),
        open_blockers={
            n: open_b
            for n, bs in blockers_of.items()
            if (open_b := [b for b in bs if b in open_nums])
        },
    )
