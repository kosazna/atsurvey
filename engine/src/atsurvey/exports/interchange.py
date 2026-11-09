"""Interchange exports: LandXML 1.2, KML and GeoJSON.

* **LandXML** keeps ΕΓΣΑ87 grid coordinates (CgPoints "northing easting elevation") and
  writes line work and traverses as PlanFeatures, for Civil 3D, Trimble Business Center,
  Leica Infinity and others.
* **KML** and **GeoJSON** are WGS84 by specification (RFC 7946 / OGC KML). Coordinates are
  transformed with pyproj (EPSG:2100 → EPSG:4326, standard 7-parameter datum shift). The
  absolute accuracy of that shift is at the metre level, which is fine for viewing in Google
  Earth or a web map but **not** for survey work; the original ΕΓΣΑ87 coordinates are kept as
  properties of every feature.
"""

from __future__ import annotations

import itertools
import json
from functools import lru_cache
from xml.etree.ElementTree import Element, SubElement, tostring

from ..core.models import ProjectResult, ResultPoint
from . import ExportOptions, selected_points


@lru_cache
def _to_wgs84():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:2100", "EPSG:4326", always_xy=True)


def _lonlat(x: float, y: float) -> tuple[float, float]:
    lon, lat = _to_wgs84().transform(x, y)
    return round(lon, 9), round(lat, 9)


def _lines(result: ProjectResult) -> list[tuple[str, str, list[ResultPoint], bool, str]]:
    """(name, code, points, closed, kind) for traverses and line work."""
    lookup = {p.name: p for p in result.points}
    out = []
    for t in result.traverses:
        names: list[str] = []
        for leg in t.legs:
            for n in (leg.frm, leg.to):
                if not names or names[-1] != n:
                    names.append(n)
        pts = [lookup[n] for n in names if n in lookup]
        if len(pts) >= 2:
            out.append((t.name, "TRAVERSE", pts, False, "traverse"))
    for ln in result.linework:
        pts = [lookup[n] for n in ln.points if n in lookup]
        if len(pts) >= 2:
            out.append((ln.name, ln.code, pts, ln.closed, "linework"))
    return out


# ---------------------------------------------------------------------------- LandXML


def to_landxml(project_name: str, result: ProjectResult, opts: ExportOptions) -> bytes:
    d = opts.decimals
    root = Element(
        "LandXML",
        {
            "xmlns": "http://www.landxml.org/schema/LandXML-1.2",
            "version": "1.2",
            "date": "",
            "time": "",
        },
    )
    SubElement(
        root,
        "Units",
    ).append(
        Element(
            "Metric",
            {
                "linearUnit": "meter",
                "areaUnit": "squareMeter",
                "volumeUnit": "cubicMeter",
                "angularUnit": "grads",
                "directionUnit": "grads",
            },
        )
    )
    SubElement(
        root,
        "CoordinateSystem",
        {"name": "GGRS87 / Greek Grid", "epsgCode": "2100", "horizontalDatum": "GGRS87"},
    )
    SubElement(root, "Project", {"name": project_name})
    app = SubElement(root, "Application", {"name": "ATSurvey", "manufacturer": "ATSurvey"})
    app.set("version", result.engine_version)

    def nez(p: ResultPoint) -> str:
        z = f" {p.z:.{d}f}" if p.z is not None else ""
        return f"{p.y:.{d}f} {p.x:.{d}f}{z}"

    cg = SubElement(root, "CgPoints")
    for p in selected_points(result, opts):
        attrs = {"name": p.name, "desc": p.kind}
        if p.code:
            attrs["code"] = p.code
        SubElement(cg, "CgPoint", attrs).text = nez(p)

    lines = _lines(result)
    if lines:
        pf_root = SubElement(root, "PlanFeatures", {"name": "ATSurvey"})
        for name, code, pts, closed, kind in lines:
            pf = SubElement(pf_root, "PlanFeature", {"name": name, "desc": f"{kind}:{code}"})
            geom = SubElement(pf, "CoordGeom")
            seq = [*pts, pts[0]] if closed else pts
            for a, b in itertools.pairwise(seq):
                line = SubElement(geom, "Line")
                SubElement(line, "Start").text = nez(a)
                SubElement(line, "End").text = nez(b)
    body = tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


# -------------------------------------------------------------------------------- KML

_KIND_STYLE = {"control": "ctrl", "traverse": "trav", "detail": "det"}


