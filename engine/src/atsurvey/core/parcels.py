"""Parcel geometry (ιδιοκτησίες / γεωτεμάχια) and area comparison.

Public API (reused by subdivision, merge and the Cadastre diagram of geometric changes):

* ``analyze_parcel(parcel)`` → :class:`ParcelGeometry`: cleaned vertices, side table, area
  (arcs included), perimeter, orientation, centroid and validation issues.
* ``signed_area(points)``: shoelace area of a ring of (x, y), positive counter-clockwise.
* ``area_tolerance(rule, reference)`` and ``compare_areas(request)``.
* ``AREA_TOLERANCE_PRESETS``: Hellenic Cadastre rules (urban / rural U0), see ``cadastre_tolerance``.

Formulas
--------
* Shoelace (Gauss) area on coordinates relative to the first vertex, summed with ``math.fsum``
  (see docs/numerics.md): ``2A = Σ (xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ)``.
* Circular segment between chord c and arc of radius R, central angle θ = 2·asin(c / 2R)
  (or 2π − θ for a major arc): ``S = R²/2 · (θ − sin θ)``, arc length ``R·θ``; its centroid
  lies on the symmetry axis at ``4R·sin³(θ/2) / (3(θ − sin θ))`` from the centre
  (e.g. Bronshtein & Semendyayev, *Handbook of Mathematics*, plane figures).
  The signed area (counter-clockwise positive) gains +S for an arc bulging to the **right** of
  the direction of travel and −S for one bulging to the left, whatever the ring orientation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .geodesy import grid_azimuth
from .issues import IssueSink
from .models import Issue
from .parcels_models import (
    AreaCompareRequest,
    AreaCompareResult,
    AreaCompareRow,
    AreaTolerancePreset,
    AreaToleranceRule,
    Parcel,
    ParcelGeometry,
    ParcelVertex,
    SideRow,
    XYPoint,
)

#: Consecutive vertices closer than this are duplicates (m)
DUPLICATE_TOL = 1e-6
#: Two non-adjacent sides closer than this touch or cross (m)
TOUCH_TOL = 1e-7
#: Polygons with |area| below this are degenerate (m²)
ZERO_AREA_TOL = 1e-6
#: Arcs are densified into this many chords for the self-intersection test only
ARC_TEST_SEGMENTS = 8

_CADASTRE_SOURCE = (
    "ΟΚΧΕ 461/03/21.7.2008 (ΦΕΚ Β΄ 1510/31.7.2008), κεφ. 7 §3.6 της 460/03/12.6.2008 "
    "(ΦΕΚ Β΄ 1156/2008)"
)
_DGM_GUIDE_SOURCE = "Κτηματολόγιο Α.Ε., οδηγός ΔΓΜ (ενδεικτικά, εμπιστοσύνη 99,7 %)"

#: Official area-tolerance rules (Hellenic Cadastre). Mirrored in web/src/lib/parcelsApi.ts.
#: Rural U0 differs between the ΦΕΚ (2.00 m) and the ΔΓΜ guide (2.50 m): both are offered and
#: flagged ``to_be_confirmed`` until the owner confirms which applies.
AREA_TOLERANCE_PRESETS: list[AreaTolerancePreset] = [
    AreaTolerancePreset(
        id="cadastre_urban",
        label="Κτηματολόγιο — αστική (U0 = 0,50 m)",
        rule=AreaToleranceRule(kind="cadastre", u0=0.5, source=_CADASTRE_SOURCE),
    ),
    AreaTolerancePreset(
        id="cadastre_rural",
        label="Κτηματολόγιο — αγροτική (U0 = 2,00 m)",
        rule=AreaToleranceRule(kind="cadastre", u0=2.0, source=_CADASTRE_SOURCE),
        to_be_confirmed=True,
    ),
    AreaTolerancePreset(
        id="cadastre_rural_dgm_guide",
        label="Κτηματολόγιο — αγροτική κατά οδηγό ΔΓΜ (U0 = 2,50 m)",
        rule=AreaToleranceRule(kind="cadastre", u0=2.5, source=_DGM_GUIDE_SOURCE),
        to_be_confirmed=True,
    ),
]
#: Cap of the cadastral tolerance for areas surveyed under the 2007 specifications (% of E)
CADASTRE_CAP_PERCENT = 7.0

Pt = tuple[float, float]


# ----------------------------------------------------------------------------- helpers


def signed_area(points: Sequence[Pt]) -> float:
    """Shoelace area of a closed ring (no repeated closing vertex), counter-clockwise > 0.
    Computed relative to the first vertex with compensated summation."""
    n = len(points)
    if n < 3:
        return 0.0
    ox, oy = points[0]
    xs = [p[0] - ox for p in points]
    ys = [p[1] - oy for p in points]
    terms = (xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n))
    return math.fsum(terms) / 2.0


def side_label(a: str, b: str) -> str:
    return f"{a}–{b}"


def _arc_params(c: float, radius: float, large: bool) -> tuple[float, float, float] | None:
    """(central angle θ, segment area S, arc length) for a chord c, or None if R < c/2."""
    if radius < c / 2.0 * (1.0 - 1e-12):
        return None
    h = c / 2.0
    half = math.atan2(h, math.sqrt(max(0.0, (radius - h) * (radius + h))))  # well-conditioned
    theta = 2.0 * math.pi - 2.0 * half if large else 2.0 * half
    seg = radius * radius / 2.0 * (theta - math.sin(theta))
    return theta, seg, radius * theta


def _arc_geometry(a: Pt, b: Pt, radius: float, theta: float, side: str) -> tuple[Pt, Pt]:
    """(centre, unit normal towards the bulge) of the arc on chord a→b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    c = math.hypot(dx, dy)
    ux, uy = dx / c, dy / c
    # right of travel (x east, y north): (uy, −ux)
    nb = (uy, -ux) if side == "right" else (-uy, ux)
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    h = radius * math.cos(theta / 2.0)
    return (mx - nb[0] * h, my - nb[1] * h), nb


