"""Geometry helpers for the ΔΓΜ: exact point identity, rings from shapely results, T-junctions.

The Cadastre's checks catch mm-level slivers ([S5] ΣΤ.10–11), so vertices shared by two
polygons must be **bit-identical**. Polygon overlay is done with shapely (GEOS); every output
coordinate is then passed through :class:`PointRegistry`, which maps it to the exact
coordinates of an existing point (input vertex, or an intersection computed once) when it lies
within ``tol`` of one. Input coordinates are never recomputed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polylabel

from ..parcels import signed_area
from ..parcels_models import ParcelVertex

Pt = tuple[float, float]

#: Two coordinates closer than this are the same point (m)
SAME_POINT = 1e-6


@dataclass(frozen=True)
class NamedPt:
    name: str
    x: float
    y: float
    new: bool = False

    @property
    def xy(self) -> Pt:
        return (self.x, self.y)


class PointRegistry:
    """Point identity by coordinates (grid hash, cell = ``tol``) with unique names."""

    def __init__(self, new_prefix: str = "Ν", tol: float = SAME_POINT) -> None:
        self.tol = tol
        self.prefix = new_prefix
        self.points: list[NamedPt] = []
        self._grid: dict[tuple[int, int], list[int]] = {}
        self._names: set[str] = set()
        self._counter = 0
        self.renamed: list[tuple[str, str]] = []

    def find(self, x: float, y: float, tol: float | None = None) -> NamedPt | None:
        t = self.tol if tol is None else tol
        reach = max(1, math.ceil(t / self.tol))
        cx, cy = math.floor(x / self.tol), math.floor(y / self.tol)
        best: tuple[float, NamedPt] | None = None
        if reach > 3:  # large search radius: linear scan is cheaper than many cells
            cands: Iterable[NamedPt] = self.points
        else:
            cands = (
                self.points[k]
                for gx in range(cx - reach, cx + reach + 1)
                for gy in range(cy - reach, cy + reach + 1)
                for k in self._grid.get((gx, gy), [])
            )
        for p in cands:
            d = math.hypot(p.x - x, p.y - y)
            if d <= t and (best is None or d < best[0]):
                best = (d, p)
        return best[1] if best else None

    def _next_name(self) -> str:
        while True:
            self._counter += 1
            name = f"{self.prefix}{self._counter}"
            if name not in self._names:
                return name

    def add(
        self, x: float, y: float, name: str | None = None, *, snap: float | None = None
    ) -> NamedPt:
        """Return the existing point within ``snap`` (default ``tol``) or register a new one.
        A given ``name`` already used elsewhere is replaced by a generated one."""
        hit = self.find(x, y, snap)
        if hit is not None:
            return hit
        new = name is None
        if name is None or name in self._names or not name.strip():
            fresh = self._next_name()
            if name and name.strip():
                self.renamed.append((name, fresh))
            name = fresh
        p = NamedPt(name, x, y, new)
        self.points.append(p)
        self._names.add(name)
        self._grid.setdefault((math.floor(x / self.tol), math.floor(y / self.tol)), []).append(
            len(self.points) - 1
        )
        return p

    def index(self, p: NamedPt) -> int:
        return self.points.index(p)


def ring_coords(vertices: Sequence[ParcelVertex]) -> list[Pt]:
    return [(v.x, v.y) for v in vertices]


def polygon(ring: Sequence[Pt]) -> Polygon:
    return Polygon(list(ring))


def polygon_rings(geom: BaseGeometry) -> list[list[Pt]]:
    """Exterior rings (open, no repeated end) of every polygon in ``geom``; holes are
    returned as separate rings of the same polygon only through ``polygon_holes``."""
    out: list[list[Pt]] = []
    for g in shapely.get_parts(geom):
        if isinstance(g, Polygon) and not g.is_empty:
            out.append([(float(x), float(y)) for x, y in g.exterior.coords[:-1]])
        elif hasattr(g, "geoms"):
            out.extend(polygon_rings(g))
    return out


def polygons_of(geom: BaseGeometry) -> list[Polygon]:
    out: list[Polygon] = []
    for g in shapely.get_parts(geom):
        if isinstance(g, Polygon) and not g.is_empty:
            out.append(g)
        elif hasattr(g, "geoms"):
            out.extend(polygons_of(g))
    return out


def lines_of(geom: BaseGeometry) -> list[list[Pt]]:
    out: list[list[Pt]] = []
    for g in shapely.get_parts(geom):
        if isinstance(g, LineString) and not g.is_empty:
            out.append([(float(x), float(y)) for x, y in g.coords])
        elif isinstance(g, MultiLineString) or hasattr(g, "geoms"):
            out.extend(lines_of(g))
    return out


def snap_ring(ring: Sequence[Pt], reg: PointRegistry) -> list[NamedPt]:
    """Map every coordinate to a registry point and drop consecutive repeats."""
    out: list[NamedPt] = []
    for x, y in ring:
        p = reg.add(x, y)
        if not out or out[-1] is not p:
            out.append(p)
    while len(out) > 1 and out[0] is out[-1]:
        out.pop()
    return out


def drop_collinear_spikes(ring: list[NamedPt]) -> list[NamedPt]:
    """Remove zero-width spikes (a, b, a) left by overlay."""
    changed = True
    while changed and len(ring) >= 3:
        changed = False
        n = len(ring)
        for i in range(n):
            if ring[(i - 1) % n] is ring[(i + 1) % n]:
                ring = [ring[k] for k in range(n) if k not in (i, (i + 1) % n)]
                changed = True
                break
    return ring


def area_of(ring: Sequence[NamedPt]) -> float:
    return abs(signed_area([p.xy for p in ring]))


def perimeter_of(ring: Sequence[NamedPt]) -> float:
    n = len(ring)
    return math.fsum(
        math.hypot(ring[(i + 1) % n].x - ring[i].x, ring[(i + 1) % n].y - ring[i].y)
        for i in range(n)
    )


def oriented(ring: list[NamedPt], reg: PointRegistry, clockwise: bool = True) -> list[NamedPt]:
    """Clockwise (Greek practice) ring starting at its earliest-registered point."""
    if not ring:
        return ring
    sa = signed_area([p.xy for p in ring])
    if (sa > 0) == clockwise:
        ring = ring[::-1]
    order = {id(p): k for k, p in enumerate(reg.points)}
    k0 = min(range(len(ring)), key=lambda k: order.get(id(ring[k]), 1 << 30))
    return ring[k0:] + ring[:k0]


def seg_dist(p: Pt, a: Pt, b: Pt) -> tuple[float, float]:
    """Distance from p to segment ab and the parameter t ∈ [0, 1] of the foot point."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy), t


