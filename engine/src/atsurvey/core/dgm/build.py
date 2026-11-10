"""Build a ΔΓΜ: geometry of every layer, area tables, change table and the Cadastre's checks.

``build_dgm(request)`` runs the mode (subdivision / merge / correction), adds the survey layers
(TOPO_PROP, TOPO_PROP_NEW, BLD, BOUND_*), compares areas with the Cadastre's tolerance and then
runs the same topology checks as the DXF validator on the result (``topology.check_drawing``).
"""

from __future__ import annotations

import math

from ..parcels import area_tolerance
from .context import Ctx, Ring, load_cadastral, register_parcel
from .correction import correction
from .deed import merge, subdivision
from .drawing import Drawing, Shape
from .geom import PointRegistry, label_point
from .models import AreaComparison, AreaRow, ChangeRow, DgmPoint, DgmRequest, DgmResult
from .spec import NEIGHBOURS, DiagramKind
from .topology import check_drawing


def build_dgm(req: DgmRequest) -> DgmResult:
    ctx = Ctx(req, reg=PointRegistry(req.new_point_prefix))
    kind: DiagramKind = "correction" if req.mode == "correction" else "deed"
    load_cadastral(ctx)
    changes: list[ChangeRow] = []
    if not ctx.failed:
        if req.mode == "subdivision":
            subdivision(ctx)
        elif req.mode == "merge":
            merge(ctx)
        else:
            changes = correction(ctx)
        if req.mode != "correction":
            _set_aside_neighbours(ctx)
    _survey_layers(ctx)
    for old, new in ctx.reg.renamed:
        ctx.sink.warning(
            "DGM_POINT_RENAMED", f"Point name {old} used twice; renamed {new}", old=old, new=new
        )
    if not ctx.failed:
        _check(ctx, kind)
    finals = ctx.on("DGM_PROP_FINAL")
    return DgmResult(
        mode=req.mode,
        kind=kind,
        polygons=[r.model() for r in ctx.rings],
        lines=ctx.line_models(),
        points=_points(ctx),
        areas=_areas(ctx),
        comparisons=_comparisons(ctx),
        changes=changes,
        total_before=math.fsum(r.area for r in ctx.pst),
        total_after=math.fsum(r.area for r in finals),
        ok=not ctx.failed,
        issues=ctx.sink.items,
    )


def _set_aside_neighbours(ctx: Ctx) -> None:
    """For a deed, PST_KAEK must hold only the parcels the deed changes: the union of
    DGM_PROP_FINAL has to equal the union of PST_KAEK ([S1] §4.5.3α, [S5] ΣΤ.10 case 3).
    Other parcels loaded from the ΚΔ are kept for context on the free layer ATS_NEIGHBOURS."""
    req = ctx.req
    if req.mode == "subdivision":
        involved = {req.subject or (ctx.pst[0].kaek if ctx.pst else None)}
    else:
        involved = set(req.merge) if req.merge else {r.kaek for r in ctx.pst}
    for r in ctx.pst:
        if r.kaek not in involved:
            r.layer = NEIGHBOURS
    ctx.pst = [r for r in ctx.pst if r.kaek in involved]


def _survey_layers(ctx: Ctx) -> None:
    req = ctx.req
    for k, p in enumerate(req.topo_prop):
        pts = register_parcel(ctx, p, "TOPO_PROP")
        if pts is not None:
            r = ctx.ring("TOPO_PROP", p.label or p.kaek or f"{k + 1}", p.kaek, pts)
            bound = "BOUND_IMPL" if req.boundary == "implemented" else "BOUND_UNIMPL"
            ctx.rings.append(Ring(bound, r.label, r.kaek, r.pts))
    for k, p in enumerate(req.topo_prop_new):
        pts = register_parcel(ctx, p, "TOPO_PROP_NEW")
        if pts is not None:
            ctx.ring("TOPO_PROP_NEW", p.label or f"{k + 1}", p.kaek, pts)
    for k, p in enumerate(req.buildings):
        pts = register_parcel(ctx, p, "BLD")
        if pts is not None:
            ctx.ring("BLD", p.label or f"Κ{k + 1}", None, pts)
    if req.mode == "correction" and not req.topo_prop:
        ctx.sink.warning(
            "DGM_TOPO_MISSING",
            "A correction ΔΓΜ needs TOPO_PROP (property per title and survey)",
            layer="TOPO_PROP",
        )
    elif req.mode != "correction" and not (req.topo_prop or req.topo_prop_new):
        ctx.sink.warning(
            "DGM_TOPO_MISSING", "A deed ΔΓΜ needs TOPO_PROP or TOPO_PROP_NEW", layer="TOPO_PROP"
        )