def arc_points(a: Pt, b: Pt, radius: float, side: str, large: bool, segments: int) -> list[Pt]:
    """Interior points of the arc a→b (excluding a and b), for drawing and tests."""
    c = math.hypot(b[0] - a[0], b[1] - a[1])
    params = _arc_params(c, radius, large)
    if params is None or segments < 2:
        return []
    theta = params[0]
    (cx, cy), _ = _arc_geometry(a, b, radius, theta, side)
    start = math.atan2(a[1] - cy, a[0] - cx)
    # bulge right ⇒ counter-clockwise around the centre (y up), minor or major arc alike
    step = (theta if side == "right" else -theta) / segments
    return [
        (cx + radius * math.cos(start + k * step), cy + radius * math.sin(start + k * step))
        for k in range(1, segments)
    ]


def _seg_dist(p: Pt, a: Pt, b: Pt) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    if ll == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _cross3(o: Pt, a: Pt, b: Pt) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_touch(a: Pt, b: Pt, c: Pt, d: Pt, tol: float = TOUCH_TOL) -> bool:
    """True when segments ab and cd cross or come within ``tol`` of each other."""
    d1, d2 = _cross3(c, d, a), _cross3(c, d, b)
    d3, d4 = _cross3(a, b, c), _cross3(a, b, d)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return min(_seg_dist(a, c, d), _seg_dist(b, c, d), _seg_dist(c, a, b), _seg_dist(d, a, b)) < tol


def find_self_intersection(ring: Sequence[Pt]) -> tuple[int, int] | None:
    """First pair of edge indices (i, j) of a closed ring that touch or cross, else None.
    Adjacent edges only count when they fold back onto each other (a spike)."""
    n = len(ring)
    edges = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    boxes = [(min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])) for a, b in edges]
    order = sorted(range(n), key=lambda k: boxes[k][0])
    for oi, i in enumerate(order):
        _, x1, y0, y1 = boxes[i]
        for j in order[oi + 1 :]:
            if boxes[j][0] > x1 + TOUCH_TOL:
                break
            if boxes[j][3] < y0 - TOUCH_TOL or boxes[j][2] > y1 + TOUCH_TOL:
                continue
            lo, hi = min(i, j), max(i, j)
            adjacent = hi - lo == 1 or (lo == 0 and hi == n - 1)
            if adjacent:
                if _folds_back(edges[lo], edges[hi], lo == 0 and hi == n - 1):
                    return lo, hi
                continue
            if segments_touch(*edges[i], *edges[j]):
                return lo, hi
    return None


