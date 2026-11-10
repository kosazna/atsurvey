"""DXF and CSV files for the surface tools.

DXF (AutoCAD R2013, metres):

* contours: ``LWPOLYLINE`` with the contour height as ``elevation`` on layers ``ISOYPSES``
  (intermediate) and ``ISOYPSES_KYRIES`` (index), height labels on ``ISOYPSES_KEIMENO``
  aligned with the line; optional TIN as ``3DFACE`` on ``TIN`` and the surface points on
  ``TIN_SHMEIA``;
* heights: 3D ``POINT`` + label (name and height) on ``YPSOMETRA``;
* profile: a drawing in its own coordinate system (x = chainage, y = (z − datum) × vertical
  exaggeration) with the ground line, datum, station ticks and a band with heights and
  chainages; cross-sections are laid out below it.

CSV: UTF-8 with BOM, numbers rounded to ``decimals``, text guarded against formula injection.
"""

from __future__ import annotations

import csv
import io
import itertools
import math
from collections.abc import Iterable

import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts.layout import Modelspace

from ...exports import slug
from ...exports.sanitize import safe_text
from . import contour_lines, heights, profile, volume_level, volume_surfaces
from .models import (
    ContoursResult,
    HeightsResult,
    ProfileResult,
    ProfileStation,
    SurfaceExportRequest,
    VolumeResult,
)
from .tin import Tin, build_surface

DXF_MEDIA = "application/dxf"
CSV_MEDIA = "text/csv; charset=utf-8"
LAYERS = {
    "ISOYPSES": 8,
    "ISOYPSES_KYRIES": 1,
    "ISOYPSES_KEIMENO": 7,
    "TIN": 9,
    "TIN_SHMEIA": 3,
    "YPSOMETRA": 5,
    "MHKOTOMH_EDAFOS": 1,
    "MHKOTOMH_PLAISIO": 8,
    "MHKOTOMH_KEIMENO": 7,
    "DIATOMES_EDAFOS": 3,
}


def export_surface(req: SurfaceExportRequest) -> tuple[bytes, str, str]:
    """Returns (content, filename, media type)."""
    base = slug(req.project_name)
    content = req.content
    if content == "contours":
        if req.contours is None:
            raise ValueError("Contour parameters are missing")
        tin = build_surface(req.contours.surface)
        res = contour_lines(req.contours, tin)
        if req.format == "dxf":
            return _contours_dxf(req, res, tin), f"{base}_isoypses.dxf", DXF_MEDIA
        return _contours_csv(req, res), f"{base}_isoypses.csv", CSV_MEDIA
    if content == "heights":
        if req.heights is None:
            raise ValueError("Height points are missing")
        hres = heights(req.heights)
        if req.format == "dxf":
            return _heights_dxf(req, hres), f"{base}_ypsometra.dxf", DXF_MEDIA
        return _heights_csv(req, hres), f"{base}_ypsometra.csv", CSV_MEDIA
    if content == "volume":
        if req.format == "dxf":
            raise ValueError("Volumes are exported as CSV")
        if req.volume_level is not None:
            vres = volume_level(req.volume_level)
        elif req.volume_surfaces is not None:
            vres = volume_surfaces(req.volume_surfaces)
        else:
            raise ValueError("Volume parameters are missing")
        return _volume_csv(req, vres), f"{base}_ogkoi.csv", CSV_MEDIA
    if req.profile is None:
        raise ValueError("Profile parameters are missing")
    pres = profile(req.profile)
    if req.format == "dxf":
        return _profile_dxf(req, pres), f"{base}_mhkotomh.dxf", DXF_MEDIA
    return _profile_csv(req, pres), f"{base}_mhkotomh.csv", CSV_MEDIA


# ------------------------------------------------------------------------------- helpers


def _new_doc() -> ezdxf.document.Drawing:  # pyright: ignore[reportAttributeAccessIssue]
    doc = ezdxf.new("R2013", setup=True)  # pyright: ignore[reportPrivateImportUsage]
    doc.header["$INSUNITS"] = 6
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    doc.styles.add("ATS", font="IBMPlexSans-Regular.ttf")
    return doc


def _bytes(doc: ezdxf.document.Drawing) -> bytes:  # pyright: ignore[reportAttributeAccessIssue]
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _text(
    msp: Modelspace,
    text: str,
    at: tuple[float, float],
    height: float,
    layer: str,
    rotation: float = 0.0,
    align: TextEntityAlignment = TextEntityAlignment.MIDDLE_CENTER,
) -> None:
    msp.add_text(
        text, height=height, rotation=rotation, dxfattribs={"layer": layer, "style": "ATS"}
    ).set_placement(at, align=align)


def _decimals_of(*values: float) -> int:
    for d in range(4):
        if all(abs(round(v, d) - v) < 1e-9 for v in values):
            return d
    return 3


def _csv(rows: Iterable[list[str]], delimiter: str) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _f(v: float | None, d: int) -> str:
    return "" if v is None else f"{v:.{d}f}"


