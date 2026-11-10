"""Graph helpers for the levelling network: connected parts, spanning trees and a short
independent loop basis (private to ``levelnet``).

Loop basis. Every line outside a spanning forest closes one *fundamental* loop; together with
one benchmark-to-benchmark connection per extra fixed benchmark they form an independent basis
of exactly f = n − u conditions. Fundamental loops of a BFS tree can be long, while surveyors
check the elementary loops (meshes). So shorter candidates are tried first: for each line, the
shortest path (by length or setups) between its ends without the line; for each benchmark pair,
the shortest path between them. Candidates are taken in order of length while they are
independent over GF(2) (edge-incidence bit vectors; connections also carry one virtual edge per
benchmark), and the fundamental set completes the basis — the greedy algorithm for a matroid
(Horton 1987, "A polynomial-time algorithm to find the shortest cycle basis of a graph").
"""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

#: Above this many candidate paths the fundamental basis is used as is (bounded CPU time).
MAX_SHORT_CANDIDATES = 200


@dataclass(frozen=True)
class Edge:
    id: int  # line index in the request
    a: str
    b: str
    dh: float


@dataclass
class Graph:
    adj: dict[str, list[Edge]] = field(default_factory=dict)

    def add(self, e: Edge) -> None:
        self.adj.setdefault(e.a, []).append(e)
        self.adj.setdefault(e.b, []).append(e)


def components(nodes: list[str], edges: list[Edge]) -> list[list[str]]:
    parent = {n: n for n in nodes}

    def find(n: str) -> str:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for e in edges:
        ra, rb = find(e.a), find(e.b)
        if ra != rb:
            parent[rb] = ra
    groups: dict[str, list[str]] = {}
    for n in nodes:
        groups.setdefault(find(n), []).append(n)
    return list(groups.values())


Tree = dict[str, tuple[str, Edge] | None]
Step = tuple[Edge, int, str]  # (line, +1 if run a→b else −1, node reached)


def spanning_forest(g: Graph, roots: list[str]) -> tuple[Tree, set[int]]:
    """BFS spanning forest (one tree per root): parent link per node and the tree line ids."""
    parent: Tree = {}
    tree: set[int] = set()
    for root in roots:
        if root in parent:
            continue
        parent[root] = None
        queue = deque([root])
        while queue:
            n = queue.popleft()
            for e in g.adj.get(n, []):
                other = e.b if e.a == n else e.a
                if other not in parent:
                    parent[other] = (n, e)
                    tree.add(e.id)
                    queue.append(other)
    return parent, tree


def path_up(parent: Tree, n: str) -> list[str]:
    out = [n]
    while (link := parent[n]) is not None:
        n = link[0]
        out.append(n)
    return out


def _link(parent: Tree, n: str) -> tuple[str, Edge]:
    link = parent[n]
    if link is None:
        raise AssertionError("the tree root has no parent")
    return link


def tree_path(parent: Tree, a: str, b: str) -> list[Step]:
    """Steps along the tree from a to b (up to their lowest common ancestor, then down)."""
    up_a = path_up(parent, a)
    up_b = path_up(parent, b)
    on_b = set(up_b)
    lca = next(n for n in up_a if n in on_b)
    steps: list[Step] = []
    for n in up_a[: up_a.index(lca)]:  # child → parent
        p, te = _link(parent, n)
        steps.append((te, 1 if te.a == n else -1, p))
    for n in up_b[: up_b.index(lca)][::-1]:  # parent → child
        p, te = _link(parent, n)
        steps.append((te, 1 if te.a == p else -1, n))
    return steps


def shortest_path(
    g: Graph, a: str, b: str, weight: Callable[[Edge], float], skip: int | None = None
) -> list[Step] | None:
    """Dijkstra from a to b, optionally without line ``skip``; None if b is unreachable."""
    dist = {a: 0.0}
    prev: dict[str, tuple[str, Edge]] = {}
    heap: list[tuple[float, int, str]] = [(0.0, 0, a)]
    tie = 0
    while heap:
        d, _, n = heapq.heappop(heap)
        if n == b:
            break
        if d > dist.get(n, float("inf")):
            continue
        for e in g.adj.get(n, []):
            if e.id == skip:
                continue
            other = e.b if e.a == n else e.a
            nd = d + weight(e)
            if nd < dist.get(other, float("inf")):
                dist[other] = nd
                prev[other] = (n, e)
                tie += 1
                heapq.heappush(heap, (nd, tie, other))
    if b not in dist:
        return None
    steps: list[Step] = []
    n = b
    while n != a:
        p, e = prev[n]
        steps.append((e, 1 if e.a == p else -1, n))
        n = p
    return steps[::-1]


@dataclass(frozen=True)
class Closure:
    kind: Literal["loop", "connection"]
    start: str
    steps: list[Step]


def _bits(c: Closure, bench_bit: dict[str, int]) -> int:
    v = 0
    for e, _, _ in c.steps:
        v ^= 1 << e.id
    if c.kind == "connection":
        v ^= (1 << bench_bit[c.start]) ^ (1 << bench_bit[c.steps[-1][2]])
    return v


def loop_basis(
    g: Graph,
    edges: list[Edge],
    benchmarks: list[str],
    weight: Callable[[Edge], float],
    n_lines: int,
) -> list[Closure]:
    """Independent loops (and benchmark connections when ``benchmarks`` are fixed)."""
    roots = benchmarks or ([edges[0].a] if edges else [])
    parent, tree = spanning_forest(g, roots)
    fundamental = [
        Closure("loop", e.a, [(e, 1, e.b), *tree_path(parent, e.b, e.a)])
        for e in edges
        if e.id not in tree
    ]
    for n in benchmarks:
        if parent.get(n) is not None:
            root = path_up(parent, n)[-1]
            fundamental.append(Closure("connection", root, tree_path(parent, root, n)))
    rank = len(fundamental)

    candidates: list[Closure] = []
    pairs = [
        (x, y)
        for i, x in enumerate(benchmarks)
        for y in benchmarks[i + 1 :]
        if path_up(parent, x)[-1] == path_up(parent, y)[-1]
    ]
    non_tree = [e for e in edges if e.id not in tree]
    if len(non_tree) + len(pairs) <= MAX_SHORT_CANDIDATES:
        for e in non_tree:
            back = shortest_path(g, e.b, e.a, weight, skip=e.id)
            if back is not None:
                candidates.append(Closure("loop", e.a, [(e, 1, e.b), *back]))
        for x, y in pairs:
            path = shortest_path(g, x, y, weight)
            if path:
                candidates.append(Closure("connection", x, path))

    def size(c: Closure) -> float:
        return sum(weight(e) for e, _, _ in c.steps)

    bench_bit = {b: n_lines + i for i, b in enumerate(benchmarks)}
    ordered = sorted(candidates, key=size) + fundamental
    basis: dict[int, int] = {}  # pivot bit → reduced vector
    chosen: list[Closure] = []
    for c in ordered:
        if len(chosen) == rank:
            break
        v = _bits(c, bench_bit)
        while v:
            pivot = v.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = v
                chosen.append(c)
                break
            v ^= basis[pivot]
    return sorted(chosen, key=lambda c: (c.kind == "connection", size(c)))
