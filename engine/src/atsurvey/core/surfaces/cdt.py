"""Constrained Delaunay triangulation by edge flipping (breaklines, boundary polygons).

Method: S. W. Sloan (1993), "A fast algorithm for generating constrained Delaunay
triangulations", Computers & Structures 47(3), 441–450:

1. Start from the (unconstrained) Delaunay triangulation of all vertices.
2. For each constrained segment vi→vj that is not already an edge, collect the edges it
   crosses (walking from vi). Repeatedly take an edge from that list: if its two triangles
   form a strictly convex quadrilateral, swap the diagonal; if the new diagonal still
   crosses vi→vj put it back in the list, otherwise remember it as a new edge. Edges of a
   non-convex quadrilateral go to the end of the list. Sloan proves this terminates.
3. Restore the Delaunay property on the new edges by Lawson swaps (never swapping a
   constrained edge).

A segment that passes exactly through a vertex is split there. A segment that crosses an
already constrained segment is rejected (``CrossingConstraint``), because the crossing
point would need a height from two different breaklines.

Predicates are exact in sign (``geom.orient``/``geom.incircle``).
"""

from __future__ import annotations

import numpy as np

from .geom import F64, I64, incircle, orient


class CrossingConstraint(ValueError):
    pass


class _Tri:
    """Mutable triangulation: triangles as CCW vertex triples + directed-edge map."""

    def __init__(self, xy: F64, tri: I64) -> None:
        self.x = xy[:, 0].tolist()
        self.y = xy[:, 1].tolist()
        self.tris: list[list[int]] = tri.tolist()
        self.edge: dict[tuple[int, int], int] = {}
        self.vt: dict[int, int] = {}
        for t, (a, b, c) in enumerate(self.tris):
            self._register(t, a, b, c)
        self.fixed: set[tuple[int, int]] = set()

    def _register(self, t: int, a: int, b: int, c: int) -> None:
        self.edge[(a, b)] = t
        self.edge[(b, c)] = t
        self.edge[(c, a)] = t
        self.vt[a] = t
        self.vt[b] = t
        self.vt[c] = t

    def o(self, a: int, b: int, c: int) -> int:
        return orient(self.x[a], self.y[a], self.x[b], self.y[b], self.x[c], self.y[c])

    def third(self, t: int, a: int, b: int) -> int:
        for v in self.tris[t]:
            if v != a and v != b:
                return v
        raise AssertionError("degenerate triangle")

    def has_edge(self, a: int, b: int) -> bool:
        return (a, b) in self.edge or (b, a) in self.edge

    def flip(self, a: int, b: int) -> tuple[int, int]:
        """Swap the diagonal a–b of the quadrilateral formed by its two triangles."""
        t1 = self.edge[(a, b)]
        t2 = self.edge[(b, a)]
        c = self.third(t1, a, b)
        d = self.third(t2, a, b)
        for u, v in ((a, b), (b, c), (c, a), (b, a), (a, d), (d, b)):
            self.edge.pop((u, v), None)
        self.tris[t1] = [a, d, c]
        self.tris[t2] = [d, b, c]
        self._register(t1, a, d, c)
        self._register(t2, d, b, c)
        return c, d

    def star(self, v: int) -> list[int]:
        """Triangles incident to v (walking both ways around it)."""
        start = self.vt[v]
        out = [start]
        t = start
        while True:  # counter-clockwise around v
            a, b, c = self.tris[t]
            prev = {a: c, b: a, c: b}[v]  # edge (v, prev) is shared with the next triangle
            nt = self.edge.get((v, prev))
            if nt is None or nt == start:
                break
            out.append(nt)
            t = nt
        if nt is None:  # hull vertex: also walk clockwise
            t = start
            while True:
                a, b, c = self.tris[t]
                nxt = {a: b, b: c, c: a}[v]
                pt = self.edge.get((nxt, v))
                if pt is None:
                    break
                out.append(pt)
                t = pt
        return out

    def crossed_edges(self, vi: int, vj: int) -> tuple[list[tuple[int, int]], int | None]:
        """Edges properly crossed by vi→vj, or (…, k) if the segment hits vertex k first."""
        for t in self.star(vi):
            a, b, c = self.tris[t]
            r, lft = {a: (b, c), b: (c, a), c: (a, b)}[vi]  # CCW triangle (vi, r, lft)
            o_r = self.o(vi, r, vj)
            o_l = self.o(vi, lft, vj)
            if o_r == 0 and _between(self, vi, r, vj):
                return [], r
            if o_l == 0 and _between(self, vi, lft, vj):
                return [], lft
            if o_r > 0 and o_l < 0:
                break
        else:  # pragma: no cover - the triangulation covers the segment's direction
            raise ValueError("Breakline segment leaves the triangulation")
        edges: list[tuple[int, int]] = []
        while True:
            if (r, lft) in self.fixed or (lft, r) in self.fixed:
                raise CrossingConstraint(f"{vi}-{vj}")
            edges.append((r, lft))
            nt = self.edge.get((lft, r))
            if nt is None:  # pragma: no cover - vj is a vertex inside the hull
                raise ValueError("Breakline segment leaves the triangulation")
            c = self.third(nt, r, lft)
            if c == vj:
                return edges, None
            oc = self.o(vi, vj, c)
            if oc == 0:
                return edges, c
            if oc > 0:
                lft = c
            else:
                r = c