# ------------------------------------------------------------------------------ contours


def _label_position(pts: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Point at half the length of a polyline, the readable text angle (deg) and length."""
    seg = [math.dist(a, b) for a, b in itertools.pairwise(pts)]
    total = math.fsum(seg)
    half = total / 2
    acc = 0.0
    for (a, b), s in zip(itertools.pairwise(pts), seg, strict=True):
        if acc + s >= half and s > 0:
            t = (half - acc) / s
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            if ang > 90:
                ang -= 180
            elif ang <= -90:
                ang += 180
            return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), ang, total
        acc += s
    return pts[0][0], pts[0][1], 0.0, total


def _contours_dxf(req: SurfaceExportRequest, res: ContoursResult, tin: Tin) -> bytes:
    assert req.contours is not None
    doc = _new_doc()
    msp = doc.modelspace()
    th = req.text_height
    d = _decimals_of(req.contours.interval, req.contours.base)
    any_index = any(line.index for line in res.lines)
    for line in res.lines:
        layer = "ISOYPSES_KYRIES" if line.index else "ISOYPSES"
        msp.add_lwpolyline(
            line.points, close=line.closed, dxfattribs={"layer": layer, "elevation": line.z}
        )
        if line.index or not any_index:
            x, y, ang, length = _label_position(line.points)
            if length >= 8 * th:
                _text(msp, f"{line.z:.{d}f}", (x, y), th, "ISOYPSES_KEIMENO", ang)
    if req.include_tin or req.include_points:
        ox, oy = tin.origin
        if req.include_tin:
            for a, b, c in tin.tri.tolist():
                pts = [
                    (float(tin.xy[i, 0] + ox), float(tin.xy[i, 1] + oy), float(tin.z[i]))
                    for i in (a, b, c)
                ]
                msp.add_3dface([pts[0], pts[1], pts[2], pts[2]], dxfattribs={"layer": "TIN"})
        if req.include_points:
            for p in req.contours.surface.points:
                if p.z is not None:
                    msp.add_point((p.x, p.y, p.z), dxfattribs={"layer": "TIN_SHMEIA"})
    _fit_view(
        doc, [pt for line in res.lines for pt in line.points[:: max(1, len(line.points) // 8)]]
    )
    return _bytes(doc)


def _contours_csv(req: SurfaceExportRequest, res: ContoursResult) -> bytes:
    d = req.decimals
    rows = [["line", "z", "index", "closed", "vertex", "x", "y"]]
    for i, line in enumerate(res.lines, start=1):
        for j, (x, y) in enumerate(line.points, start=1):
            rows.append(
                [
                    str(i),
                    _f(line.z, d),
                    str(int(line.index)),
                    str(int(line.closed)),
                    str(j),
                    _f(x, d),
                    _f(y, d),
                ]
            )
    return _csv(rows, req.csv_delimiter)


# ------------------------------------------------------------------------------- heights


def _heights_dxf(req: SurfaceExportRequest, res: HeightsResult) -> bytes:
    doc = _new_doc()
    msp = doc.modelspace()
    th = req.text_height
    d = min(req.decimals, 3)
    for r in res.rows:
        if r.z is None:
            continue
        msp.add_point((r.x, r.y, r.z), dxfattribs={"layer": "YPSOMETRA"})
        label = f"{safe_text(r.name)} {r.z:.{d}f}".strip()
        _text(
            msp,
            label,
            (r.x + th * 0.5, r.y + th * 0.3),
            th,
            "YPSOMETRA",
            0.0,
            TextEntityAlignment.BOTTOM_LEFT,
        )
    _fit_view(doc, [(r.x, r.y) for r in res.rows])
    return _bytes(doc)


def _heights_csv(req: SurfaceExportRequest, res: HeightsResult) -> bytes:
    d = req.decimals
    rows = [["name", "x", "y", "z", "inside"]]
    rows += [
        [safe_text(r.name), _f(r.x, d), _f(r.y, d), _f(r.z, d), str(int(r.inside))]
        for r in res.rows
    ]
    return _csv(rows, req.csv_delimiter)


# ------------------------------------------------------------------------------- volumes


def _volume_csv(req: SurfaceExportRequest, res: VolumeResult) -> bytes:
    d = req.decimals
    rows = [
        ["quantity", "value", "unit"],
        ["reference", res.reference, ""],
        ["level", _f(res.level, d), "m"],
        ["cut", _f(res.cut, d), "m3"],
        ["fill", _f(res.fill, d), "m3"],
        ["net", _f(res.net, d), "m3"],
        ["cut_area", _f(res.cut_area, d), "m2"],
        ["fill_area", _f(res.fill_area, d), "m2"],
        ["area", _f(res.area, d), "m2"],
        ["method", res.method, ""],
    ]
    return _csv(rows, req.csv_delimiter)


# ------------------------------------------------------------------------------- profile


def _runs(stations: list[ProfileStation]) -> list[list[ProfileStation]]:
    out: list[list[ProfileStation]] = []
    for s in stations:
        if not out or out[-1][-1].run != s.run:
            out.append([])
        out[-1].append(s)
    return out


def _draw_profile(
    msp: Modelspace,
    stations: list[ProfileStation],
    x0: float,
    x1: float,
    origin: tuple[float, float],
    ve: float,
    th: float,
    title: str,
    layer_ground: str,
) -> float:
    """Draw one profile; returns the height used (drawing units)."""
    ox, oy = origin
    zs = [s.z for s in stations]
    datum = math.floor(min(zs) - 1.0) if zs else 0.0
    top = (max(zs) - datum) * ve if zs else 1.0

    def p(ch: float, z: float) -> tuple[float, float]:
        return ox + (ch - x0), oy + (z - datum) * ve

    for run in _runs(stations):
        if len(run) >= 2:
            msp.add_lwpolyline(
                [p(s.chainage, s.z) for s in run], dxfattribs={"layer": layer_ground}
            )
    frame = "MHKOTOMH_PLAISIO"
    text = "MHKOTOMH_KEIMENO"
    msp.add_line((ox, oy), (ox + x1 - x0, oy), dxfattribs={"layer": frame})
    band = 7 * th
    msp.add_line((ox, oy - band), (ox + x1 - x0, oy - band), dxfattribs={"layer": frame})
    msp.add_line((ox, oy - 2 * band), (ox + x1 - x0, oy - 2 * band), dxfattribs={"layer": frame})
    _text(
        msp,
        f"{title}  ({datum:.2f} m)",
        (ox, oy + top + 2 * th),
        th * 1.2,
        text,
        0.0,
        TextEntityAlignment.BOTTOM_LEFT,
    )
    _text(
        msp,
        "Υψόμετρο",
        (ox - th, oy - band / 2),
        th * 0.8,
        text,
        0.0,
        TextEntityAlignment.MIDDLE_RIGHT,
    )
    _text(
        msp,
        "Χ.Θ.",
        (ox - th, oy - 1.5 * band),
        th * 0.8,
        text,
        0.0,
        TextEntityAlignment.MIDDLE_RIGHT,
    )
    last = -math.inf
    for s in stations:
        x, y = p(s.chainage, s.z)
        msp.add_line((x, oy), (x, y), dxfattribs={"layer": frame})
        if x - last < 1.6 * th:
            continue
        last = x
        _text(msp, f"{s.z:.2f}", (x, oy - band / 2), th * 0.8, text, 90.0)
        _text(msp, f"{s.chainage:.2f}", (x, oy - 1.5 * band), th * 0.8, text, 90.0)
    return top + 2 * band + 4 * th


def _profile_dxf(req: SurfaceExportRequest, res: ProfileResult) -> bytes:
    doc = _new_doc()
    msp = doc.modelspace()
    th = req.text_height
    ve = req.vertical_exaggeration
    used = _draw_profile(
        msp, res.stations, 0.0, res.length, (0.0, 0.0), ve, th,
        f"ΜΗΚΟΤΟΜΗ  1:{ve:g} υψομ.", "MHKOTOMH_EDAFOS",
    )  # fmt: skip
    if res.sections:
        assert req.profile is not None
        hw = req.profile.half_width
        cols = 4
        col_w = 2 * hw + 12 * th
        row_y = -used - 10 * th
        row_h = 0.0
        for i, cs in enumerate(res.sections):
            if i and i % cols == 0:
                row_y -= row_h + 14 * th
                row_h = 0.0
            ox = (i % cols) * col_w
            if not cs.stations:
                continue
            h = _draw_profile(
                msp, cs.stations, -hw, hw, (ox, row_y), ve, th,
                f"ΔΙΑΤΟΜΗ Χ.Θ. {cs.chainage:.2f}", "DIATOMES_EDAFOS",
            )  # fmt: skip
            row_h = max(row_h, h)
    return _bytes(doc)


def _profile_csv(req: SurfaceExportRequest, res: ProfileResult) -> bytes:
    d = req.decimals
    rows = [["type", "section_chainage", "chainage_or_offset", "x", "y", "z", "run"]]
    for s in res.stations:
        rows.append(
            ["profile", "", _f(s.chainage, d), _f(s.x, d), _f(s.y, d), _f(s.z, d), str(s.run)]
        )
    for cs in res.sections:
        for s in cs.stations:
            rows.append(
                [
                    "section",
                    _f(cs.chainage, d),
                    _f(s.chainage, d),
                    _f(s.x, d),
                    _f(s.y, d),
                    _f(s.z, d),
                    str(s.run),
                ]
            )
    return _csv(rows, req.csv_delimiter)


def _fit_view(doc: ezdxf.document.Drawing, pts: list[tuple[float, float]]) -> None:  # pyright: ignore[reportAttributeAccessIssue]
    if not pts:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    doc.set_modelspace_vport(
        height=max(y1 - y0, x1 - x0, 10) * 1.2, center=((x0 + x1) / 2, (y0 + y1) / 2)
    )
