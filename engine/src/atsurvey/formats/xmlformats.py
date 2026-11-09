"""Trimble JobXML (.jxl) and LandXML raw observations.

Both are parsed with ``defusedxml`` because the files are user uploads.

**JobXML**: values are always SI (metres, decimal degrees) regardless of display
units. ``StationRecord``\\s define setups; ``PointRecord``\\s with a ``<Circle>`` block are
raw observations referencing their station via ``<StationID>`` and their target height
via ``<TargetID>`` → ``TargetRecord``. Deleted records are skipped. Points with a
``<Grid>`` block of method ``KeyedIn``/``Coordinates`` are returned as control points.

**LandXML**: ``Survey/InstrumentSetup`` with ``RawObservation`` children. The angular
unit is read from ``Units/Metric@angularUnit`` (``grads``, ``decimal degrees``,
``decimal dd.mm.ss``, ``radians``). ``CgPoints`` are returned as control points.
"""

from __future__ import annotations

import math
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as DET

from ..core.models import ControlPoint, Observation, Setup
from ..core.units import AngleUnit, to_rad
from .base import ParseError, ParseResult, decode


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el: Element, name: str) -> Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el: Element | None, name: str) -> str | None:
    if el is None:
        return None
    c = _find(el, name)
    if c is None or c.text is None:
        return None
    t = c.text.strip()
    return t or None


def _float(el: Element | None, name: str) -> float | None:
    t = _text(el, name)
    if t is None:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _iter(root: Element, name: str):
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


def _parse_xml(data: bytes) -> Element:
    try:
        # no DTDs at all: JobXML/LandXML never need them; blocks entity tricks outright
        return DET.fromstring(data, forbid_dtd=True)
    except Exception as exc:  # defusedxml raises several types
        raise ParseError(f"Invalid XML: {exc}") from exc


# ----------------------------------------------------------------------------- JobXML


def parse_jobxml(data: bytes) -> ParseResult:
    root = _parse_xml(data)
    if _local(root.tag) != "JOBFile":
        raise ParseError("Not a Trimble JobXML file (missing JOBFile root)")
    res = ParseResult(format="trimble_jobxml", angle_unit="deg")

    targets: dict[str, float] = {}
    for tr in _iter(root, "TargetRecord"):
        tid = tr.get("ID")
        th = _float(tr, "TargetHeight")
        if tid and th is not None:
            targets[tid] = th

    setups: dict[str, Setup] = {}
    order: list[str] = []
    for sr in _iter(root, "StationRecord"):
        if (_text(sr, "Deleted") or "false").lower() == "true":
            continue
        sid = sr.get("ID")
        name = _text(sr, "StationName")
        if not sid or not name:
            continue
        setups[sid] = Setup(
            station=name,
            instrument_height=_float(sr, "TheodoliteHeight") or 0.0,
            id=None,
        )
        order.append(sid)

    coords: dict[str, ControlPoint] = {}
    n_skipped = 0
    for pr in _iter(root, "PointRecord"):
        if (_text(pr, "Deleted") or "false").lower() == "true":
            n_skipped += 1
            continue
        name = _text(pr, "Name")
        if not name:
            continue
        circle = _find(pr, "Circle")
        if circle is not None:
            sid = _text(pr, "StationID")
            setup = setups.get(sid or "")
            if setup is None:
                res.warnings.append(f"Observation to {name} references unknown station {sid}")
                continue
            hz = _float(circle, "HorizontalCircle")
            if hz is None:
                continue
            v = _float(circle, "VerticalCircle")
            sd = _float(circle, "EDMDistance")
            tid = _text(pr, "TargetID")
            setup.observations.append(
                Observation(
                    target=name,
                    hz=to_rad(hz, "deg"),
                    v=to_rad(v, "deg") if v is not None else None,
                    sd=sd if sd else None,
                    target_height=targets.get(tid or "", 0.0),
                    code=_text(pr, "Code"),
                )
            )
            continue
        grid = _find(pr, "Grid")
        method = (_text(pr, "Method") or "").lower()
        if grid is not None and method in ("keyedin", "coordinates", "copied", ""):
            e = _float(grid, "East")
            n = _float(grid, "North")
            if e is not None and n is not None and name not in coords:
                coords[name] = ControlPoint(
                    name=name, x=e, y=n, z=_float(grid, "Elevation"), code=_text(pr, "Code")
                )
    if n_skipped:
        res.warnings.append(f"{n_skipped} deleted records were skipped")
    res.setups = [setups[s] for s in order]
    res.control_points = list(coords.values())
    return res.finalise()