def _folds_back(e1: tuple[Pt, Pt], e2: tuple[Pt, Pt], wrap: bool) -> bool:
    first, second = (e2, e1) if wrap else (e1, e2)
    (a, b), (_, c) = first, second
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
    if lu == 0 or lv == 0:
        return False
    return abs(ux * vy - uy * vx) < TOUCH_TOL * max(lu, lv) and ux * vx + uy * vy < 0


# ------------------------------------------------------------------------------- analysis


def clean_vertices(vertices: Sequence[ParcelVertex], sink: IssueSink) -> list[ParcelVertex]:
    """Drop a repeated closing vertex silently and consecutive duplicates with a warning."""
    pts = list(vertices)
    if len(pts) > 1 and _close(pts[0], pts[-1]):
        pts = pts[:-1]
    out: list[ParcelVertex] = []
    for v in pts:
        if out and _close(out[-1], v):
            sink.warning(
                "PARCEL_DUPLICATE_VERTEX",
                f"Vertex {v.name} repeats vertex {out[-1].name}; removed",
                point=v.name,
                other=out[-1].name,
            )
            continue
        out.append(v)
    if len(out) > 1 and _close(out[0], out[-1]):
        out.pop()
    seen: dict[str, ParcelVertex] = {}
    for v in out:
        prev = seen.get(v.name)
        if prev is not None and not _close(prev, v):
            sink.warning(
                "PARCEL_DUPLICATE_NAME",
                f"The name {v.name} is used for two different vertices",
                point=v.name,
            )
        seen.setdefault(v.name, v)
    return out


def _close(a: ParcelVertex, b: ParcelVertex) -> bool:
    return math.hypot(a.x - b.x, a.y - b.y) < DUPLICATE_TOL


