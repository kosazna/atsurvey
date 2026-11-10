"""ΔΓΜ for a deed (για εγγραπτέα πράξη): subdivision (κατάτμηση) and merge (συνένωση).

The outer perimeter of the involved cadastral parcels is preserved; only internal lines change
([S3] §A). The existing boundaries come from the cadastral diagram, not from the survey.

Subdivision: the partition line of the topographic diagram is clipped to the PST_KAEK polygon
(LINE_XM, [S1] Table I row 19) and DGM_PROP_FINAL is built from PST_KAEK + LINE_XM. "The
partition line of the ΤΔ is respected regardless of the area of the resulting parts" ([S8],
subdivision example, error 4). A line end that stops inside the parcel (the survey boundary
lies inside the cadastral one) is extended along its last segment to the PST_KAEK boundary or
to another partition line.

Merge: DGM_PROP_FINAL = the union of the parcels (``parcels_merge.union_boundary``, exact
coordinates); LINE_XM holds the abolished common boundaries (our reading of the rule
"19 ⇔ 24" of [S1] §4.5.2β — to be confirmed against the Cadastre's merge example).
"""

from __future__ import annotations

import itertools
import math

import shapely
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, split

from ..parcels import analyze_parcel
from ..parcels_coverage import check_coverage
from ..parcels_merge import union_boundary
from ..parcels_models import CoverageRequest, Parcel
from .context import Ctx, Ring
from .geom import (
    SAME_POINT,
    NamedPt,
    drop_collinear_spikes,
    insert_on_sides,
    lines_of,
    polygon_rings,
    seg_dist,
    snap_ring,
    to_vertices,
)

#: The splitting copy of a partition line overshoots the boundary by this much (m), so the
#: overlay sees a proper crossing; LINE_XM itself ends exactly on the boundary.
OVERSHOOT = 0.01
#: Parts smaller than this are reported (m²)
TINY_PART = 0.01

Pt = tuple[float, float]


def subdivision(ctx: Ctx) -> None:
    req = ctx.req
    subj = ctx.pst_by_kaek(req.subject) if req.subject else (ctx.pst[0] if ctx.pst else None)
    if subj is None:
        ctx.sink.error(
            "DGM_SUBJECT_UNKNOWN",
            f"KAEK {req.subject} is not among the parcels",
            kaek=req.subject or "",
        )
        return
    if not req.partition_lines:
        ctx.sink.error("DGM_LINE_REQUIRED", "Give the partition line of the topographic diagram")
        return
    poly = subj.poly
    raw = [_dedupe([(v.x, v.y) for v in ln.vertices]) for ln in req.partition_lines]
    raw = [ln for ln in raw if len(ln) >= 2]
    for src in req.partition_lines:
        for v in src.vertices:
            if poly.covers(Point(v.x, v.y)):
                ctx.reg.add(v.x, v.y, v.name)
    cutters: list[list[Pt]] = []
    xm_lines: list[list[Pt]] = []
    for k, ln in enumerate(raw):
        others = [LineString(o) for j, o in enumerate(raw) if j != k]
        cut, xm = _extend(ln, poly, others, ctx) if req.extend_lines else (ln, ln)
        cutters.append(cut)
        xm_lines.append(xm)
    pieces = polygon_rings(split(poly, MultiLineString(cutters)))
    if len(pieces) < 2:
        ctx.sink.error(
            "DGM_LINE_NO_SPLIT",
            f"The partition line does not divide KAEK {subj.kaek}",
            kaek=subj.kaek or "",
        )
        return
    rings = [drop_collinear_spikes(snap_ring(r, ctx.reg)) for r in pieces]
    rings = _heal(rings)
    rings.sort(key=lambda r: min(ctx.reg.index(p) for p in r))
    labels = req.part_labels or []
    parts: list[Ring] = []
    for i, pts in enumerate(rings):
        label = labels[i] if i < len(labels) and labels[i] else str(i + 1)
        part = ctx.ring("DGM_PROP_FINAL", label, None, pts)
        parts.append(part)
        if part.area < TINY_PART:
            x, y = part.coords[0]
            ctx.sink.warning(
                "DGM_TINY_PART",
                f"Part {label} is only {part.area:.4f} m²",
                label=label,
                area=round(part.area, 4),
                x=round(x, 3),
                y=round(y, 3),
            )
    part_pts = [p for r in parts for p in r.pts]
    for xm in xm_lines:
        for piece in lines_of(poly.intersection(LineString(xm))):
            pts = [ctx.reg.add(x, y) for x, y in piece]
            pts = [p for i, p in enumerate(pts) if i == 0 or p is not pts[i - 1]]
            if len(pts) >= 2:
                pts = _insert_on_line(pts, part_pts)
                ctx.lines.append(("LINE_XM", pts))
                _dangling(ctx, pts, parts)
    _coverage(ctx, subj, parts)


def _dedupe(coords: list[Pt]) -> list[Pt]:
    out: list[Pt] = []
    for c in coords:
        if not out or math.hypot(c[0] - out[-1][0], c[1] - out[-1][1]) > SAME_POINT:
            out.append(c)
    return out


