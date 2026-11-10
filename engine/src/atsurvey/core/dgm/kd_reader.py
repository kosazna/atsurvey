"""Read the cadastral parcels (PST_KAEK) from a Κτηματογραφικό Διάγραμμα DXF.

The vector file of the ΚΔ is downloaded from the Cadastre (e-services/11) with the code printed
on the diagram. We have no real sample yet, so the reader is tolerant:

* every closed LWPOLYLINE / POLYLINE (or one whose ends coincide) on any layer — or only on
  ``layer`` if given — is a candidate parcel;
* every TEXT / MTEXT whose content is a KAEK (12 digits, optionally with a «ΚΑΕΚ» prefix,
  spaces, dots or dashes) is assigned to the **smallest** candidate containing its insertion
  point (so a sheet frame or a block outline does not capture it);
* polygons without a KAEK and KAEK texts outside every polygon are reported (warnings), and
  polygons without KAEK are dropped unless the file has no KAEK texts at all;
* vertices shared by two parcels get one name (numbered 1, 2, … in reading order).

Greek text is decoded by ezdxf from $DWGCODEPAGE (cp1253 for ANSI_1253) or UTF-8 (DXF ≥ 2007).
**To validate with a real ΚΔ DXF** (layer names, text placement, encoding) — see docs/dgm.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import Point, Polygon

from ..issues import IssueSink
from ..parcels import signed_area
from ..parcels_models import ParcelVertex
from .dxf_load import (
    MAX_ENTITIES,
    DxfLoadError,
    dedupe,
    finite,
    load_dxf,
    lwpolyline_points,
    polyline_points,
    strip_closing,
)
from .geom import PointRegistry
from .models import KdParcel, KdReadResult
from .spec import kaek_status, normalize_kaek

MAX_PARCELS = 5000
#: Rough ΕΓΣΑ87 extent of Greece (E, N), m
EGSA_E = (50_000.0, 1_050_000.0)
EGSA_N = (3_800_000.0, 4_650_000.0)


@dataclass
class _Cand:
    layer: str
    handle: str | None
    pts: list[tuple[float, float]]
    poly: Polygon
    texts: list[str]


def read_kd(data: bytes, layer: str | None = None) -> KdReadResult:
    sink = IssueSink()
    try:
        loaded = load_dxf(data)
    except DxfLoadError as exc:
        sink.error("DGM_DXF_UNREADABLE", str(exc), reason=str(exc))
        return KdReadResult(parcels=[], issues=sink.items)
    msp = loaded.doc.modelspace()
    if len(msp) > MAX_ENTITIES:
        sink.error(
            "DGM_TOO_MANY_ENTITIES", f"More than {MAX_ENTITIES} entities", limit=MAX_ENTITIES
        )
        return KdReadResult(parcels=[], issues=sink.items)
    cands: list[_Cand] = []
    texts: list[tuple[str, float, float, str | None]] = []
    for e in msp:
        lay = str(e.dxf.layer)
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            _text(e, t, texts)
            continue
        if layer is not None and lay != layer:
            continue
        c = _candidate(e, t, lay)
        if c is not None:
            cands.append(c)
    if len(cands) > MAX_PARCELS:
        sink.error("DGM_TOO_MANY_ENTITIES", f"More than {MAX_PARCELS} polygons", limit=MAX_PARCELS)
        return KdReadResult(parcels=[], issues=sink.items)
    _assign(cands, texts, sink)
    return KdReadResult(parcels=_parcels(cands, bool(texts), sink), issues=sink.items)


def _text(e: Any, t: str, out: list) -> None:
    raw = e.dxf.text if t == "TEXT" else e.plain_text()
    kaek = normalize_kaek(str(raw))
    if kaek_status(kaek) == "invalid":
        return
    ins = e.dxf.insert
    if finite(ins.x, ins.y):
        out.append((kaek, float(ins.x), float(ins.y), e.dxf.get("handle")))


def _candidate(e: Any, t: str, layer: str) -> _Cand | None:
    if t == "LWPOLYLINE":
        pts, closed, _ = lwpolyline_points(e)
    elif t == "POLYLINE" and not (e.is_polygon_mesh or e.is_poly_face_mesh):
        pts, closed, _ = polyline_points(e)
    else:
        return None
    pts, repeated = strip_closing(dedupe(pts))
    if not (closed or repeated) or len(pts) < 3 or not all(finite(x, y) for x, y in pts):
        return None
    poly = Polygon(pts)
    if not poly.is_valid or poly.area <= 1e-6:
        return None
    return _Cand(layer, e.dxf.get("handle"), pts, poly, [])


def _assign(cands: list[_Cand], texts: list, sink: IssueSink) -> None:
    for kaek, x, y, _handle in texts:
        pt = Point(x, y)
        inside = [c for c in cands if c.poly.contains(pt)]
        if not inside:
            sink.warning(
                "DGM_KD_TEXT_UNASSIGNED",
                f"KAEK {kaek} is not inside any polygon",
                kaek=kaek,
                x=round(x, 3),
                y=round(y, 3),
            )
            continue
        min(inside, key=lambda c: c.poly.area).texts.append(kaek)


def _parcels(cands: list[_Cand], have_texts: bool, sink: IssueSink) -> list[KdParcel]:
    reg = PointRegistry(new_prefix="", tol=1e-6)
    out: list[KdParcel] = []
    seen: dict[str, int] = {}
    dropped = 0
    for c in cands:
        if not c.texts and have_texts:
            dropped += 1
            continue
        kaek = c.texts[0] if c.texts else None
        if len(set(c.texts)) > 1:
            sink.warning(
                "DGM_KD_MULTIPLE_KAEK",
                f"Polygon {c.handle} contains {len(c.texts)} KAEK; kept {kaek}",
                handle=c.handle,
                kaeks=sorted(set(c.texts)),
            )
        if kaek is not None and kaek in seen:
            sink.warning("DGM_KD_DUPLICATE_KAEK", f"KAEK {kaek} labels two polygons", kaek=kaek)
        if kaek is not None:
            seen[kaek] = len(out)
        pts = c.pts if signed_area(c.pts) < 0 else c.pts[::-1]  # clockwise
        verts = [reg.add(x, y) for x, y in pts]
        out.append(
            KdParcel(
                kaek=kaek,
                layer=c.layer,
                handle=c.handle,
                vertices=[ParcelVertex(name=p.name, x=p.x, y=p.y) for p in verts],
                area=abs(signed_area(pts)),
            )
        )
    if dropped:
        sink.info(
            "DGM_KD_POLYGONS_SKIPPED",
            f"{dropped} closed polygons without KAEK skipped (frames, buildings, …)",
            count=dropped,
        )
    if not have_texts and out:
        sink.warning("DGM_KD_NO_KAEK", "No KAEK texts found: enter the KAEK of each parcel")
    if not out:
        sink.error("DGM_KD_EMPTY", "No closed polygons found in the DXF")
    outside = [
        p
        for p in out
        for v in p.vertices
        if not (EGSA_E[0] <= v.x <= EGSA_E[1] and EGSA_N[0] <= v.y <= EGSA_N[1])
    ]
    if outside:
        sink.warning("DGM_KD_NOT_EGSA", "Coordinates outside the ΕΓΣΑ87 range of Greece")
    return out