def _between(t: _Tri, a: int, m: int, b: int) -> bool:
    """m (collinear with a, b) lies strictly between a and b."""
    dx, dy = t.x[b] - t.x[a], t.y[b] - t.y[a]
    s = (t.x[m] - t.x[a]) * dx + (t.y[m] - t.y[a]) * dy
    return 0 < s < dx * dx + dy * dy


def _crosses(t: _Tri, c: int, d: int, vi: int, vj: int) -> bool:
    if c in (vi, vj) or d in (vi, vj):
        return False
    return t.o(vi, vj, c) * t.o(vi, vj, d) < 0 and t.o(c, d, vi) * t.o(c, d, vj) < 0


def _insert(t: _Tri, vi: int, vj: int) -> None:
    while True:
        if t.has_edge(vi, vj):
            t.fixed.add((vi, vj))
            return
        edges, hit = t.crossed_edges(vi, vj)
        target = vj if hit is None else hit
        if edges:
            _insert_segment_edges(t, vi, target, edges)
        t.fixed.add((vi, target))
        if target == vj:
            return
        vi = target  # the segment passed exactly through a vertex: continue from it


def _insert_segment_edges(t: _Tri, vi: int, vj: int, crossing: list[tuple[int, int]]) -> None:
    queue = list(crossing)
    new: list[tuple[int, int]] = []
    guard = 0
    limit = 50 * (len(queue) + 1) ** 2 + 1000
    while queue:
        guard += 1
        if guard > limit:  # pragma: no cover - defensive, Sloan's loop terminates
            raise ValueError("Breakline insertion did not converge")
        a, b = queue.pop(0)
        t1 = t.edge[(a, b)]
        t2 = t.edge[(b, a)]
        c = t.third(t1, a, b)
        d = t.third(t2, a, b)
        if t.o(c, d, a) * t.o(c, d, b) >= 0:  # not strictly convex
            queue.append((a, b))
            continue
        c, d = t.flip(a, b)
        if _crosses(t, c, d, vi, vj):
            queue.append((c, d))
        else:
            new.append((c, d))
    _restore_delaunay(t, new, vi, vj)


def _restore_delaunay(t: _Tri, new: list[tuple[int, int]], vi: int, vj: int) -> None:
    swapped = True
    rounds = 0
    while swapped and rounds < 1000:
        swapped = False
        rounds += 1
        for i, (a, b) in enumerate(new):
            if {a, b} == {vi, vj} or (a, b) in t.fixed or (b, a) in t.fixed:
                continue
            t1 = t.edge.get((a, b))
            t2 = t.edge.get((b, a))
            if t1 is None or t2 is None:
                continue
            c = t.third(t1, a, b)
            d = t.third(t2, a, b)
            if incircle(t.x[a], t.y[a], t.x[b], t.y[b], t.x[c], t.y[c], t.x[d], t.y[d]) > 0:
                new[i] = t.flip(a, b)
                swapped = True


def constrain(
    xy: F64, tri: I64, segments: list[tuple[int, int]]
) -> tuple[I64, list[tuple[int, int]], list[tuple[int, int]]]:
    """Enforce ``segments`` (vertex index pairs) as edges of a CCW Delaunay triangulation.

    Returns (triangles, enforced segments, rejected segments that cross an earlier one).
    """
    t = _Tri(xy, tri)
    done: list[tuple[int, int]] = []
    rejected: list[tuple[int, int]] = []
    for a, b in segments:
        if a == b:
            continue
        if (a, b) in t.fixed or (b, a) in t.fixed:
            continue
        if t.has_edge(a, b):
            t.fixed.add((a, b))
            done.append((a, b))
            continue
        try:
            _insert(t, a, b)  # a crossing is detected before any edge is swapped
            done.append((a, b))
        except CrossingConstraint:
            rejected.append((a, b))
    return np.asarray(t.tris, dtype=np.int64).reshape(-1, 3), done, rejected
