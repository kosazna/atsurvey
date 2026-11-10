"""Structural checks of a DXF against Table I ([S1] §4.5.1–4.5.2, §5.2.1; [S5] ΣΤ.5, ΣΤ.12–13).

Scans model space once and produces (a) issues per check and (b) the :class:`Drawing` of the
Table I layers for the topology checks. An entity counts as layer *content* only if it has an
allowed type and no elevation: the Cadastre reports "layer has no content" for 3D entities.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..issues import IssueSink
from .drawing import Drawing, Shape
from .dxf_load import dedupe, finite, lwpolyline_points, polyline_points, strip_closing
from .spec import (
    BY_NAME,
    BY_NO,
    COMPLETENESS,
    FORBIDDEN_TYPES,
    DiagramKind,
    is_latin_name,
    latinize,
)

#: |z| or |elevation| above this is not 2D (m)
Z_EPS = 1e-9

_GEOMETRY_TYPES = {
    "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "SOLID", "3DFACE", "TRACE", "RAY", "XLINE",
    "MLINE", "LEADER", "MULTILEADER", "DIMENSION", "3DSOLID", "REGION", "BODY", "MESH",
}  # fmt: skip


@dataclass
class Scan:
    checks: dict[str, IssueSink] = field(default_factory=lambda: defaultdict(IssueSink))
    drawing: Drawing = field(default_factory=Drawing)
    content: set[str] = field(default_factory=set)
    counts: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))


def _xy(v: Any) -> tuple[float, float]:
    return (round(float(v[0]), 3), round(float(v[1]), 3))


def scan_doc(doc: Any, kind: DiagramKind) -> Scan:
    sc = Scan()
    _layer_names(doc, sc)
    _xrefs(doc, sc)
    for e in doc.modelspace():
        layer = str(e.dxf.layer)
        t = e.dxftype()
        sc.counts[layer][t] += 1
        spec = BY_NAME.get(layer)
        if spec is None:
            _free_entity(e, t, layer, sc)
            continue
        _table_entity(e, t, layer, spec.forms, sc)
    _completeness(kind, sc)
    return sc


def _layer_names(doc: Any, sc: Scan) -> None:
    sink = sc.checks["layer_names"]
    names = {str(lay.dxf.name) for lay in doc.layers}
    names |= {str(e.dxf.layer) for e in doc.modelspace()}
    for name in sorted(names):
        if name in BY_NAME:
            continue
        fixed = latinize(name)
        if fixed in BY_NAME:
            bad = [f"{c} (U+{ord(c):04X})" for c in name if not is_latin_name(c)]
            sink.error(
                "DGM_LAYER_GREEK_LOOKALIKE",
                f"Layer {name} uses Greek/Cyrillic letters ({', '.join(bad)}); use {fixed}",
                layer=name,
                expected=fixed,
                chars=bad,
            )
        elif latinize(name.upper().strip().replace(" ", "_")) in BY_NAME:
            expected = latinize(name.upper().strip().replace(" ", "_"))
            sink.error(
                "DGM_LAYER_NAME_FORM",
                f"Layer {name} must be written {expected} (capitals, no spaces)",
                layer=name,
                expected=expected,
            )
        elif not is_latin_name(name):
            sink.error(
                "DGM_LAYER_NON_LATIN", f"Layer name {name} has non-Latin characters", layer=name
            )


def _xrefs(doc: Any, sc: Scan) -> None:
    for blk in doc.blocks:
        block = blk.block
        if block is not None and (block.is_xref or block.is_xref_overlay):
            sc.checks["forbidden"].error(
                "DGM_XREF", f"External reference {blk.name}", name=str(blk.name)
            )


def _free_entity(e: Any, t: str, layer: str, sc: Scan) -> None:
    if t in FORBIDDEN_TYPES and t not in ("MTEXT", "INSERT"):
        sc.checks["forbidden"].warning(
            "DGM_FORBIDDEN_FREE",
            f"{t} on free layer {layer}: keep it only in the PDF image",
            layer=layer,
            type=t,
            handle=e.dxf.get("handle"),
        )


def _table_entity(e: Any, t: str, layer: str, forms: frozenset[str], sc: Scan) -> None:
    handle = e.dxf.get("handle")
    if t in FORBIDDEN_TYPES:
        kind = FORBIDDEN_TYPES[t]
        x, y = _anchor(e)
        sc.checks["forbidden"].error(
            "DGM_FORBIDDEN_ENTITY",
            f"{t} ({kind}) on {layer} is not allowed",
            layer=layer,
            type=t,
            what=kind,
            handle=handle,
            x=x,
            y=y,
        )
        return
    if t in ("LWPOLYLINE", "POLYLINE"):
        _polyline(e, t, layer, forms, sc)
    elif t == "TEXT":
        ins = e.dxf.insert
        _check_z(e, layer, [float(ins.z)], sc, (float(ins.x), float(ins.y)))
        if "text" not in forms:
            sc.checks["entity_types"].error(
                "DGM_ENTITY_TYPE",
                f"TEXT is not allowed on {layer}",
                layer=layer,
                type=t,
                handle=handle,
                x=round(float(ins.x), 3),
                y=round(float(ins.y), 3),
            )
        elif finite(ins.x, ins.y):
            sc.drawing.shapes.append(
                Shape(layer, "text", ((float(ins.x), float(ins.y)),), handle, str(e.dxf.text))
            )
            if abs(float(ins.z)) <= Z_EPS:
                sc.content.add(layer)
    elif t == "POINT":
        loc = e.dxf.location
        _check_z(e, layer, [float(loc.z)], sc, (float(loc.x), float(loc.y)))
        if "point" not in forms:
            sc.checks["entity_types"].error(
                "DGM_ENTITY_TYPE",
                f"POINT is not allowed on {layer}",
                layer=layer,
                type=t,
                handle=handle,
                x=round(float(loc.x), 3),
                y=round(float(loc.y), 3),
            )
        elif finite(loc.x, loc.y):
            sc.drawing.shapes.append(Shape(layer, "point", ((float(loc.x), float(loc.y)),), handle))
            if abs(float(loc.z)) <= Z_EPS:
                sc.content.add(layer)
    else:
        x, y = _anchor(e)
        code = (
            "DGM_KAEK_STRAY_SHAPE"
            if layer == "PST_KAEK" and t in ("CIRCLE", "ELLIPSE", "SPLINE", "SOLID")
            else "DGM_ENTITY_TYPE"
        )
        sc.checks["entity_types"].error(
            code, f"{t} is not allowed on {layer}", layer=layer, type=t, handle=handle, x=x, y=y
        )


def _polyline(e: Any, t: str, layer: str, forms: frozenset[str], sc: Scan) -> None:
    handle = e.dxf.get("handle")
    types = sc.checks["entity_types"]
    if t == "LWPOLYLINE":
        pts, closed, bulges = lwpolyline_points(e)
        zs = [float(e.dxf.get("elevation", 0.0) or 0.0)]
    else:
        if e.is_polygon_mesh or e.is_poly_face_mesh:
            types.error(
                "DGM_ENTITY_TYPE",
                f"Mesh on {layer} is not allowed",
                layer=layer,
                type="MESH",
                handle=handle,
                x=None,
                y=None,
            )
            return
        pts, closed, zs = polyline_points(e)
        bulges = any(abs(float(v.dxf.get("bulge", 0.0))) > 1e-12 for v in e.vertices)
        x0, y0 = _xy(pts[0]) if pts else (None, None)
        if e.is_3d_polyline:
            types.error(
                "DGM_POLYLINE_3D", f"3D POLYLINE on {layer}", layer=layer, handle=handle, x=x0, y=y0
            )
        else:
            types.warning(
                "DGM_POLYLINE_HEAVY",
                f"POLYLINE on {layer}: Table I asks for LWPOLYLINE",
                layer=layer,
                handle=handle,
                x=x0,
                y=y0,
            )
    pts = dedupe([p for p in pts if finite(*p)])
    if len(pts) < 2:
        types.error(
            "DGM_POLYGON_DEGENERATE",
            f"Polyline {handle} on {layer} has fewer than 2 vertices",
            layer=layer,
            handle=handle,
            x=None,
            y=None,
        )
        return
    first = _xy(pts[0])
    _check_z(e, layer, zs, sc, pts[0])
    if bulges:
        types.warning(
            "DGM_ARC_SEGMENT",
            f"Polyline {handle} on {layer} has arc segments",
            layer=layer,
            handle=handle,
            x=first[0],
            y=first[1],
        )
    ring, repeated = strip_closing(pts)
    is_polygon = (closed or repeated) and len(ring) >= 3
    if is_polygon and not closed:
        types.warning(
            "DGM_POLYGON_CLOSED_BY_POINT",
            f"Polyline {handle} on {layer} closes on its first vertex but is not marked closed",
            layer=layer,
            handle=handle,
            x=first[0],
            y=first[1],
        )
    if is_polygon and "polygon" not in forms:
        types.warning(
            "DGM_ENTITY_FORM",
            f"Closed polyline on line layer {layer}",
            layer=layer,
            handle=handle,
            x=first[0],
            y=first[1],
        )
    if not is_polygon and "polyline" not in forms:
        types.error(
            "DGM_POLYGON_OPEN",
            f"Open polyline {handle} on polygon layer {layer}",
            layer=layer,
            handle=handle,
            x=first[0],
            y=first[1],
        )
        return
    form = "polygon" if is_polygon and "polygon" in forms else "polyline"
    coords = tuple(ring) if form == "polygon" else tuple(pts)
    sc.drawing.shapes.append(Shape(layer, form, coords, handle))
    if all(abs(z) <= Z_EPS for z in zs):
        sc.content.add(layer)


def _check_z(e: Any, layer: str, zs: list[float], sc: Scan, at: tuple[float, float]) -> None:
    handle = e.dxf.get("handle")
    z = max((abs(v) for v in zs if math.isfinite(v)), default=0.0)
    if z > Z_EPS:
        sc.checks["elevation"].error(
            "DGM_ELEVATION",
            f"{e.dxftype()} {handle} on {layer} has elevation {z:.3f} (must be 2D)",
            layer=layer,
            handle=handle,
            z=round(z, 3),
            x=round(at[0], 3),
            y=round(at[1], 3),
        )
    ext = _attr(e, "extrusion")
    if ext is not None and (abs(ext[0]) > 1e-12 or abs(ext[1]) > 1e-12 or ext[2] < 0):
        sc.checks["elevation"].warning(
            "DGM_EXTRUSION",
            f"{e.dxftype()} {handle} on {layer} is not in the world XY plane",
            layer=layer,
            handle=handle,
            x=round(at[0], 3),
            y=round(at[1], 3),
        )
    th = _attr(e, "thickness")
    if th is not None and abs(float(th)) > Z_EPS:
        sc.checks["elevation"].error(
            "DGM_ELEVATION",
            f"{e.dxftype()} {handle} on {layer} has thickness",
            layer=layer,
            handle=handle,
            z=round(float(th), 3),
            x=round(at[0], 3),
            y=round(at[1], 3),
        )


def _attr(e: Any, name: str) -> Any:
    return e.dxf.get(name) if e.dxf.is_supported(name) else None


def _anchor(e: Any) -> tuple[float | None, float | None]:
    for attr in ("insert", "center", "start", "location"):
        if e.dxf.is_supported(attr) and e.dxf.hasattr(attr):
            return _xy(e.dxf.get(attr))
    return (None, None)


def _completeness(kind: DiagramKind, sc: Scan) -> None:
    """Required layers and the ⇔ rules of [S1] §4.5.2 for the declared diagram kind."""
    sink = sc.checks["layers_required"]
    have = {s.no for s in BY_NAME.values() if s.name in sc.content}
    for rule in COMPLETENESS[kind]:
        if not all(n in have for n in rule.when) or any(n in have for n in rule.unless):
            continue
        if any(n in have for n in rule.need):
            continue
        need = [BY_NO[n].name for n in rule.need]
        if rule.when:
            when = [BY_NO[n].name for n in rule.when]
            sink.error(
                "DGM_LAYER_PAIR",
                f"{', '.join(when)} requires {' or '.join(need)}",
                when=when,
                layers=need,
            )
        elif len(need) == 1:
            sink.error("DGM_LAYER_REQUIRED", f"Layer {need[0]} is missing or empty", layers=need)
        else:
            sink.error(
                "DGM_LAYER_REQUIRED_ANY",
                f"At least one of {', '.join(need)} must have content",
                layers=need,
            )
    other = sc.checks["layers_kind"]
    for name in sorted(sc.content):
        spec = BY_NAME[name]
        if kind not in spec.kinds:
            other.warning(
                "DGM_LAYER_NOT_FOR_KIND",
                f"Layer {name} is not used in this kind of diagram",
                layer=name,
            )
