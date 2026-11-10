"""Merge (συνένωση) of adjacent parcels into one polygon.

Method (boundary cancellation on a planar subdivision):

1. Vertices of all parcels closer than the snap tolerance become one node (the first occurrence
   keeps its name and coordinates).
2. A node that lies on a side of another parcel (a T-junction, e.g. a neighbour that was already
   subdivided) is inserted into that side.
3. Every ring is oriented counter-clockwise and its sides become directed edges. A side shared by
   two parcels appears once in each direction and cancels; the edges that remain form the
   boundary of the union.
4. The remaining edges are traced into loops: one counter-clockwise loop is the merged parcel,
   clockwise loops are holes, several counter-clockwise loops mean the parcels are not adjacent.
   A node with two outgoing boundary edges means the parcels only touch at a point.

Same-direction duplicate edges, or a merged area smaller than the sum of the (snapped) parts,
mean the parcels overlap.
"""

from __future__ import annotations

import bisect
import math
from collections import Counter
from dataclasses import dataclass

from .issues import IssueSink
from .parcels import analyze_parcel, signed_area
from .parcels_models import MergeRequest, MergeResult, Parcel, ParcelGeometry, ParcelVertex

#: Union area may fall short of the sum of the parts by this much before it counts as overlap (m²)
OVERLAP_TOL = 1e-6


@dataclass(frozen=True)
class _Node:
    name: str
    x: float
    y: float


class _Snapper:
    """Greedy snapping with a grid hash (cell = tolerance)."""

    def __init__(self, tol: float) -> None:
        self.tol = tol
        self.nodes: list[_Node] = []
        self.grid: dict[tuple[int, int], list[int]] = {}
        self.max_snap = 0.0
        self.snapped = 0

    def add(self, v: ParcelVertex) -> int:
        cx, cy = math.floor(v.x / self.tol), math.floor(v.y / self.tol)
        best: tuple[float, int] | None = None
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for k in self.grid.get((gx, gy), []):
                    d = math.hypot(self.nodes[k].x - v.x, self.nodes[k].y - v.y)
                    if d <= self.tol and (best is None or d < best[0]):
                        best = (d, k)
        if best is not None:
            if best[0] > 0:
                self.snapped += 1
                self.max_snap = max(self.max_snap, best[0])
            return best[1]
        self.nodes.append(_Node(v.name, v.x, v.y))
        self.grid.setdefault((cx, cy), []).append(len(self.nodes) - 1)
        return len(self.nodes) - 1


@dataclass(frozen=True)
class Union:
    """Boundary of the union of valid straight-sided parcels (``loop`` is counter-clockwise)."""

    loop: list[tuple[str, float, float]]


def union_boundary(
    geos: list[ParcelGeometry], tol: float, sink: IssueSink
) -> tuple[Union | None, float, list[str]]:
    """Union of the parcels by boundary cancellation. Returns (union or None, max snap,
    inserted T-junction names); problems are added to ``sink``. Coordinates are those of the
    first occurrence of each vertex, never recomputed."""
    for g in geos:
        if not g.valid:
            sink.items.extend(i for i in g.issues if i.severity == "error")
    if any(i.severity == "error" for i in sink.items):
        return None, 0.0, []
    if any(g.has_arcs for g in geos):
        sink.error(
            "PARCEL_ARCS_NOT_SUPPORTED",
            "Subdivision and merge need straight sides; replace the arcs with chords first",
        )
        return None, 0.0, []
    snap = _Snapper(tol)
    rings = [_ring_ids(g, snap) for g in geos]
    rings, inserted = _insert_t_junctions(rings, snap.nodes, tol)
    if snap.snapped:
        sink.info(
            "PARCEL_MERGE_SNAPPED",
            f"{snap.snapped} vertices snapped (up to {snap.max_snap * 1000:.1f} mm)",
            count=snap.snapped,
            max_mm=round(snap.max_snap * 1000, 1),
        )
    loops = _boundary_loops(rings, snap.nodes, sink)
    if loops is None:
        return None, snap.max_snap, inserted
    outer = [lp for lp in loops if _loop_area(lp, snap.nodes) > 0]
    holes = [lp for lp in loops if _loop_area(lp, snap.nodes) < 0]
    if len(outer) != 1:
        sink.error("PARCEL_MERGE_NOT_ADJACENT", "The parcels do not share a common side")
        return None, snap.max_snap, inserted
    if holes:
        sink.error(
            "PARCEL_MERGE_HOLES",
            f"The union has {len(holes)} hole(s) (enclosed area)",
            count=len(holes),
        )
        return None, snap.max_snap, inserted
    parts = math.fsum(abs(_loop_area(r, snap.nodes)) for r in rings)
    union_area = _loop_area(outer[0], snap.nodes)
    if parts - union_area > OVERLAP_TOL * max(1.0, len(rings)):
        sink.error(
            "PARCEL_MERGE_OVERLAP",
            f"The parcels overlap by {parts - union_area:.4f} m²",
            area=round(parts - union_area, 4),
        )
        return None, snap.max_snap, inserted
    loop = [(snap.nodes[k].name, snap.nodes[k].x, snap.nodes[k].y) for k in outer[0]]
    return Union(loop), snap.max_snap, inserted


