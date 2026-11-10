"""Coverage check: do a set of parcels tile an outline exactly?

The Hellenic Cadastre accepts a diagram of geometric changes only if the final parcels cover
the original cadastral outline with no gaps and no overlaps (even mm slivers are rejected).
The check:

1. the parts are united by boundary cancellation (``parcels_merge.union_boundary``): overlaps,
   inner gaps (holes), point contacts and disconnected parts are reported there;
2. every vertex of the union boundary must lie on the outline boundary (nothing outside), and
   every outline vertex on the union boundary (no gap along the outline), within ``tolerance``;
3. |Σ part areas − outline area| ≤ ``area_tolerance`` catches slivers thinner than the vertex
   tolerance.

The default vertex tolerance is 1 µm: parts produced by ``subdivide`` reuse the exact original
coordinates and share every new vertex bit for bit, so they pass with exact matching.
"""

from __future__ import annotations

import math

from .issues import IssueSink
from .parcels import analyze_parcel
from .parcels_merge import union_boundary
from .parcels_models import CoverageRequest, CoverageResult


def _dist_to_ring(px: float, py: float, ring: list[tuple[float, float]]) -> float:
    best = math.inf
    n = len(ring)
    for i in range(n):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        ll = dx * dx + dy * dy
        t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best


def check_coverage(req: CoverageRequest) -> CoverageResult:
    sink = IssueSink()
    outline = analyze_parcel(req.outline)
    geos = [analyze_parcel(p) for p in req.parts]
    parts_area = math.fsum(g.area or 0.0 for g in geos)
    if not outline.valid or outline.area is None:
        sink.items.extend(i for i in outline.issues if i.severity == "error")
        return CoverageResult(
            ok=False, outline_area=None, parts_area=parts_area, difference=None, issues=sink.items
        )
    union, _, _ = union_boundary(geos, req.tolerance, sink)
    difference = parts_area - outline.area
    if union is not None:
        ring = [(v.x, v.y) for v in outline.vertices]
        outside = [n for n, x, y in union.loop if _dist_to_ring(x, y, ring) > req.tolerance]
        if outside:
            sink.error(
                "PARCEL_COVERAGE_OUTSIDE",
                f"Vertices off the outline: {', '.join(outside[:10])}",
                points=outside[:10],
            )
        uring = [(x, y) for _, x, y in union.loop]
        gaps = [v.name for v in outline.vertices if _dist_to_ring(v.x, v.y, uring) > req.tolerance]
        if gaps:
            sink.error(
                "PARCEL_COVERAGE_GAP",
                f"Outline vertices not covered by the parts: {', '.join(gaps[:10])}",
                points=gaps[:10],
            )
    if abs(difference) > req.area_tolerance:
        sink.error(
            "PARCEL_COVERAGE_AREA",
            f"The parts total {parts_area:.4f} m², the outline {outline.area:.4f} m²",
            difference=round(difference, 4),
        )
    ok = not any(i.severity == "error" for i in sink.items)
    return CoverageResult(
        ok=ok,
        outline_area=outline.area,
        parts_area=parts_area,
        difference=difference,
        issues=sink.items,
    )
