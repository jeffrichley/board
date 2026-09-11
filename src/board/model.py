from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

MAP_LABEL = "wayfinder:map"


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


def blocker_chain(
    num: int,
    edges: dict[int, list[int]],
    depth: int = 0,
    seen: frozenset[int] = frozenset(),
) -> str:
    direct = [b for b in edges.get(num, []) if b not in seen]
    if not direct or depth >= 4:
        return ""
    here = ", ".join(f"#{b}" for b in direct)
    seen = seen | {num} | set(direct)
    deeper = {b for d in direct for b in edges.get(d, []) if b not in seen}
    tail = ""
    if deeper:
        nxt = sorted(deeper)
        tail = " <- " + ", ".join(f"#{b}" for b in nxt)
        if any(edges.get(b) for b in nxt) and depth + 2 < 4:
            tail += " <- …"
    return f"<- {here}{tail}"


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

    # Anyone listed as an open child of anyone
    is_child: set[int] = set()
    for kids in children_of.values():
        is_child.update(n for n in kids if n in open_nums)

    # Candidate build parents: open, have open children, not maps, not children
    build_nums: set[int] = set()
    for num, kids in children_of.items():
        if num not in open_nums or num in map_nums or num in is_child:
            continue
        if any(k in open_nums for k in kids):
            build_nums.add(num)

    placed: set[int] = set(map_nums) | set(build_nums)

    def make_parent(num: int) -> ParentNode:
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
        return ParentNode(issue=by_num[num], group=group, edges=edges, blocks=dict(blocks))

    maps = [make_parent(i["number"]) for i in sorted(maps_raw, key=lambda x: x["number"])]
    builds = [make_parent(n) for n in sorted(build_nums)]

    leftover = [by_num[n] for n in sorted(open_nums - placed)]
    return Board(
        slug=slug,
        open_count=len(issues),
        maps=maps,
        builds=builds,
        backlog=_backlog_for(leftover),
    )
