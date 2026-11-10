"""Shared state of one ΔΓΜ build: validated cadastral parcels, the point registry, outputs."""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Polygon

from ..issues import IssueSink
from ..parcels import analyze_parcel
from ..parcels_models import Parcel
from .geom import NamedPt, PointRegistry, area_of, oriented, perimeter_of, to_vertices
from .models import DgmLine, DgmPolygon, DgmRequest
from .spec import kaek_status


@dataclass
class Ring:
    """A polygon of the build: named exact points (clockwise, first not repeated)."""

    layer: str
    label: str
    kaek: str | None
    pts: list[NamedPt]

    @property
    def coords(self) -> list[tuple[float, float]]:
        return [p.xy for p in self.pts]

    @property
    def poly(self) -> Polygon:
        return Polygon(self.coords)

    @property
    def area(self) -> float:
        return area_of(self.pts)

    @property
    def perimeter(self) -> float:
        return perimeter_of(self.pts)

    def model(self) -> DgmPolygon:
        return DgmPolygon(
            layer=self.layer,
            label=self.label,
            kaek=self.kaek,
            vertices=to_vertices(self.pts),
            area=self.area,
            perimeter=self.perimeter,
        )


@dataclass
class Ctx:
    req: DgmRequest
    sink: IssueSink = field(default_factory=IssueSink)
    reg: PointRegistry = field(default_factory=PointRegistry)
    pst: list[Ring] = field(default_factory=list)
    rings: list[Ring] = field(default_factory=list)
    lines: list[tuple[str, list[NamedPt]]] = field(default_factory=list)

    def pst_by_kaek(self, kaek: str) -> Ring | None:
        return next((r for r in self.pst if r.kaek == kaek), None)

    def ring(self, layer: str, label: str, kaek: str | None, pts: list[NamedPt]) -> Ring:
        r = Ring(layer, label, kaek, oriented(pts, self.reg))
        self.rings.append(r)
        return r

    def on(self, layer: str) -> list[Ring]:
        return [r for r in self.rings if r.layer == layer]

    def line_models(self) -> list[DgmLine]:
        return [DgmLine(layer=lay, vertices=to_vertices(pts)) for lay, pts in self.lines]

    @property
    def failed(self) -> bool:
        return any(i.severity == "error" for i in self.sink.items)


def register_parcel(
    ctx: Ctx, parcel: Parcel, what: str, snap: float | None = None
) -> list[NamedPt] | None:
    """Validate a parcel (``analyze_parcel``: duplicates, self-intersection, zero area) and
    register its vertices. Arcs are not allowed: the DXF layers hold straight polylines."""
    geo = analyze_parcel(parcel)
    label = parcel.kaek or parcel.label or what
    if not geo.valid:
        ctx.sink.error(
            "DGM_PARCEL_INVALID", f"{what} {label} is not a valid polygon", what=what, label=label
        )
        ctx.sink.items.extend(i for i in geo.issues if i.severity == "error")
        return None
    if geo.has_arcs:
        ctx.sink.error(
            "DGM_ARCS", f"{what} {label} has arcs; replace them with chords", label=label
        )
        return None
    pts: list[NamedPt] = []
    for v in geo.vertices:
        p = ctx.reg.add(v.x, v.y, v.name, snap=snap)
        if not pts or pts[-1] is not p:
            pts.append(p)
    while len(pts) > 1 and pts[0] is pts[-1]:
        pts.pop()
    if len(pts) < 3:
        ctx.sink.error(
            "DGM_PARCEL_INVALID", f"{what} {label} collapsed after snapping", what=what, label=label
        )
        return None
    return pts


def load_cadastral(ctx: Ctx) -> None:
    """PST_KAEK: every parcel needs a unique KAEK (12 digits, [S3])."""
    seen: set[str] = set()
    for k, parcel in enumerate(ctx.req.parcels):
        kaek = (parcel.kaek or "").strip()
        if not kaek:
            ctx.sink.error("DGM_KAEK_MISSING", f"Parcel {k + 1} has no KAEK", index=k + 1)
            continue
        if kaek in seen:
            ctx.sink.error("DGM_KAEK_REPEATED", f"KAEK {kaek} given twice", kaek=kaek)
            continue
        seen.add(kaek)
        if kaek_status(kaek) == "invalid":
            ctx.sink.warning("DGM_KAEK_INPUT_FORMAT", f"{kaek} is not a 12-digit KAEK", kaek=kaek)
        pts = register_parcel(ctx, parcel, "ΚΑΕΚ")
        if pts is not None:
            ring = Ring("PST_KAEK", kaek, kaek, oriented(pts, ctx.reg))
            ctx.pst.append(ring)
            ctx.rings.append(ring)
    for old, new in ctx.reg.renamed:
        ctx.sink.warning(
            "DGM_POINT_RENAMED", f"Point name {old} used twice; renamed {new}", old=old, new=new
        )
    ctx.reg.renamed.clear()
