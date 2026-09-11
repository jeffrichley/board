from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

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

    @classmethod
    def from_raw(cls, raw: dict) -> Issue:
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
    other: list[Issue] = field(default_factory=list)


@dataclass
class Board:
    slug: str
    open_count: int
    maps: list[ParentNode]
    builds: list[ParentNode]
    backlog: Backlog


def labels_of(raw: dict) -> list[str]:
    return [lb["name"] for lb in raw.get("labels", [])]


def parse_part_of(body: str | None) -> int | None:
    """First `Part of #N` in the body, if any (map/spec parent convention)."""
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
    build_nums: set[int],
    by_num: dict[int, Issue],
    issues: list[dict],
) -> str | None:
    """Status under a map with no open decision tickets left."""
    if not _group_empty(group):
        return None
    related: list[Issue] = []
    seen: set[int] = set()
    for n in children_of.get(map_num, []):
        if n in build_nums and n not in seen:
            related.append(by_num[n])
            seen.add(n)
    for raw in issues:
        n = raw["number"]
        if n not in build_nums or n in seen:
            continue
        if parse_part_of(raw.get("body")) == map_num:
            related.append(by_num[n])
            seen.add(n)
    if related:
        bits = ", ".join(f"#{b.number} {short(b.title, 40)}" for b in related)
        return f"ready to close — open build: {bits}"
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
            if t.assignee:
                claimed.append(t)
            else:
                takeable.append(t)
        elif t.assignee:
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
        if "P1" in labs:
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
    issues: list[dict],
    children_of: dict[int, list[int]],
    blockers_of: dict[int, list[int]],
) -> Board:
    by_num = {i["number"]: Issue.from_raw(i) for i in issues}
    open_nums = set(by_num)

    maps_raw = [i for i in issues if MAP_LABEL in labels_of(i)]
    map_nums = {i["number"] for i in maps_raw}

    # Anyone listed as an open child of a non-map parent cannot be a BUILD root
    # (nested under a spec). Children of maps may still be BUILD roots (spec handoff).
    is_child_of_non_map: set[int] = set()
    for parent, kids in children_of.items():
        if parent in map_nums:
            continue
        is_child_of_non_map.update(n for n in kids if n in open_nums)

    # Candidate build parents: open, have open children, not maps, not nested under a build
    build_nums: set[int] = set()
    for num, kids in children_of.items():
        if num not in open_nums or num in map_nums or num in is_child_of_non_map:
            continue
        if any(k in open_nums for k in kids):
            build_nums.add(num)

    placed: set[int] = set(map_nums) | set(build_nums)

    def make_parent(num: int, note: str | None = None) -> ParentNode:
        child_nums = [k for k in children_of.get(num, []) if k in open_nums and k not in placed]
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
        adjusted = []
        for t in tickets:
            open_b = edges.get(t.number, [])
            adjusted.append(
                Issue(
                    number=t.number,
                    title=t.title,
                    labels=t.labels,
                    assignee=t.assignee,
                    kids_completed=t.kids_completed,
                    kids_total=t.kids_total,
                    blocked_by_count=len(open_b),
                )
            )
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
            build_nums=build_nums,
            by_num=by_num,
            issues=issues,
        )
        if note:
            node.note = note
        maps.append(node)
    builds = [make_parent(n) for n in sorted(build_nums)]

    leftover = [by_num[n] for n in sorted(open_nums - placed)]
    return Board(
        slug=slug,
        open_count=len(issues),
        maps=maps,
        builds=builds,
        backlog=_backlog_for(leftover),
    )