def analyze_parcel(parcel: Parcel) -> ParcelGeometry:
    """Geometry, tables and validation of one parcel (arcs supported)."""
    sink = IssueSink()
    verts = clean_vertices(parcel.vertices, sink)
    n = len(verts)
    if n < 3:
        sink.error(
            "PARCEL_TOO_FEW_VERTICES",
            f"A parcel needs at least 3 distinct vertices ({n} given)",
            count=n,
        )
        return _geometry(parcel, verts, [], None, sink.items)
    ox, oy = verts[0].x, verts[0].y
    loc = [(v.x - ox, v.y - oy) for v in verts]
    sides: list[SideRow] = []
    seg_terms: list[float] = []  # signed segment areas
    seg_mx: list[float] = []
    seg_my: list[float] = []
    lengths: list[float] = []
    test_ring: list[Pt] = []
    for i, v in enumerate(verts):
        w = verts[(i + 1) % n]
        a, b = loc[i], loc[(i + 1) % n]
        c = math.hypot(b[0] - a[0], b[1] - a[1])
        row = SideRow(frm=v.name, to=w.name, length=c, azimuth=grid_azimuth(v.x, v.y, w.x, w.y))
        test_ring.append(a)
        if v.arc is None:
            lengths.append(c)
            sides.append(row)
            continue
        params = _arc_params(c, v.arc.radius, v.arc.large)
        if params is None:
            sink.error(
                "PARCEL_ARC_RADIUS",
                f"Arc {side_label(v.name, w.name)}: radius {v.arc.radius:.3f} m is smaller "
                f"than half the chord ({c / 2:.3f} m)",
                side=side_label(v.name, w.name),
                radius=round(v.arc.radius, 3),
                half_chord=round(c / 2, 3),
            )
            lengths.append(c)
            sides.append(row)
            continue
        theta, seg, arc_len = params
        sign = 1.0 if v.arc.side == "right" else -1.0
        centre, nb = _arc_geometry(a, b, v.arc.radius, theta, v.arc.side)
        dist = 4.0 * v.arc.radius * math.sin(theta / 2.0) ** 3 / (3.0 * (theta - math.sin(theta)))
        seg_terms.append(sign * seg)
        seg_mx.append(sign * seg * (centre[0] + nb[0] * dist))
        seg_my.append(sign * seg * (centre[1] + nb[1] * dist))
        lengths.append(arc_len)
        test_ring.extend(arc_points(a, b, v.arc.radius, v.arc.side, v.arc.large, ARC_TEST_SEGMENTS))
        sides.append(
            row.model_copy(
                update={
                    "arc_length": arc_len,
                    "radius": v.arc.radius,
                    "central_angle": theta,
                    "segment_area": seg,
                }
            )
        )
    if any(i.severity == "error" for i in sink.items):
        return _geometry(parcel, verts, sides, None, sink.items)

    hit = find_self_intersection(test_ring)
    if hit is not None:
        s1, s2 = (_side_of_test_edge(verts, k) for k in hit)
        sink.error(
            "PARCEL_SELF_INTERSECTION",
            f"The boundary crosses itself: sides {s1} and {s2}",
            side_a=s1,
            side_b=s2,
        )
        return _geometry(parcel, verts, sides, None, sink.items)

    terms = [loc[i][0] * loc[(i + 1) % n][1] - loc[(i + 1) % n][0] * loc[i][1] for i in range(n)]
    a_poly = math.fsum(terms) / 2.0
    a_signed = math.fsum([a_poly, *seg_terms])
    if abs(a_signed) < ZERO_AREA_TOL:
        sink.error("PARCEL_ZERO_AREA", "The parcel has zero area")
        return _geometry(parcel, verts, sides, None, sink.items)
    # polygon first moments: Σ (xᵢ + xᵢ₊₁)·termᵢ / 6
    mx = math.fsum((loc[i][0] + loc[(i + 1) % n][0]) * terms[i] for i in range(n)) / 6.0
    my = math.fsum((loc[i][1] + loc[(i + 1) % n][1]) * terms[i] for i in range(n)) / 6.0
    cx = math.fsum([mx, *seg_mx]) / a_signed
    cy = math.fsum([my, *seg_my]) / a_signed
    metrics = (abs(a_signed), math.fsum(lengths), a_signed, (ox + cx, oy + cy))
    return _geometry(parcel, verts, sides, metrics, sink.items)


def _side_of_test_edge(verts: list[ParcelVertex], k: int) -> str:
    """Map an edge of the densified test ring back to the parcel side it belongs to."""
    n = len(verts)
    idx = 0
    for i, v in enumerate(verts):
        span = ARC_TEST_SEGMENTS if v.arc is not None else 1
        if k < idx + span:
            return side_label(v.name, verts[(i + 1) % n].name)
        idx += span
    return side_label(verts[-1].name, verts[0].name)


def _geometry(
    parcel: Parcel,
    verts: list[ParcelVertex],
    sides: list[SideRow],
    metrics: tuple[float, float, float, Pt] | None,
    issues: list[Issue],
) -> ParcelGeometry:
    area = perimeter = None
    orientation = None
    centroid = None
    if metrics is not None:
        area, perimeter, signed, (cx, cy) = metrics
        orientation = "counterclockwise" if signed > 0 else "clockwise"
        centroid = XYPoint(x=cx, y=cy)
    return ParcelGeometry(
        label=parcel.label,
        kaek=parcel.kaek,
        vertices=verts,
        sides=sides,
        area=area,
        perimeter=perimeter,
        orientation=orientation,
        centroid=centroid,
        has_arcs=any(v.arc is not None for v in verts),
        valid=metrics is not None,
        issues=issues,
    )


# ------------------------------------------------------------------------ area comparison


