"""ΔΓΜ for correction of geometric data (διόρθωση) and ΤΔΓΜ.

PST_KAEK holds the subject parcel(s) and the affected neighbours as they are in the cadastral
diagram; DGM_PROP_FINAL holds the final polygons of ALL involved parcels; AREA_A (parts cut
from the parcel being corrected, labelled A1, A2, …) and AREA_D (parts claimed from the
neighbours, Δ1, Δ2, …) come from overlaying the two layers ([S1] Table I rows 24–26; [S6] §6;
[S4] §6.1). The change table has the columns «ΤΜΗΜΑ / ΠΕΡΙΓΡΑΦΗ / ΕΜΒΑΔΟ / ΑΠΟ ΚΑΕΚ /
ΣΕ ΚΑΕΚ» with «ΝΕΟ» for parts excluded from the parcel ([S4] §6.2).

Invariants (tested): the total area of PST_KAEK equals that of DGM_PROP_FINAL ([S6] §6), and for
each corrected parcel  final = cadastral − ΣA + ΣΔ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from shapely.geometry import Point

from ..parcels import signed_area
from ..parcels_models import Parcel
from .context import Ctx, Ring, register_parcel
from .geom import (
    NamedPt,
    drop_collinear_spikes,
    insert_on_sides,
    oriented,
    polygon_rings,
    seg_dist,
    snap_ring,
)
from .models import ChangeRow
from .spec import NEW_PARCEL

#: Overlay pieces below this area are slivers from imprecise drawing, not changes (m²)
MIN_PIECE = 1e-4
#: Overlay pieces below this are numerical noise of touching polygons (m²)
NOISE = 1e-8
#: Snaps shorter than this are float noise, not reported (m)
NOISE_SNAP = 1e-9
#: |Σ PST_KAEK − Σ DGM_PROP_FINAL| above this is an error (m²)
TOTAL_TOL = 1e-4


@dataclass
class Piece:
    frm: str
    to: str
    pts: list[NamedPt]
    area: float


def correction(ctx: Ctx) -> list[ChangeRow]:
    req = ctx.req
    known = {r.kaek for r in ctx.pst}
    subjects = list(dict.fromkeys(req.subjects))
    if not subjects:
        ctx.sink.error("DGM_SUBJECTS_REQUIRED", "Choose the parcel(s) being corrected")
    for s in subjects:
        if s not in known:
            ctx.sink.error("DGM_SUBJECT_UNKNOWN", f"KAEK {s} is not among the parcels", kaek=s)
    if not req.finals:
        ctx.sink.error("DGM_FINALS_REQUIRED", "Give the final polygons of all involved parcels")
    if ctx.failed:
        return []
    finals = _load_finals(ctx, known)
    if finals is None:
        return []
    for k in known - {f.kaek for f in finals}:
        ctx.sink.warning("DGM_FINAL_MISSING", f"No final polygon for KAEK {k}", kaek=k or "")
    pieces = _overlay(ctx, finals)
    rows = _changes(ctx, pieces, set(subjects))
    _totals(ctx, finals, rows, subjects)
    return rows


def _load_finals(ctx: Ctx, known: set[str | None]) -> list[Ring] | None:
    req = ctx.req
    seen: set[str] = set()
    snapped: list[float] = []
    raw: list[tuple[str | None, str, list[NamedPt]]] = []
    pst_pts = {id(p): p for r in ctx.pst for p in r.pts}
    for k, f in enumerate(req.finals):
        if f.kaek is not None:
            if f.kaek not in known:
                ctx.sink.error(
                    "DGM_FINAL_UNKNOWN_KAEK",
                    f"Final polygon {k + 1}: KAEK {f.kaek} is not in PST_KAEK",
                    index=k + 1,
                    kaek=f.kaek,
                )
                continue
            if f.kaek in seen:
                ctx.sink.error(
                    "DGM_FINAL_REPEATED", f"Two final polygons for KAEK {f.kaek}", kaek=f.kaek
                )
                continue
            seen.add(f.kaek)
        verts = []
        for v in f.vertices:
            x, y = _snap_to_cadastre(ctx, v.x, v.y, pst_pts, snapped)
            verts.append(v.model_copy(update={"x": x, "y": y}))
        label = f.label or f.kaek or f"{NEW_PARCEL} {k + 1}"
        pts = register_parcel(
            ctx, Parcel(kaek=f.kaek, label=label, vertices=verts), "Τελικό", snap=req.snap_tolerance
        )
        if pts is not None:
            raw.append((f.kaek, label, pts))
    moved = [d for d in snapped if d > NOISE_SNAP]
    if moved:
        ctx.sink.info(
            "DGM_SNAPPED",
            f"{len(moved)} final vertices snapped to the cadastral geometry (up to {max(moved) * 1000:.1f} mm)",
            count=len(moved),
            max_mm=round(max(moved) * 1000, 1),
        )
    if ctx.failed:
        return None
    # heal T-junctions: every final or cadastral vertex on a final side becomes a vertex of it
    pool = {id(p): p for _, _, pts in raw for p in pts} | pst_pts
    finals: list[Ring] = []
    for kaek, label, pts in raw:
        healed, ins = insert_on_sides(pts, pool.values())
        if ins:
            ctx.sink.info(
                "DGM_TJUNCTION_FIXED",
                f"{len(ins)} shared vertices added to {label}",
                label=label,
                count=len(ins),
                points=[p.name for p in ins][:10],
            )
        finals.append(ctx.ring("DGM_PROP_FINAL", label, kaek, healed))
    return finals


def _snap_to_cadastre(
    ctx: Ctx, x: float, y: float, pst_pts: dict, moved: list[float]
) -> tuple[float, float]:
    """Exact cadastral coordinates for a final vertex within the snap tolerance of a PST_KAEK
    vertex, or its projection onto a PST_KAEK side within that tolerance."""
    tol = ctx.req.snap_tolerance
    hit = ctx.reg.find(x, y, tol)
    if hit is not None and id(hit) in pst_pts:
        moved.append(math.hypot(hit.x - x, hit.y - y))
        return hit.x, hit.y
    best: tuple[float, float, float] | None = None
    for r in ctx.pst:
        n = len(r.pts)
        for i in range(n):
            a, b = r.pts[i].xy, r.pts[(i + 1) % n].xy
            d, t = seg_dist((x, y), a, b)
            if d <= tol and 0 < t < 1 and (best is None or d < best[0]):
                best = (d, a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    if best is None:
        return x, y
    moved.append(best[0])
    return best[1], best[2]


def _overlay(ctx: Ctx, finals: list[Ring]) -> list[Piece]:
    pieces: list[Piece] = []
    for p in ctx.pst:
        ppoly = p.poly
        for f in finals:
            if f.kaek == p.kaek:
                continue
            fpoly = f.poly
            if not ppoly.intersects(fpoly):
                continue
            inter = ppoly.intersection(fpoly)
            if inter.area <= NOISE:
                continue
            for ring in polygon_rings(inter):
                pts = drop_collinear_spikes(snap_ring(ring, ctx.reg))
                if len(pts) < 3:
                    continue
                piece = Piece(p.kaek or "", f.kaek or NEW_PARCEL, oriented(pts, ctx.reg), 0.0)
                piece.area = abs(signed_area([q.xy for q in piece.pts]))
                if piece.area <= NOISE:
                    continue
                if piece.area < MIN_PIECE:
                    c = Point(pts[0].xy)
                    ctx.sink.warning(
                        "DGM_SLIVER",
                        f"Sliver of {piece.area:.6f} m² between {piece.frm} and {piece.to}",
                        frm=piece.frm,
                        to=piece.to,
                        area=round(piece.area, 6),
                        x=round(c.x, 3),
                        y=round(c.y, 3),
                    )
                    continue
                pieces.append(piece)
    return pieces


def _changes(ctx: Ctx, pieces: list[Piece], subjects: set[str]) -> list[ChangeRow]:
    def order(pc: Piece) -> tuple:
        cx = math.fsum(p.x for p in pc.pts) / len(pc.pts)
        cy = math.fsum(p.y for p in pc.pts) / len(pc.pts)
        return (pc.frm, pc.to, -cy, cx)

    a_parts, d_parts = [], []
    for pc in sorted(pieces, key=order):
        if pc.frm in subjects:
            a_parts.append(pc)
        elif pc.to in subjects:
            d_parts.append(pc)
        else:
            ctx.sink.warning(
                "DGM_TRANSFER_NEIGHBOURS",
                f"Part moves from {pc.frm} to {pc.to}, neither is being corrected",
                frm=pc.frm,
                to=pc.to,
            )
            a_parts.append(pc)
    if not pieces:
        ctx.sink.error("DGM_NO_CHANGE", "The final polygons do not change any boundary")
    rows: list[ChangeRow] = []
    groups: tuple[tuple[Literal["A", "D"], str, str, list[Piece]], ...] = (
        ("A", "AREA_A", "A", a_parts),
        ("D", "AREA_D", "Δ", d_parts),
    )
    for kind, layer, prefix, group in groups:
        for i, pc in enumerate(group, start=1):
            label = f"{prefix}{i}"
            ctx.rings.append(Ring(layer, label, None, pc.pts))
            names = [p.name for p in pc.pts]
            rows.append(
                ChangeRow(
                    part=label,
                    kind=kind,
                    description=[*names, names[0]],
                    area=pc.area,
                    from_kaek=pc.frm,
                    to_kaek=pc.to,
                )
            )  # type: ignore[arg-type]
    return rows


def _totals(ctx: Ctx, finals: list[Ring], rows: list[ChangeRow], subjects: list[str]) -> None:
    before = math.fsum(r.area for r in ctx.pst)
    after = math.fsum(f.area for f in finals)
    if abs(after - before) > TOTAL_TOL:
        ctx.sink.error(
            "DGM_TOTAL_AREA",
            f"PST_KAEK totals {before:.4f} m², DGM_PROP_FINAL {after:.4f} m²",
            before=round(before, 4),
            after=round(after, 4),
            difference=round(after - before, 4),
        )
    for s in subjects:
        pst = ctx.pst_by_kaek(s)
        fin = next((f for f in finals if f.kaek == s), None)
        if pst is None or fin is None:
            continue
        cut = math.fsum(r.area for r in rows if r.from_kaek == s)
        got = math.fsum(r.area for r in rows if r.to_kaek == s)
        expected = pst.area - cut + got
        if abs(expected - fin.area) > TOTAL_TOL:
            ctx.sink.warning(
                "DGM_PARTS_INCONSISTENT",
                f"KAEK {s}: {pst.area:.2f} − ΣA + ΣΔ = {expected:.2f} m² but the final polygon is {fin.area:.2f} m²",
                kaek=s,
                expected=round(expected, 2),
                final=round(fin.area, 2),
            )
