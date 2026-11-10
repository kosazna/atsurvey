"""Topology checks of the Hellenic Cadastre on a :class:`Drawing` ([S1] §4.5.1, §4.5.3;
[S5] ΣΤ.10–12).

* within a layer: valid polygons, no duplicate entities, no overlaps, no gaps, and every vertex
  of a polygon that lies on the boundary of an adjacent polygon is also a vertex of it (the
  #1 cause of rejection: "a shared vertex missing in one of two adjacent polygons");
* PST_KAEK: exactly one KAEK TEXT with its insertion point inside each polygon;
* ΔΓΜ for a deed: LINE_XM, LINE_XM_VST, VST_FINAL, EAS_FINAL inside PST_KAEK, and the union of
  DGM_PROP_FINAL equal to the union of PST_KAEK;
* ΔΓΜ for correction: the outer perimeter of DGM_PROP_FINAL equal to that of PST_KAEK.

The Cadastre publishes no numeric tolerance; it catches mm-level slivers. The thresholds below
are therefore strict: shared vertices must coincide to 1 µm.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable

import shapely
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from ..issues import IssueSink
from ..models import Issue
from .drawing import Drawing, Shape
from .geom import SAME_POINT, label_point, location, polygons_of, seg_dist
from .spec import BY_NAME, DiagramKind, kaek_status

#: Overlaps or outline differences larger than this are reported (m²)
AREA_EPS = 1e-6
#: Vertices of two polygons this close but not identical do not coincide (m)
VERTEX_MISMATCH = 0.01
#: A vertex this close to another polygon's side must also be a vertex of it (m)
T_JUNCTION_TOL = 0.001
#: Two polygons closer than this but not touching leave a gap (m)
GAP_TOL = 0.01
#: Holes in a layer's union narrower than this (2·area/perimeter) are gaps (m)
THIN_HOLE = 0.05
#: At most this many issues per check (then one summary line)
MAX_ISSUES = 50

POLYGON_LAYERS = tuple(s.name for s in BY_NAME.values() if "polygon" in s.forms)
_DEED_INSIDE = ("LINE_XM", "LINE_XM_VST", "VST_FINAL", "EAS_FINAL")

Checks = dict[str, list[Issue]]


def _mm(v: float) -> float:
    return round(v, 3)


class _Capped(IssueSink):
    def __init__(self) -> None:
        super().__init__()
        self.dropped = 0

    def add(self, severity, code, message, **kw):  # type: ignore[override]
        if len(self.items) >= MAX_ISSUES:
            self.dropped += 1
            return
        super().add(severity, code, message, **kw)

    def done(self) -> list[Issue]:
        if self.dropped:
            self.items.append(
                Issue(
                    severity="info",
                    code="DGM_MORE",
                    message=f"{self.dropped} more",
                    params={"count": self.dropped},
                )
            )
        return self.items


def _poly(s: Shape) -> Polygon | None:
    if len(s.coords) < 3:
        return None
    return Polygon(s.coords)


def check_drawing(drawing: Drawing, kind: DiagramKind) -> Checks:
    """All topology checks; returns issues per check id."""
    checks: dict[str, _Capped] = defaultdict(_Capped)
    polys: dict[str, list[tuple[Shape, Polygon]]] = {}
    for layer in POLYGON_LAYERS:
        items: list[tuple[Shape, Polygon]] = []
        for s in drawing.on(layer, "polygon"):
            p = _poly(s)
            if _valid_polygon(s, p, checks["polygons_valid"]):
                items.append((s, p))  # type: ignore[arg-type]
        polys[layer] = items
    _duplicates(drawing, checks["duplicates"])
    for layer, items in polys.items():
        if len(items) > 1:
            _pairs(layer, items, checks)
            _thin_holes(layer, [p for _, p in items], checks["gaps"])
    _kaek_texts(drawing, polys.get("PST_KAEK", []), checks["kaek_text"])
    if kind in ("deed", "correction"):
        _outline(drawing, polys, kind, checks["outline"])
    ids = ("polygons_valid", "duplicates", "overlaps", "shared_vertices", "gaps", "kaek_text")
    out = {k: checks[k].done() for k in ids}
    if kind in ("deed", "correction"):
        out["outline"] = checks["outline"].done()
    return out


def _valid_polygon(s: Shape, p: Polygon | None, sink: IssueSink) -> bool:
    if p is None or p.area <= AREA_EPS:
        x, y = s.coords[0] if s.coords else (math.nan, math.nan)
        sink.error(
            "DGM_POLYGON_DEGENERATE",
            f"Degenerate polygon on {s.layer} ({s.handle})",
            layer=s.layer,
            handle=s.handle,
            x=_mm(x),
            y=_mm(y),
        )
        return False
    if not p.is_valid:
        reason = shapely.is_valid_reason(p)
        x, y = _reason_xy(reason, s)
        sink.error(
            "DGM_POLYGON_INVALID",
            f"Self-intersecting polygon on {s.layer} ({s.handle}) at {x}, {y}",
            layer=s.layer,
            handle=s.handle,
            x=_mm(x),
            y=_mm(y),
        )
        return False
    return True


def _reason_xy(reason: str, s: Shape) -> tuple[float, float]:
    # GEOS: "Self-intersection[458793.5 4258956.5]"
    if "[" in reason and "]" in reason:
        try:
            a, b = reason[reason.index("[") + 1 : reason.index("]")].split()[:2]
            return float(a), float(b)
        except ValueError:
            pass
    return s.coords[0]


def _shape_key(s: Shape) -> tuple:
    pts = tuple((round(x / SAME_POINT), round(y / SAME_POINT)) for x, y in s.coords)
    if s.form == "polygon":
        return (s.layer, s.form, tuple(sorted(set(pts))), len(pts))
    if s.form == "polyline":
        return (s.layer, s.form, min(pts, pts[::-1]))
    return (s.layer, s.form, pts, s.text)


def _duplicates(drawing: Drawing, sink: IssueSink) -> None:
    seen: dict[tuple, Shape] = {}
    for s in drawing.shapes:
        key = _shape_key(s)
        first = seen.get(key)
        if first is None:
            seen[key] = s
            continue
        x, y = s.coords[0]
        sink.error(
            "DGM_DUPLICATE",
            f"Duplicate entity on {s.layer}: {s.handle} = {first.handle}",
            layer=s.layer,
            handle=s.handle,
            other=first.handle,
            x=_mm(x),
            y=_mm(y),
        )


def _pairs(layer: str, items: list[tuple[Shape, Polygon]], checks: dict[str, _Capped]) -> None:
    geoms = [p for _, p in items]
    tree = STRtree(geoms)
    left, right = tree.query(geoms, predicate="dwithin", distance=max(GAP_TOL, VERTEX_MISMATCH))
    dup_keys = {_shape_key(s) for s, _ in items}
    for i, j in zip(left.tolist(), right.tolist(), strict=True):
        if i >= j:
            continue
        (sa, pa), (sb, pb) = items[i], items[j]
        if _shape_key(sa) == _shape_key(sb) and _shape_key(sa) in dup_keys:
            continue  # reported as duplicate
        d = pa.distance(pb)
        if d > 0:
            if d <= GAP_TOL:
                a, b = shapely.shortest_line(pa, pb).coords
                checks["gaps"].error(
                    "DGM_GAP",
                    f"Gap of {d * 1000:.1f} mm between {sa.handle} and {sb.handle} on {layer}",
                    layer=layer,
                    handle=sa.handle,
                    other=sb.handle,
                    mm=round(d * 1000, 1),
                    x=_mm((a[0] + b[0]) / 2),
                    y=_mm((a[1] + b[1]) / 2),
                )
        else:
            inter = pa.intersection(pb)
            if inter.area > AREA_EPS:
                x, y = location(inter)
                checks["overlaps"].error(
                    "DGM_OVERLAP",
                    f"Polygons {sa.handle} and {sb.handle} on {layer} overlap by {inter.area:.6f} m²",
                    layer=layer,
                    handle=sa.handle,
                    other=sb.handle,
                    area=round(inter.area, 6),
                    x=_mm(x),
                    y=_mm(y),
                )
        _vertices(layer, sa, sb, checks["shared_vertices"])
        _vertices(layer, sb, sa, checks["shared_vertices"])


def _vertices(layer: str, sa: Shape, sb: Shape, sink: IssueSink) -> None:
    """Vertices of A that should also be vertices of B."""
    ring_b = sb.coords
    n = len(ring_b)
    for v in dict.fromkeys(sa.coords):
        dv = min(math.hypot(v[0] - q[0], v[1] - q[1]) for q in ring_b)
        if dv <= SAME_POINT:
            continue
        if dv <= VERTEX_MISMATCH:
            sink.error(
                "DGM_VERTEX_MISMATCH",
                f"Vertex of {sa.handle} is {dv * 1000:.1f} mm from a vertex of {sb.handle} on {layer}",
                layer=layer,
                handle=sa.handle,
                other=sb.handle,
                mm=round(dv * 1000, 1),
                x=_mm(v[0]),
                y=_mm(v[1]),
            )
            continue
        d = min(seg_dist(v, ring_b[k], ring_b[(k + 1) % n])[0] for k in range(n))
        if d <= T_JUNCTION_TOL:
            sink.error(
                "DGM_SHARED_VERTEX_MISSING",
                f"Vertex ({v[0]:.3f}, {v[1]:.3f}) of {sa.handle} lies on a side of {sb.handle} "
                f"on {layer} but is not a vertex of it",
                layer=layer,
                handle=sb.handle,
                other=sa.handle,
                x=_mm(v[0]),
                y=_mm(v[1]),
            )


def _thin_holes(layer: str, geoms: list[Polygon], sink: IssueSink) -> None:
    union = shapely.unary_union(geoms)
    for poly in polygons_of(union):
        for ring in poly.interiors:
            hole = Polygon(ring)
            if hole.length > 0 and 2 * hole.area / hole.length < THIN_HOLE:
                x, y = location(hole)
                sink.error(
                    "DGM_GAP_SLIVER",
                    f"Sliver gap of {hole.area:.6f} m² between polygons of {layer}",
                    layer=layer,
                    area=round(hole.area, 6),
                    x=_mm(x),
                    y=_mm(y),
                )


def _kaek_texts(drawing: Drawing, polys: list[tuple[Shape, Polygon]], sink: IssueSink) -> None:
    texts = drawing.on("PST_KAEK", "text")
    inside: dict[int, list[Shape]] = defaultdict(list)
    for t in texts:
        pt = Point(t.coords[0])
        hits = [k for k, (_, p) in enumerate(polys) if p.contains(pt)]
        if not hits:
            sink.error(
                "DGM_KAEK_TEXT_OUTSIDE",
                f"KAEK text «{t.text}» ({t.handle}) is not inside a PST_KAEK polygon",
                handle=t.handle,
                text=t.text or "",
                x=_mm(t.coords[0][0]),
                y=_mm(t.coords[0][1]),
            )
        for k in hits:
            inside[k].append(t)
        status = kaek_status((t.text or "").strip())
        if status == "invalid":
            sink.warning(
                "DGM_KAEK_FORMAT",
                f"«{t.text}» is not a 12-digit KAEK",
                handle=t.handle,
                text=t.text or "",
                x=_mm(t.coords[0][0]),
                y=_mm(t.coords[0][1]),
            )
    seen: dict[str, Shape] = {}
    for k, (s, p) in enumerate(polys):
        found = inside.get(k, [])
        x, y = label_point(p)
        if not found:
            sink.error(
                "DGM_KAEK_TEXT_MISSING",
                f"PST_KAEK polygon {s.handle} has no KAEK text inside",
                handle=s.handle,
                x=_mm(x),
                y=_mm(y),
            )
        elif len(found) > 1:
            sink.error(
                "DGM_KAEK_TEXT_MULTIPLE",
                f"PST_KAEK polygon {s.handle} contains {len(found)} texts",
                handle=s.handle,
                count=len(found),
                x=_mm(x),
                y=_mm(y),
            )
        for t in found[:1]:
            kaek = (t.text or "").strip()
            if kaek in seen:
                sink.warning(
                    "DGM_KAEK_DUPLICATE",
                    f"KAEK {kaek} appears in two polygons",
                    kaek=kaek,
                    handle=s.handle,
                    x=_mm(x),
                    y=_mm(y),
                )
            seen[kaek] = s


def _outline(
    drawing: Drawing,
    polys: dict[str, list[tuple[Shape, Polygon]]],
    kind: DiagramKind,
    sink: IssueSink,
) -> None:
    pst = [p for _, p in polys.get("PST_KAEK", [])]
    final = [p for _, p in polys.get("DGM_PROP_FINAL", [])]
    if not pst:
        return
    u_pst = shapely.unary_union(pst)
    if final:
        compare_outlines(u_pst, shapely.unary_union(final), "DGM_PROP_FINAL", sink)
    if kind != "deed":
        return
    zone = u_pst.buffer(SAME_POINT, join_style="mitre")
    for layer in _DEED_INSIDE:
        for s in drawing.on(layer):
            g: BaseGeometry = Polygon(s.coords) if s.form == "polygon" else LineString(s.coords)
            if s.form not in ("polygon", "polyline") or zone.covers(g):
                continue
            outside = g.difference(zone)
            x, y = location(outside) if not outside.is_empty else s.coords[0]
            sink.error(
                "DGM_OUTSIDE_PST",
                f"{layer} ({s.handle}) extends beyond PST_KAEK",
                layer=layer,
                handle=s.handle,
                x=_mm(x),
                y=_mm(y),
            )


def compare_outlines(
    u_pst: BaseGeometry, u_final: BaseGeometry, layer: str, sink: IssueSink
) -> None:
    """Union of ``layer`` vs union of PST_KAEK: parts outside (Π1 of [S5] ΣΤ.10) and parts of
    PST_KAEK not covered (Π2, Π3), each with a coordinate pair."""
    parts: list[tuple[str, BaseGeometry]] = [
        ("DGM_OUTLINE_EXCEEDS", u_final.difference(u_pst)),
        ("DGM_OUTLINE_SHORT", u_pst.difference(u_final)),
    ]
    for code, diff in parts:
        for piece in polygons_of(diff):
            if piece.area <= AREA_EPS:
                continue
            x, y = location(piece)
            sink.error(
                code,
                f"{layer} and PST_KAEK differ by {piece.area:.6f} m² near ({x:.3f}, {y:.3f})",
                layer=layer,
                area=round(piece.area, 6),
                x=_mm(x),
                y=_mm(y),
            )


def issue_counts(checks: Checks) -> Callable[[str], int]:
    return lambda sev: sum(1 for v in checks.values() for i in v if i.severity == sev)