def _extend(ln: list[Pt], poly, others: list[LineString], ctx: Ctx) -> tuple[list[Pt], list[Pt]]:
    """(splitting copy, LINE_XM copy) of a partition line whose ends are extended to the
    parcel boundary or to another partition line."""
    cut, xm = list(ln), list(ln)
    boundary = shapely.union_all([poly.exterior, *others])
    span = math.hypot(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1]) * 2 + 1
    for end, prev in ((0, 1), (-1, -2)):
        ex, ey = ln[end]
        px, py = ln[prev]
        length = math.hypot(ex - px, ey - py)
        dx, dy = (ex - px) / length, (ey - py) / length
        e = Point(ex, ey)
        if boundary.distance(e) <= SAME_POINT:
            hit = (ex, ey)
        elif poly.contains(e):
            ray = LineString([(ex, ey), (ex + dx * span, ey + dy * span)])
            cands = [
                (math.hypot(x - ex, y - ey), (x, y))
                for g in shapely.get_parts(ray.intersection(boundary))
                for x, y in g.coords
            ]
            cands = [c for c in cands if c[0] > SAME_POINT]
            if not cands:  # pragma: no cover - a ray from inside always leaves the polygon
                continue
            dist, hit = min(cands)
            ctx.sink.info(
                "DGM_LINE_EXTENDED",
                f"Partition line extended by {dist:.3f} m to the boundary",
                length=round(dist, 3),
                x=round(hit[0], 3),
                y=round(hit[1], 3),
            )
        else:
            continue  # outside: clipped by the overlay
        over = (hit[0] + dx * OVERSHOOT, hit[1] + dy * OVERSHOOT)
        if end == 0:
            cut = [over, *cut] if hit == (ex, ey) else [over, *cut[1:]]
            xm = [hit, *xm[1:]]
        else:
            cut = [*cut, over] if hit == (ex, ey) else [*cut[:-1], over]
            xm = [*xm[:-1], hit]
    return cut, xm


def _heal(rings: list[list[NamedPt]]) -> list[list[NamedPt]]:
    """Insert every part vertex that lies on another part's side (shared T-junctions)."""
    pool = {id(p): p for r in rings for p in r}
    out = []
    for r in rings:
        healed, _ = insert_on_sides(r, pool.values())
        out.append(healed)
    return out


def _insert_on_line(pts: list[NamedPt], pool: list[NamedPt]) -> list[NamedPt]:
    """Polyline with every pool point lying on one of its segments inserted (in order)."""
    out = [pts[0]]
    for a, b in itertools.pairwise(pts):
        on = []
        for p in pool:
            if p is a or p is b:
                continue
            d, t = seg_dist(p.xy, a.xy, b.xy)
            if d <= SAME_POINT and 0.0 < t < 1.0:
                on.append((t, p))
        seen = {id(q) for q in out}
        out.extend(p for _, p in sorted(on, key=lambda tp: tp[0]) if id(p) not in seen)
        out.append(b)
    return out


def _dangling(ctx: Ctx, pts: list[NamedPt], parts: list[Ring]) -> None:
    for a, b in itertools.pairwise(pts):
        mid = Point((a.x + b.x) / 2, (a.y + b.y) / 2)
        touching = sum(1 for r in parts if r.poly.exterior.distance(mid) <= SAME_POINT)
        if touching < 2:
            ctx.sink.warning(
                "DGM_LINE_DANGLING",
                "Part of the partition line does not separate two parts",
                x=round(mid.x, 3),
                y=round(mid.y, 3),
            )
            return


def _coverage(ctx: Ctx, outline: Ring, parts: list[Ring]) -> None:
    """Parts must tile the cadastral parcel exactly (``parcels_coverage.check_coverage``)."""
    res = check_coverage(
        CoverageRequest(
            outline=Parcel(vertices=to_vertices(outline.pts)),
            parts=[Parcel(vertices=to_vertices(r.pts)) for r in parts],
        )
    )
    if not res.ok:
        ctx.sink.items.extend(res.issues)


def merge(ctx: Ctx) -> None:
    req = ctx.req
    wanted = req.merge or [r.kaek for r in ctx.pst if r.kaek]
    members: list[Ring] = []
    for k in wanted:
        r = ctx.pst_by_kaek(k)
        if r is None:
            ctx.sink.error("DGM_SUBJECT_UNKNOWN", f"KAEK {k} is not among the parcels", kaek=k)
            return
        members.append(r)
    if len(members) < 2:
        ctx.sink.error("DGM_MERGE_NEEDS_TWO", "A merge needs at least two parcels")
        return
    geos = [analyze_parcel(Parcel(kaek=r.kaek, vertices=to_vertices(r.pts))) for r in members]
    union, _, _ = union_boundary(geos, SAME_POINT, ctx.sink)
    if union is None:
        return
    pts = [ctx.reg.add(x, y, name) for name, x, y in union.loop]
    label = "+".join(r.kaek or "" for r in members)
    ctx.ring("DGM_PROP_FINAL", label, None, pts)
    shared = [
        a.poly.exterior.intersection(b.poly.exterior)
        for i, a in enumerate(members)
        for b in members[i + 1 :]
    ]
    segs = [ln for g in shared for ln in lines_of(g) if LineString(ln).length > SAME_POINT]
    if segs:
        for ln in lines_of(linemerge(MultiLineString(segs))):
            line = [ctx.reg.add(x, y) for x, y in ln]
            ctx.lines.append(
                ("LINE_XM", [p for i, p in enumerate(line) if i == 0 or p is not line[i - 1]])
            )