def insert_on_sides(
    ring: list[NamedPt], others: Iterable[NamedPt], tol: float = SAME_POINT
) -> tuple[list[NamedPt], list[NamedPt]]:
    """Insert every point of ``others`` that lies on a side of ``ring`` (within ``tol``, not
    at its ends) into that side: heals T-junctions, the Cadastre's most common failure
    ("a shared vertex missing in one of two adjacent polygons", [S5] ΣΤ.10)."""
    members = {id(p) for p in ring}
    cands = [p for p in others if id(p) not in members]
    if not cands:
        return ring, []
    xs = [p.x for p in ring]
    ys = [p.y for p in ring]
    box = (min(xs) - tol, min(ys) - tol, max(xs) + tol, max(ys) + tol)
    cands = [p for p in cands if box[0] <= p.x <= box[2] and box[1] <= p.y <= box[3]]
    inserted: list[NamedPt] = []
    out: list[NamedPt] = []
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        out.append(a)
        on: list[tuple[float, NamedPt]] = []
        for p in cands:
            d, t = seg_dist(p.xy, a.xy, b.xy)
            if d <= tol and 0.0 < t < 1.0 and p is not a and p is not b:
                on.append((t, p))
        for _, p in sorted(on, key=lambda tp: tp[0]):
            out.append(p)
            inserted.append(p)
    return out, inserted


def to_vertices(ring: Sequence[NamedPt]) -> list[ParcelVertex]:
    return [ParcelVertex(name=p.name, x=p.x, y=p.y) for p in ring]


def label_point(poly: Polygon) -> Pt:
    """A point well inside the polygon (pole of inaccessibility, Mapbox polylabel)."""
    span = max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
    p = polylabel(poly, tolerance=max(span / 200.0, 1e-3))
    if not poly.contains(p):  # pragma: no cover - polylabel stays inside valid polygons
        p = poly.representative_point()
    return (float(p.x), float(p.y))


def location(geom: BaseGeometry) -> Pt:
    """A representative coordinate pair for reporting a problem."""
    if geom.is_empty:
        return (math.nan, math.nan)
    p = geom.representative_point() if not isinstance(geom, Point) else geom
    return (float(p.x), float(p.y))