def drawing_of(ctx_rings: list[Ring], lines: list[tuple[str, list]]) -> Drawing:
    """Table I content of a build, with the KAEK text at the label point of each PST_KAEK."""
    d = Drawing()
    for k, r in enumerate(ctx_rings):
        d.shapes.append(Shape(r.layer, "polygon", tuple(r.coords), handle=f"#{k + 1}"))
        if r.layer == "PST_KAEK" and r.kaek:
            d.shapes.append(
                Shape(r.layer, "text", (label_point(r.poly),), handle=f"#{k + 1}t", text=r.kaek)
            )
    for k, (layer, pts) in enumerate(lines):
        d.shapes.append(Shape(layer, "polyline", tuple(p.xy for p in pts), handle=f"L{k + 1}"))
    return d


def _check(ctx: Ctx, kind: DiagramKind) -> None:
    checks = check_drawing(drawing_of(ctx.rings, ctx.lines), kind)
    for issues in checks.values():
        ctx.sink.items.extend(issues)


def _points(ctx: Ctx) -> list[DgmPoint]:
    used = {id(p) for r in ctx.rings for p in r.pts} | {id(p) for _, pts in ctx.lines for p in pts}
    return [DgmPoint(name=p.name, x=p.x, y=p.y, new=p.new) for p in ctx.reg.points if id(p) in used]


def _areas(ctx: Ctx) -> list[AreaRow]:
    finals = ctx.on("DGM_PROP_FINAL")
    rows: list[AreaRow] = []
    for p in ctx.pst:
        after = next((f.area for f in finals if f.kaek and f.kaek == p.kaek), None)
        rows.append(
            AreaRow(
                label=p.label,
                kaek=p.kaek,
                before=p.area,
                after=after,
                difference=None if after is None else after - p.area,
            )
        )
    for f in finals:
        if f.kaek is None or ctx.pst_by_kaek(f.kaek) is None:
            rows.append(
                AreaRow(label=f.label, kaek=f.kaek, before=None, after=f.area, difference=None)
            )
    return rows


def _best_match(ring: Ring, others: list[Ring]) -> Ring | None:
    """The polygon overlapping ``ring`` the most, if it covers at least half of either."""
    poly = ring.poly
    best = max(others, key=lambda o: poly.intersection(o.poly).area, default=None)
    if best is None:
        return None
    common = poly.intersection(best.poly).area
    return best if common >= 0.5 * min(ring.area, best.area) else None


def _comparisons(ctx: Ctx) -> list[AreaComparison]:
    """Cadastral area E vs the survey (TOPO_PROP / TOPO_PROP_NEW) or vs the final polygon,
    with the tolerance T(E, Π) of the chosen rule; Π = perimeter on the cadastral diagram."""
    out: list[AreaComparison] = []
    topo, topo_new = ctx.on("TOPO_PROP"), ctx.on("TOPO_PROP_NEW")
    finals = ctx.on("DGM_PROP_FINAL")
    for p in ctx.pst:
        m = _best_match(p, topo)
        if m is not None:
            out.append(_compare(ctx, p, m.area, "survey"))
        if ctx.req.mode == "correction":
            f = next((f for f in finals if f.kaek == p.kaek), None)
            if f is not None:
                out.append(_compare(ctx, p, f.area, "final"))
    if ctx.req.mode != "correction":
        for f in finals:
            m = _best_match(f, topo_new if topo_new else topo if ctx.req.mode == "merge" else [])
            if m is not None:
                out.append(_compare(ctx, f, m.area, "survey"))
    return out


def _compare(ctx: Ctx, ref: Ring, other: float, against: str) -> AreaComparison:
    e, perim = ref.area, ref.perimeter
    diff = other - e
    tol: float | None = None
    within: bool | None = None
    if ctx.req.tolerance is not None and e > 0:
        tol = area_tolerance(ctx.req.tolerance, e, perim)
        within = abs(diff) <= tol
        if not within:
            ctx.sink.warning(
                "DGM_AREA_TOLERANCE",
                f"{ref.label}: difference {diff:.2f} m² exceeds the tolerance {tol:.2f} m²",
                label=ref.label,
                difference=round(diff, 2),
                tolerance=round(tol, 2),
            )
    return AreaComparison(
        label=ref.label,
        kaek=ref.kaek,
        against=against,  # type: ignore[arg-type]
        cadastre_area=e,
        other_area=other,
        difference=diff,
        difference_percent=diff / e * 100.0 if e > 0 else 0.0,
        perimeter=perim,
        tolerance=tol,
        within=within,
    )
