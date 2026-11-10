"""Subdivision of a parcel (κατάτμηση) into parts of given areas or ratios.

Three families of cut lines (straight-sided parcels only):

* **parallel** to a side, and **perpendicular** to a side. Both are half-plane cuts
  ``{p : n·p ≤ s}`` with a fixed unit normal n. The cut-off area A(s) is continuous, increasing
  and *piecewise quadratic* in s, with breakpoints at the vertex projections n·vᵢ (between two
  breakpoints every trapezoid/triangle of the slab grows linearly in width). The bracket that
  contains the requested area is found from the exact areas at the breakpoints; inside it the
  quadratic through three exact evaluations is solved in closed form (numerically stable root),
  then polished with Newton steps using dA/ds = cross-section width.
* **pivot**: the cut line passes through a fixed boundary point P. Walking the boundary from P,
  the fan triangle (P, vₖ, X) has an area that is *linear* in the position of X along the side
  vₖvₖ₊₁, so the side that holds X is found by accumulating fan areas and X follows in closed
  form.

Area of P ∩ half-plane: Sutherland–Hodgman clipping by one half-plane followed by the shoelace
formula. For non-convex polygons the clip may contain zero-width bridges along the clip line;
their contributions cancel, so the area stays exact (Sutherland & Hodgman 1974).

A cut is accepted only if the line crosses the boundary exactly twice (pivot: if the segment
P–X stays inside the parcel); otherwise an Issue is reported instead of a broken result.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass

from .geodesy import grid_azimuth
from .issues import IssueSink
from .parcels import analyze_parcel, segments_touch, signed_area
from .parcels_models import (
    CutLine,
    Parcel,
    ParcelGeometry,
    ParcelVertex,
    SubdivideRequest,
    SubdivisionPart,
    SubdivisionResult,
)

#: Vertices this close to a cut line are on it (m, local coordinates)
ON_LINE_TOL = 1e-9
#: Pivot coordinates farther than this from the boundary are rejected (m)
PIVOT_TOL = 0.001
#: Requested areas whose sum differs from the parcel by less than this use the remainder (m²)
SUM_MATCH_TOL = 0.01
#: Accuracy goal of every cut (m²); tests demand ≤ 1e-6
AREA_GOAL = 1e-9
NEWTON_STEPS = 6


@dataclass(frozen=True)
class _V:
    """Vertex in local coordinates; ``name`` is None for a new point not yet named.
    ``src`` keeps an original vertex so its exact input coordinates are written back
    (``(x − x0) + x0`` need not round-trip bit for bit)."""

    x: float
    y: float
    name: str | None
    src: ParcelVertex | None = None


class CutError(Exception):
    def __init__(self, code: str, message: str, **params: object) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class _Cut:
    piece: list[_V]
    rest: list[_V]
    ends: tuple[_V, _V]


# ---------------------------------------------------------------------------- half-plane


def _clip_area(ring: list[_V], nx: float, ny: float, s: float) -> float:
    """Area of ring ∩ {n·p ≤ s} (Sutherland–Hodgman against one half-plane, then shoelace)."""
    out: list[tuple[float, float]] = []
    m = len(ring)
    for i in range(m):
        a, b = ring[i], ring[(i + 1) % m]
        fa, fb = nx * a.x + ny * a.y - s, nx * b.x + ny * b.y - s
        if fa <= 0:
            out.append((a.x, a.y))
        if (fa < 0 < fb) or (fb < 0 < fa):
            t = fa / (fa - fb)
            out.append((a.x + t * (b.x - a.x), a.y + t * (b.y - a.y)))
    return abs(signed_area(out))


def _solve_halfplane(ring: list[_V], nx: float, ny: float, target: float) -> float:
    """Offset s with area(ring ∩ {n·p ≤ s}) = target."""
    events = sorted({nx * v.x + ny * v.y for v in ring})
    areas = [_clip_area(ring, nx, ny, e) for e in events]
    k = next((i for i in range(1, len(events)) if areas[i] >= target), len(events) - 1)
    s0, s1 = events[k - 1], events[k]
    a0, a1 = areas[k - 1], areas[k]
    h = s1 - s0
    am = _clip_area(ring, nx, ny, s0 + h / 2.0)
    gamma = 2.0 * (a1 - 2.0 * am + a0) / (h * h)
    beta = (a1 - a0) / h - gamma * h
    d = _quadratic_root(gamma, beta, a0 - target, h)
    s = s0 + d
    for _ in range(NEWTON_STEPS):
        err = _clip_area(ring, nx, ny, s) - target
        if abs(err) <= AREA_GOAL * max(1.0, target):
            break
        width = beta + 2.0 * gamma * (s - s0)
        if width <= 0:
            break
        s = min(max(s - err / width, s0), s1)
    return s


def _quadratic_root(a: float, b: float, c: float, h: float) -> float:
    """Root of a·d² + b·d + c = 0 in [0, h] (stable form; linear when a ≈ 0)."""
    if abs(a) * h <= 1e-14 * max(abs(b), 1e-300):
        return min(max(-c / b, 0.0), h) if b != 0 else 0.0
    disc = max(b * b - 4.0 * a * c, 0.0)
    q = -0.5 * (b + math.copysign(math.sqrt(disc), b))
    roots = [r for r in ((q / a) if a else None, (c / q) if q else None) if r is not None]
    best = min(roots, key=lambda r: 0.0 if 0.0 <= r <= h else min(abs(r), abs(r - h)))
    return min(max(best, 0.0), h)


def _split(ring: list[_V], nx: float, ny: float, s: float) -> _Cut:
    """Split the ring by the line n·p = s; ``piece`` is the part with n·p ≤ s."""
    aug: list[tuple[_V, int]] = []
    m = len(ring)
    f = [nx * v.x + ny * v.y - s for v in ring]
    sg = [0 if abs(x) <= ON_LINE_TOL else (1 if x > 0 else -1) for x in f]
    for i in range(m):
        j = (i + 1) % m
        aug.append((ring[i], sg[i]))
        if sg[i] * sg[j] < 0:
            t = f[i] / (f[i] - f[j])
            a, b = ring[i], ring[j]
            aug.append((_V(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), None), 0))
    if all(x == 0 for _, x in aug):
        raise CutError("PARCEL_CUT_DEGENERATE", "The cut line runs along the boundary")
    crossings = list(_crossing_runs(aug))
    if len(crossings) > 2:
        raise CutError(
            "PARCEL_CUT_MULTIPLE_CROSSINGS",
            f"The cut line crosses the boundary {len(crossings)} times (non-convex parcel)",
            crossings=len(crossings),
        )
    if len(crossings) < 2 or any(len(run) > 1 for run in crossings):
        raise CutError("PARCEL_CUT_DEGENERATE", "The cut line runs along the boundary")
    a, b = crossings[0][0], crossings[1][0]
    n = len(aug)
    first = [aug[(a + k) % n] for k in range((b - a) % n + 1)]
    second = [aug[(b + k) % n] for k in range((a - b) % n + 1)]
    keep_first = any(x < 0 for _, x in first)
    piece, rest = (first, second) if keep_first else (second, first)
    return _Cut([v for v, _ in piece], [v for v, _ in rest], (aug[a][0], aug[b][0]))


def _crossing_runs(aug: list[tuple[_V, int]]) -> Iterator[list[int]]:
    """Runs of on-line vertices whose neighbours lie on opposite sides."""
    n = len(aug)
    start = next(i for i, (_, x) in enumerate(aug) if x != 0)
    run: list[int] = []
    before = aug[start][1]
    for k in range(1, n + 1):
        idx = (start + k) % n
        x = aug[idx][1]
        if x == 0:
            run.append(idx)
            continue
        if run and x != before:
            yield run
        run = []
        before = x


# ---------------------------------------------------------------------------------- pivot


def _pivot_cut(ring: list[_V], p: int, direction: int, target: float) -> _Cut:
    """Cut off ``target`` m² with a line through ring[p], walking the ring in ``direction``."""
    m = len(ring)
    seq = [ring[(p + direction * k) % m] for k in range(m)]
    sign = 1.0 if signed_area([(v.x, v.y) for v in seq]) > 0 else -1.0
    piv = seq[0]
    cum = 0.0
    for k in range(1, m - 1):
        a, b = seq[k], seq[k + 1]
        tri = sign * ((a.x - piv.x) * (b.y - piv.y) - (a.y - piv.y) * (b.x - piv.x)) / 2.0
        if tri <= 0 or cum + tri < target:
            cum += tri
            continue
        t = (target - cum) / tri
        length = math.hypot(b.x - a.x, b.y - a.y)
        if t * length <= ON_LINE_TOL:
            x, piece, rest = a, seq[: k + 1], seq[k:]
        elif (1.0 - t) * length <= ON_LINE_TOL:
            x, piece, rest = b, seq[: k + 2], seq[k + 1 :]
        else:
            x = _V(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), None)
            piece, rest = [*seq[: k + 1], x], [x, *seq[k + 1 :]]
        rest = [*rest, piv]
        _check_chord(seq, piv, x, k)
        if direction < 0:
            piece, rest = piece[::-1], rest[::-1]
        return _Cut(piece, rest, (piv, x))
    raise CutError("PARCEL_CUT_DEGENERATE", "No cut through the pivot gives this area")


def _check_chord(seq: list[_V], piv: _V, x: _V, k: int) -> None:
    """The segment pivot–X must stay inside the parcel and touch the boundary only at its ends."""
    m = len(seq)
    pts = [(v.x, v.y) for v in seq]
    for i in range(m):
        j = (i + 1) % m
        if i in (0, m - 1) or i == k or seq[i] is x or seq[j] is x:
            continue  # sides at the pivot, the side holding X, sides ending at X
        if segments_touch((piv.x, piv.y), (x.x, x.y), pts[i], pts[j], ON_LINE_TOL):
            raise CutError(
                "PARCEL_CUT_MULTIPLE_CROSSINGS",
                "The cut line through the pivot crosses the boundary again (non-convex parcel)",
                crossings=3,
            )
    mid = ((piv.x + x.x) / 2.0, (piv.y + x.y) / 2.0)
    if not _inside(mid, pts):
        raise CutError(
            "PARCEL_CUT_MULTIPLE_CROSSINGS",
            "The cut line through the pivot runs outside the parcel (non-convex parcel)",
            crossings=3,
        )


def _inside(p: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    inside = False
    m = len(ring)
    for i in range(m):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % m]
        if (y1 > p[1]) != (y2 > p[1]):
            xc = x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1)
            if xc > p[0]:
                inside = not inside
    return inside


# ------------------------------------------------------------------------------- driver


class _Names:
    def __init__(self, prefix: str, start: int, used: set[str]) -> None:
        self.prefix, self.k, self.used = prefix, start, set(used)

    def next(self) -> str:
        while f"{self.prefix}{self.k}" in self.used:
            self.k += 1
        name = f"{self.prefix}{self.k}"
        self.used.add(name)
        return name


def _targets(req: SubdivideRequest, total: float, sink: IssueSink) -> list[float | None] | None:
    """Requested area per part (None = remainder), or None when impossible."""
    if req.mode == "ratios":
        tot_r = math.fsum(req.parts)
        return [total * r / tot_r for r in req.parts]
    requested = math.fsum(req.parts)
    tol = max(SUM_MATCH_TOL, 1e-9 * total)
    if requested > total + tol:
        sink.error(
            "PARCEL_PARTS_EXCEED_AREA",
            f"The requested areas ({requested:.2f} m²) exceed the parcel ({total:.2f} m²)",
            requested=round(requested, 2),
            available=round(total, 2),
        )
        return None
    if requested >= total - tol:
        return list(req.parts)
    return [*req.parts, None]  # the remainder is an extra part


def subdivide(req: SubdivideRequest) -> SubdivisionResult:
    """Cut the parcel into parts (see :class:`SubdivideRequest`)."""
    original = analyze_parcel(req.parcel)
    sink = IssueSink()

    def fail() -> SubdivisionResult:
        return SubdivisionResult(
            original=original, parts=[], cut_lines=[], new_points=[], issues=sink.items
        )

    if not original.valid or original.area is None:
        sink.items.extend(i for i in original.issues if i.severity == "error")
        return fail()
    if original.has_arcs:
        sink.error(
            "PARCEL_ARCS_NOT_SUPPORTED",
            "Subdivision and merge need straight sides; replace the arcs with chords first",
        )
        return fail()
    verts = original.vertices
    ox, oy = verts[0].x, verts[0].y
    ring = [_V(v.x - ox, v.y - oy, v.name, v) for v in verts]
    names = _Names(req.new_point_prefix, req.new_point_start, {v.name for v in verts})
    targets = _targets(req, original.area, sink)
    if targets is None:
        return fail()
    try:
        plan = _plan(req, ring, original, (ox, oy))
        pieces, cuts = _run(plan, ring, targets)
    except CutError as exc:
        sink.error(exc.code, str(exc), **exc.params)
        return fail()
    first = [plan.pivot] if plan.pivot is not None else []
    return _assemble(
        req,
        original,
        pieces,
        [*first, *(v for c in cuts for v in c)],
        cuts,
        targets,
        names,
        (ox, oy),
        sink,
    )


@dataclass
class _Plan:
    kind: str
    nx: float = 0.0
    ny: float = 0.0
    pivot: _V | None = None
    direction: int = 1


def _plan(
    req: SubdivideRequest, ring: list[_V], geo: ParcelGeometry, origin: tuple[float, float]
) -> _Plan:
    """Cut family; may insert a pivot point into ``ring`` (local coordinates)."""
    n = len(ring)
    if req.method == "pivot":
        return _pivot_plan(req, ring, origin)
    if req.side is None:
        raise ValueError("Choose the side the cut lines refer to")
    if req.side >= n:
        raise ValueError(f"Side index {req.side} is out of range (the parcel has {n} sides)")
    a, b = ring[req.side], ring[(req.side + 1) % n]
    length = math.hypot(b.x - a.x, b.y - a.y)
    ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
    if req.method == "perpendicular":
        sgn = 1.0 if req.from_end == "start" else -1.0
        return _Plan("halfplane", sgn * ux, sgn * uy)
    ccw = geo.orientation == "counterclockwise"
    nx, ny = (-uy, ux) if ccw else (uy, -ux)  # inward normal
    return _Plan("halfplane", nx, ny)


def _pivot_plan(req: SubdivideRequest, ring: list[_V], origin: tuple[float, float]) -> _Plan:
    if req.pivot is not None:
        idx = next((i for i, v in enumerate(ring) if v.name == req.pivot), None)
        if idx is None:
            raise CutError(
                "PARCEL_PIVOT_UNKNOWN",
                f"The pivot {req.pivot} is not a vertex",
                point=req.pivot,
            )
    elif req.pivot_point is not None:
        idx = _insert_pivot(req.pivot_point.x - origin[0], req.pivot_point.y - origin[1], ring)
    else:
        raise ValueError("Give the pivot vertex or the pivot coordinates")
    direction = 1
    if req.towards is not None:
        if ring[(idx + 1) % len(ring)].name == req.towards:
            direction = 1
        elif ring[(idx - 1) % len(ring)].name == req.towards:
            direction = -1
        else:
            raise CutError(
                "PARCEL_TOWARDS_NOT_ADJACENT",
                f"{req.towards} is not a neighbour of the pivot",
                point=req.towards,
            )
    return _Plan("pivot", pivot=ring[idx], direction=direction)


def _insert_pivot(px: float, py: float, ring: list[_V]) -> int:
    """Put the pivot (local coordinates) on the boundary; a coinciding vertex is reused,
    otherwise a new, still unnamed, vertex is inserted into ``ring``."""
    n = len(ring)
    best: tuple[float, int, float] | None = None
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b.x - a.x, b.y - a.y
        t = max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / (dx * dx + dy * dy)))
        d = math.hypot(px - a.x - t * dx, py - a.y - t * dy)
        if best is None or d < best[0]:
            best = (d, i, t)
    assert best is not None
    d, i, t = best
    if d > PIVOT_TOL:
        raise CutError(
            "PARCEL_PIVOT_NOT_ON_BOUNDARY",
            f"The pivot is {d:.3f} m away from the boundary",
            distance=round(d, 3),
        )
    a, b = ring[i], ring[(i + 1) % n]
    length = math.hypot(b.x - a.x, b.y - a.y)
    if t * length <= PIVOT_TOL:
        return i
    if (1.0 - t) * length <= PIVOT_TOL:
        return (i + 1) % n
    ring.insert(i + 1, _V(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), None))
    return i + 1


def _run(plan: _Plan, ring: list[_V], targets: list[float | None]) -> tuple[list, list]:
    pieces: list[list[_V]] = []
    cuts: list[tuple[_V, _V]] = []
    rest = ring
    for k, target in enumerate(targets):
        if k == len(targets) - 1:
            pieces.append(rest)
            break
        assert target is not None
        available = abs(signed_area([(v.x, v.y) for v in rest]))
        if target >= available - 1e-9 * max(1.0, available):
            raise CutError(
                "PARCEL_TARGET_TOO_LARGE",
                f"Part {k + 1}: {target:.2f} m² requested, only {available:.2f} m² left",
                part=k + 1,
                requested=round(target, 2),
                available=round(available, 2),
            )
        try:
            cut = _cut_once(plan, rest, target)
        except CutError as exc:
            exc.params.setdefault("part", k + 1)
            raise
        pieces.append(cut.piece)
        cuts.append(cut.ends)
        rest = cut.rest
    return pieces, cuts


def _cut_once(plan: _Plan, ring: list[_V], target: float) -> _Cut:
    if plan.kind == "pivot":
        assert plan.pivot is not None
        idx = next(i for i, v in enumerate(ring) if v is plan.pivot)
        return _pivot_cut(ring, idx, plan.direction, target)
    s = _solve_halfplane(ring, plan.nx, plan.ny, target)
    return _split(ring, plan.nx, plan.ny, s)


def _assemble(
    req: SubdivideRequest,
    original: ParcelGeometry,
    pieces: list[list[_V]],
    new_order: list[_V],
    cuts: list[tuple[_V, _V]],
    targets: list[float | None],
    names: _Names,
    origin: tuple[float, float],
    sink: IssueSink,
) -> SubdivisionResult:
    ox, oy = origin
    assigned: dict[int, str] = {}
    new_points: list[ParcelVertex] = []

    def name_of(v: _V) -> str:
        if v.name is not None:
            return v.name
        key = id(v)
        if key not in assigned:
            assigned[key] = names.next()
            new_points.append(ParcelVertex(name=assigned[key], x=v.x + ox, y=v.y + oy))
        return assigned[key]

    for v in new_order:  # pivot first, then cut ends in cut order (Ν1, Ν2 for cut 1, …)
        name_of(v)

    def to_vertex(v: _V) -> ParcelVertex:
        if v.src is not None:  # original vertex: exact input coordinates
            return ParcelVertex(name=v.src.name, x=v.src.x, y=v.src.y)
        return ParcelVertex(name=name_of(v), x=v.x + ox, y=v.y + oy)

    labels = req.part_labels or []
    parts: list[SubdivisionPart] = []
    front = _frontage_segment(req, original)
    rank = {v.name: i for i, v in enumerate(original.vertices)}
    for k, piece in enumerate(pieces):
        label = labels[k] if k < len(labels) and labels[k] else str(k + 1)
        start = min(range(len(piece)), key=lambda i: rank.get(piece[i].name or "", len(rank)))
        ordered = piece[start:] + piece[:start]  # start at the first original vertex
        geo = analyze_parcel(Parcel(label=label, vertices=[to_vertex(v) for v in ordered]))
        requested = targets[k]
        err = geo.area - requested if geo.area is not None and requested is not None else None
        is_cut = k < len(pieces) - 1  # the last part is the remainder, not a solved cut
        if is_cut and err is not None and abs(err) > _area_limit(geo):
            sink.warning(
                "PARCEL_CUT_NOT_CONVERGED",
                f"Part {k + 1}: area differs from the request by {err:.2e} m²",
                part=k + 1,
                error=f"{err:.2e}",
            )
        frontage = _frontage(geo, front) if front is not None else None
        if frontage is not None and req.min_frontage is not None and frontage < req.min_frontage:
            sink.warning(
                "PARCEL_FRONTAGE_SHORT",
                f"Part {k + 1}: frontage {frontage:.2f} m is below {req.min_frontage:.2f} m",
                part=k + 1,
                frontage=round(frontage, 2),
                minimum=round(req.min_frontage, 2),
            )
        parts.append(
            SubdivisionPart(
                geometry=geo, requested_area=requested, area_error=err, frontage=frontage
            )
        )
    cut_lines = [_cut_line(to_vertex(a), to_vertex(b)) for a, b in cuts]
    return SubdivisionResult(
        original=original,
        parts=parts,
        cut_lines=cut_lines,
        new_points=new_points,
        issues=sink.items,
    )


def _area_limit(geo: ParcelGeometry) -> float:
    """Accuracy a cut can reach once its new points are stored as float64 coordinates:
    1e-6 m², or perimeter × one unit in the last place of the coordinates for large parcels
    (≈ 0.9 nm at ΕΓΣΑ87 northings, so this only matters beyond ≈ 1 km)."""
    big = max((max(abs(v.x), abs(v.y)) for v in geo.vertices), default=0.0)
    return max(1e-6, (geo.perimeter or 0.0) * math.ulp(big))


def _cut_line(a: ParcelVertex, b: ParcelVertex) -> CutLine:
    return CutLine(
        a=a,
        b=b,
        length=math.hypot(b.x - a.x, b.y - a.y),
        azimuth=grid_azimuth(a.x, a.y, b.x, b.y),
    )


def _frontage_segment(
    req: SubdivideRequest, original: ParcelGeometry
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if req.frontage_side is None:
        return None
    vs = original.vertices
    if req.frontage_side >= len(vs):
        raise ValueError(f"Frontage side {req.frontage_side} is out of range")
    a, b = vs[req.frontage_side], vs[(req.frontage_side + 1) % len(vs)]
    return (a.x, a.y), (b.x, b.y)


def _frontage(geo: ParcelGeometry, seg: tuple[tuple[float, float], tuple[float, float]]) -> float:
    """Length of the part's boundary lying on the frontage side."""
    (ax, ay), (bx, by) = seg
    dx, dy = bx - ax, by - ay
    ll = math.hypot(dx, dy)
    vs = geo.vertices

    def on(v: ParcelVertex) -> bool:
        cross = abs((v.x - ax) * dy - (v.y - ay) * dx) / ll
        t = ((v.x - ax) * dx + (v.y - ay) * dy) / (ll * ll)
        return cross < 1e-6 and -1e-9 <= t <= 1 + 1e-9

    total = [
        math.hypot(w.x - v.x, w.y - v.y)
        for v, w in zip(vs, vs[1:] + vs[:1], strict=True)
        if on(v) and on(w)
    ]
    return math.fsum(total)