def area_tolerance(
    rule: AreaToleranceRule, reference: float, perimeter: float | None = None
) -> float:
    """Tolerance T(E) in m² for reference area E (see :class:`AreaToleranceRule`); the
    cadastral rule also needs the perimeter Π. ``cap_percent`` caps the result."""
    t = _raw_tolerance(rule, reference, perimeter)
    if rule.cap_percent is not None:
        t = min(t, rule.cap_percent / 100.0 * reference)
    return t


def cadastre_tolerance(area: float, perimeter: float, u0: float) -> float:
    """Hellenic Cadastre area tolerance A = U0·Π·(1 + U0/√E), algebraically equal to the
    published [(√E + 2·U0)² − E]·Π / (4·√E) (ΟΚΧΕ 461/03/2008, ΦΕΚ Β΄ 1510/2008); the
    factored form avoids the cancellation of (√E + 2U0)² − E for large E."""
    if area <= 0:
        raise ValueError("The cadastral tolerance needs a positive area")
    return u0 * perimeter * (1.0 + u0 / math.sqrt(area))


def _raw_tolerance(rule: AreaToleranceRule, reference: float, perimeter: float | None) -> float:
    if rule.kind == "cadastre":
        if rule.u0 is None:
            raise ValueError("The cadastral tolerance needs U0")
        if perimeter is None:
            raise ValueError("The cadastral tolerance needs the parcel perimeter")
        return cadastre_tolerance(reference, perimeter, rule.u0)
    if rule.kind == "fixed":
        if rule.value is None:
            raise ValueError("A fixed tolerance needs a value in m²")
        return rule.value
    if rule.kind == "percent":
        if rule.value is None:
            raise ValueError("A percentage tolerance needs a percentage")
        return rule.value / 100.0 * reference
    if rule.a is None or rule.b is None:
        raise ValueError("A formula tolerance a + b·√E needs both a and b")
    return rule.a + rule.b * math.sqrt(reference)


def compare_areas(req: AreaCompareRequest) -> AreaCompareResult:
    """Surveyed vs deed vs Cadastre area: differences, percentages and the user's tolerance."""
    sink = IssueSink()
    perimeter = req.perimeter
    if req.parcel is not None:
        geo = analyze_parcel(req.parcel)
        sink.items.extend(geo.issues)
        if geo.area is None:
            return AreaCompareResult(
                surveyed_area=0.0, rows=[], tolerance=req.tolerance, issues=sink.items
            )
        surveyed = req.surveyed_area if req.surveyed_area is not None else geo.area
        perimeter = perimeter if perimeter is not None else geo.perimeter
    elif req.surveyed_area is not None:
        surveyed = req.surveyed_area
    else:
        raise ValueError("Give the surveyed area or the parcel vertices")
    pairs: list[tuple[str, float, float | None]] = [
        ("surveyed_vs_deed", surveyed, req.deed_area),
        ("surveyed_vs_cadastre", surveyed, req.cadastre_area),
        ("cadastre_vs_deed", req.cadastre_area or 0.0, req.deed_area),
    ]
    rows: list[AreaCompareRow] = []
    for kind, value, ref in pairs:
        if ref is None or (kind == "cadastre_vs_deed" and req.cadastre_area is None):
            continue
        diff = value - ref
        tol = within = None
        if req.tolerance is not None:
            tol = area_tolerance(req.tolerance, ref, perimeter)
            within = abs(diff) <= tol
            if not within:
                sink.warning(
                    "PARCEL_AREA_OUTSIDE_TOLERANCE",
                    f"{kind}: difference {diff:.2f} m² exceeds the chosen limit {tol:.2f} m²",
                    kind=kind,
                    difference=round(diff, 2),
                    tolerance=round(tol, 2),
                    source=req.tolerance.source or "—",
                )
        rows.append(
            AreaCompareRow(
                kind=kind,  # type: ignore[arg-type]
                area=value,
                reference_area=ref,
                difference=diff,
                difference_percent=diff / ref * 100.0 if ref > 0 else None,
                tolerance=tol,
                within=within,
            )
        )
    return AreaCompareResult(
        surveyed_area=surveyed,
        perimeter=perimeter,
        rows=rows,
        tolerance=req.tolerance,
        issues=sink.items,
    )