def merge_parcels(req: MergeRequest) -> MergeResult:
    sink = IssueSink()
    geos = [analyze_parcel(p) for p in req.parcels]
    area_sum = math.fsum(g.area or 0.0 for g in geos)
    union, max_snap, inserted = union_boundary(geos, req.snap_tolerance, sink)
    if union is None:
        return MergeResult(
            merged=None, max_snap=max_snap, inserted=inserted, area_sum=area_sum, issues=sink.items
        )
    merged = _merged_geometry(req, geos, union.loop)
    sink.items.extend(merged.issues)
    return MergeResult(
        merged=merged,
        max_snap=max_snap,
        inserted=inserted,
        area_sum=area_sum,
        issues=sink.items,
    )


def _ring_ids(g: ParcelGeometry, snap: _Snapper) -> list[int]:
    ids = [snap.add(v) for v in g.vertices]
    if g.orientation == "clockwise":
        ids.reverse()
    out: list[int] = []
    for k in ids:
        if not out or out[-1] != k:
            out.append(k)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _insert_t_junctions(
    rings: list[list[int]], nodes: list[_Node], tol: float
) -> tuple[list[list[int]], list[str]]:
    """Insert nodes lying on the interior of a side into that side (sorted along it)."""
    order = sorted(range(len(nodes)), key=lambda k: nodes[k].x)
    xs = [nodes[k].x for k in order]
    inserted: list[str] = []
    out: list[list[int]] = []
    for ring in rings:
        new_ring: list[int] = []
        m = len(ring)
        for i in range(m):
            a, b = nodes[ring[i]], nodes[ring[(i + 1) % m]]
            new_ring.append(ring[i])
            lo = bisect.bisect_left(xs, min(a.x, b.x) - tol)
            hi = bisect.bisect_right(xs, max(a.x, b.x) + tol)
            dx, dy = b.x - a.x, b.y - a.y
            ll = dx * dx + dy * dy
            on: list[tuple[float, int]] = []
            for k in order[lo:hi]:
                if k in (ring[i], ring[(i + 1) % m]):
                    continue
                p = nodes[k]
                t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / ll
                if t <= 0 or t >= 1:
                    continue
                if math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy) <= tol:
                    on.append((t, k))
            for _, k in sorted(on):
                new_ring.append(k)
                inserted.append(nodes[k].name)
        out.append(new_ring)
    return out, inserted


def _boundary_loops(
    rings: list[list[int]], nodes: list[_Node], sink: IssueSink
) -> list[list[int]] | None:
    edges: Counter[tuple[int, int]] = Counter()
    for ring in rings:
        for i in range(len(ring)):
            edges[(ring[i], ring[(i + 1) % len(ring)])] += 1
    if any(c > 1 for c in edges.values()):
        sink.error("PARCEL_MERGE_OVERLAP", "The parcels overlap", area=0.0)
        return None
    boundary = [e for e in edges if (e[1], e[0]) not in edges]
    out: dict[int, list[int]] = {}
    for a, b in boundary:
        out.setdefault(a, []).append(b)
    pinch = next((a for a, bs in out.items() if len(bs) > 1), None)
    if pinch is not None:
        sink.error(
            "PARCEL_MERGE_POINT_CONTACT",
            f"The parcels touch only at vertex {nodes[pinch].name}",
            point=nodes[pinch].name,
        )
        return None
    loops: list[list[int]] = []
    seen: set[int] = set()
    for start in out:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        cur = out[start][0]
        while cur != start:
            if cur in seen or cur not in out:
                sink.error("PARCEL_MERGE_NOT_ADJACENT", "The parcels do not share a common side")
                return None
            loop.append(cur)
            seen.add(cur)
            cur = out[cur][0]
        loops.append(loop)
    return loops


def _loop_area(loop: list[int], nodes: list[_Node]) -> float:
    return signed_area([(nodes[k].x, nodes[k].y) for k in loop])


def _merged_geometry(
    req: MergeRequest, geos: list[ParcelGeometry], loop: list[tuple[str, float, float]]
) -> ParcelGeometry:
    if geos[0].orientation == "clockwise":
        loop = loop[::-1]
    first = next((i for i, n in enumerate(loop) if n[0] == geos[0].vertices[0].name), 0)
    loop = loop[first:] + loop[:first]
    label = req.label or " + ".join(g.label for g in geos if g.label)
    vertices = [ParcelVertex(name=n, x=x, y=y) for n, x, y in loop]
    return analyze_parcel(Parcel(label=label, vertices=vertices))