def to_kml(project_name: str, result: ProjectResult, opts: ExportOptions) -> bytes:
    from .theme import color

    def kml_color(hex_rgb: str, alpha: str = "ff") -> str:
        h = hex_rgb.lstrip("#")
        return f"{alpha}{h[4:6]}{h[2:4]}{h[0:2]}"  # KML is aabbggrr

    root = Element("kml", {"xmlns": "http://www.opengis.net/kml/2.2"})
    doc = SubElement(root, "Document")
    SubElement(doc, "name").text = project_name
    SubElement(
        doc, "description"
    ).text = "ΕΓΣΑ87 → WGS84 (EPSG:2100 → 4326), accuracy ≈ 1 m: for viewing only."
    for kind, sid in _KIND_STYLE.items():
        st = SubElement(doc, "Style", {"id": sid})
        icon = SubElement(st, "IconStyle")
        SubElement(icon, "color").text = kml_color(color(f"point-{kind}"))
        SubElement(icon, "scale").text = "0.8" if kind == "detail" else "1.0"
        ic = SubElement(icon, "Icon")
        SubElement(
            ic, "href"
        ).text = "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"
        lbl = SubElement(st, "LabelStyle")
        SubElement(lbl, "scale").text = "0.7"
    for sid, key in (("line", "traverse-line"), ("poly", "accent")):
        st = SubElement(doc, "Style", {"id": sid})
        ls = SubElement(st, "LineStyle")
        SubElement(ls, "color").text = kml_color(color(key))
        SubElement(ls, "width").text = "2"
        ps = SubElement(st, "PolyStyle")
        SubElement(ps, "color").text = kml_color(color(key), "33")

    folder = SubElement(doc, "Folder")
    SubElement(folder, "name").text = "Points"
    for p in selected_points(result, opts):
        pm = SubElement(folder, "Placemark")
        SubElement(pm, "name").text = p.name
        SubElement(pm, "styleUrl").text = f"#{_KIND_STYLE[p.kind]}"
        ext = SubElement(pm, "ExtendedData")
        for k, v in (
            ("EGSA87_X", f"{p.x:.3f}"),
            ("EGSA87_Y", f"{p.y:.3f}"),
            ("Z", "" if p.z is None else f"{p.z:.3f}"),
            ("code", p.code or ""),
            ("kind", p.kind),
        ):
            data = SubElement(ext, "Data", {"name": k})
            SubElement(data, "value").text = v
        pt = SubElement(pm, "Point")
        lon, lat = _lonlat(p.x, p.y)
        SubElement(pt, "coordinates").text = f"{lon},{lat},0"

    lines = _lines(result)
    if lines:
        lf = SubElement(doc, "Folder")
        SubElement(lf, "name").text = "Lines"
        for name, _code, pts, closed, _kind in lines:
            pm = SubElement(lf, "Placemark")
            SubElement(pm, "name").text = name
            coords = [_lonlat(p.x, p.y) for p in pts]
            if closed and len(coords) >= 3:
                SubElement(pm, "styleUrl").text = "#poly"
                ring = [*coords, coords[0]]
                poly = SubElement(pm, "Polygon")
                outer = SubElement(SubElement(poly, "outerBoundaryIs"), "LinearRing")
                SubElement(outer, "coordinates").text = " ".join(f"{a},{b},0" for a, b in ring)
            else:
                SubElement(pm, "styleUrl").text = "#line"
                ls = SubElement(pm, "LineString")
                SubElement(ls, "coordinates").text = " ".join(f"{a},{b},0" for a, b in coords)
    body = tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


# ---------------------------------------------------------------------------- GeoJSON


def to_geojson(project_name: str, result: ProjectResult, opts: ExportOptions) -> bytes:
    features = []
    for p in selected_points(result, opts):
        lon, lat = _lonlat(p.x, p.y)
        props = {
            "name": p.name,
            "kind": p.kind,
            "code": p.code,
            "egsa87_x": p.x,
            "egsa87_y": p.y,
            "z": p.z,
            "source": p.source,
        }
        if p.sx is not None:
            props.update({"sx": p.sx, "sy": p.sy, "sz": p.sz})
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )
    for name, code, pts, closed, kind in _lines(result):
        coords = [list(_lonlat(p.x, p.y)) for p in pts]
        if closed and len(coords) >= 3:
            geom = {"type": "Polygon", "coordinates": [[*coords, coords[0]]]}
        else:
            geom = {"type": "LineString", "coordinates": coords}
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {"name": name, "code": code, "kind": kind},
            }
        )
    fc = {
        "type": "FeatureCollection",
        "name": project_name,
        "metadata": {
            "source_crs": "EPSG:2100",
            "note": "WGS84 via EPSG:2100→4326 (≈1 m): for viewing; survey values in properties",
            "engine_version": result.engine_version,
            "input_hash": result.input_hash,
        },
        "features": features,
    }
    return json.dumps(fc, ensure_ascii=False, indent=1).encode("utf-8")