# ---------------------------------------------------------------------------- LandXML

_LANDXML_UNITS: dict[str, AngleUnit] = {
    "grads": "gon",
    "gons": "gon",
    "gon": "gon",
    "decimal degrees": "deg",
    "degrees": "deg",
    "decimal dd.mm.ss": "dms",
    "radians": "rad",
}


def parse_landxml(data: bytes, angle_unit: AngleUnit | None = None) -> ParseResult:
    root = _parse_xml(data)
    if _local(root.tag) != "LandXML":
        raise ParseError("Not a LandXML file")
    unit: AngleUnit | None = angle_unit
    if unit is None:
        for m in _iter(root, "Metric"):
            u = (m.get("angularUnit") or "").strip().lower()
            if u in _LANDXML_UNITS:
                unit = _LANDXML_UNITS[u]
                break
        for m in _iter(root, "Imperial"):
            u = (m.get("angularUnit") or "").strip().lower()
            if unit is None and u in _LANDXML_UNITS:
                unit = _LANDXML_UNITS[u]
    res = ParseResult(format="landxml", angle_unit=unit or "deg")
    if unit is None:
        res.warnings.append("Angular unit not declared; decimal degrees assumed")
        unit = "deg"

    coords: dict[str, ControlPoint] = {}
    for cg in _iter(root, "CgPoint"):
        name = cg.get("name") or cg.get("oID")
        if not name or not cg.text:
            continue
        parts = cg.text.split()
        try:
            vals = [float(p) for p in parts]
        except ValueError:
            continue
        if len(vals) >= 2:
            # LandXML stores "northing easting [elevation]"
            coords.setdefault(
                name,
                ControlPoint(
                    name=name,
                    x=vals[1],
                    y=vals[0],
                    z=vals[2] if len(vals) > 2 else None,
                    code=cg.get("code"),
                ),
            )

    for ins in _iter(root, "InstrumentSetup"):
        ip = _find(ins, "InstrumentPoint")
        station = ins.get("stationName") or (ip.get("pntRef") if ip is not None else None)
        if not station:
            continue
        setup = Setup(
            station=station,
            instrument_height=float(ins.get("instrumentHeight") or 0.0),
            id=None,
        )
        for ro in ins:
            if _local(ro.tag) != "RawObservation":
                continue
            tp = _find(ro, "TargetPoint")
            target = None
            code = None
            if tp is not None:
                target = tp.get("pntRef") or tp.get("name")
                code = tp.get("code")
            target = target or ro.get("targetPoint")
            hz = ro.get("horizAngle")
            if not target or hz is None:
                continue
            v = ro.get("zenithAngle")
            sd = ro.get("slopeDistance")
            hd = ro.get("horizDistance")
            v_rad = to_rad(float(v), unit) if v is not None else None
            dist = float(sd) if sd is not None else None
            if dist is None and hd is not None:
                h = float(hd)
                dist = h / math.sin(v_rad) if v_rad else h
            setup.observations.append(
                Observation(
                    target=target,
                    hz=to_rad(float(hz), unit),
                    v=v_rad,
                    sd=dist or None,
                    target_height=float(ro.get("targetHeight") or 0.0),
                    code=code,
                )
            )
        res.setups.append(setup)
    res.control_points = list(coords.values())
    if not res.setups and not coords:
        raise ParseError("LandXML file contains no InstrumentSetup or CgPoints")
    return res.finalise()


__all__ = ["decode", "parse_jobxml", "parse_landxml"]
