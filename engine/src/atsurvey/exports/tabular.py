"""CSV and Excel exports."""

from __future__ import annotations

import csv
import io

import xlsxwriter

from ..core.messages import localize
from ..core.models import ProjectInput, ProjectResult
from ..core.units import from_rad, rad_to_cc
from . import ExportOptions, selected_points
from .labels import KIND_LABELS, L


def _fmt(v: float | None, d: int) -> str:
    return "" if v is None else f"{v:.{d}f}"


def to_csv(result: ProjectResult, opts: ExportOptions) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=opts.csv_delimiter, lineterminator="\r\n")
    if opts.csv_header:
        w.writerow(["name", "x", "y", "z", "code", "kind"])
    d = opts.decimals
    for p in selected_points(result, opts):
        w.writerow([p.name, _fmt(p.x, d), _fmt(p.y, d), _fmt(p.z, d), p.code or "", p.kind])
    # BOM so Excel opens UTF-8 (Greek point names/codes) correctly
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(
    project_name: str, inp: ProjectInput, result: ProjectResult, opts: ExportOptions
) -> bytes:
    lang = opts.language
    t = L[lang]
    unit = opts.angle_unit
    d = opts.decimals
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    wb.set_properties({"title": project_name, "author": "ATSurvey"})
    h = wb.add_format({"bold": True, "bg_color": "#EEF2F7", "border": 1, "border_color": "#CBD5E1"})
    title = wb.add_format({"bold": True, "font_size": 14})
    num = wb.add_format({"num_format": "0." + "0" * d if d else "0"})
    ang = wb.add_format({"num_format": "0.0000" if unit in ("gon", "deg") else "0.000000"})
    cc = wb.add_format({"num_format": "+0.0;-0.0;0.0"})
    mm = wb.add_format({"num_format": "+0.000;-0.000;0.000"})
    red = wb.add_format({"font_color": "#B91C1C", "bold": True})
    green = wb.add_format({"font_color": "#15803D", "bold": True})

    # Points
    ws = wb.add_worksheet(t["points"])
    ws.write_row(0, 0, [t["name"], "X", "Y", "Z", t["code"], t["kind"], t["source"]], h)
    for i, p in enumerate(selected_points(result, opts), 1):
        ws.write_string(i, 0, p.name)
        ws.write_number(i, 1, round(p.x, d), num)
        ws.write_number(i, 2, round(p.y, d), num)
        if p.z is not None:
            ws.write_number(i, 3, round(p.z, d), num)
        ws.write_string(i, 4, p.code or "")
        ws.write_string(i, 5, KIND_LABELS[lang][p.kind])
        ws.write_string(i, 6, p.source or "")
    ws.set_column(0, 0, 12)
    ws.set_column(1, 3, 14)
    ws.set_column(4, 6, 16)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(1, len(result.points)), 6)

    # Traverse summary
    ws = wb.add_worksheet(t["traverses"])
    ws.write_row(
        0,
        0,
        [
            t["traverse"],
            t["kind_t"],
            t["n_angles"],
            t["length"],
            "wβ (cc)",
            t["tol"] + " (cc)",
            "wx",
            "wy",
            "w",
            t["tol"] + " (m)",
            "1:N",
            "wz",
            t["status"],
        ],
        h,
    )
    for i, tr in enumerate(result.traverses, 1):
        ws.write_string(i, 0, tr.name)
        ws.write_string(i, 1, t[f"kind_{tr.kind}"])
        ws.write_number(i, 2, tr.n_angles)
        ws.write_number(i, 3, round(tr.length, 3), num)
        if tr.angular_misclosure is not None:
            ws.write_number(i, 4, rad_to_cc(tr.angular_misclosure), cc)
            ws.write_number(i, 5, rad_to_cc(tr.angular_tolerance or 0), cc)
        for c, v in ((6, tr.wx), (7, tr.wy), (8, tr.linear_misclosure), (9, tr.linear_tolerance)):
            if v is not None:
                ws.write_number(i, c, v, mm)
        if tr.relative_precision:
            ws.write_number(i, 10, round(tr.relative_precision))
        if tr.wz is not None:
            ws.write_number(i, 11, tr.wz, mm)
        ok = tr.within_tolerance
        label = t["ok"] if ok else (t["exceeded"] if ok is False else t[f"status_{tr.status}"])
        ws.write_string(i, 12, label, green if ok else red if ok is False else None)
    ws.set_column(0, 0, 28)
    ws.set_column(1, 12, 11)

    # One sheet per traverse (computation sheet)
    for k, tr in enumerate(result.traverses, 1):
        ws = wb.add_worksheet(f"{t['traverse_short']} {k}"[:31])
        ws.write(0, 0, tr.name, title)
        ws.write_row(
            2,
            0,
            [
                t["station"],
                t["bs"],
                t["fs"],
                f"β ({unit})",
                "δβ (cc)",
                f"β' ({unit})",
                f"α ({unit})",
                "X",
                "Y",
                "Z",
            ],
            h,
        )
        for i, s in enumerate(tr.stations, 3):
            ws.write_row(i, 0, [s.station, s.backsight, s.foresight])
            ws.write_number(i, 3, from_rad(s.angle_measured, unit), ang)
            ws.write_number(i, 4, rad_to_cc(s.angle_correction), cc)
            ws.write_number(i, 5, from_rad(s.angle_corrected, unit), ang)
            ws.write_number(i, 6, from_rad(s.azimuth, unit), ang)
            ws.write_number(i, 7, round(s.x, d), num)
            ws.write_number(i, 8, round(s.y, d), num)
            if s.z is not None:
                ws.write_number(i, 9, round(s.z, d), num)
        r0 = len(tr.stations) + 5
        ws.write_row(
            r0,
            0,
            [
                t["from"],
                t["to"],
                "S0",
                "n",
                "k",
                "R/(R+H)",
                "S",
                f"α ({unit})",
                "ΔX",
                "ΔY",
                "δX",
                "δY",
                "ΔH",
                "δH",
            ],
            h,
        )
        for i, leg in enumerate(tr.legs, r0 + 1):
            ws.write_row(i, 0, [leg.frm, leg.to])
            ws.write_number(i, 2, leg.hd_measured, mm)
            ws.write_number(i, 3, leg.n_measurements)
            ws.write_number(i, 4, leg.reduction_scale, wb.add_format({"num_format": "0.0000000"}))
            ws.write_number(i, 5, leg.elevation_factor, wb.add_format({"num_format": "0.0000000"}))
            ws.write_number(i, 6, leg.distance_grid, mm)
            ws.write_number(i, 7, from_rad(leg.azimuth, unit), ang)
            ws.write_number(i, 8, leg.dx, mm)
            ws.write_number(i, 9, leg.dy, mm)
            ws.write_number(i, 10, leg.corr_x, mm)
            ws.write_number(i, 11, leg.corr_y, mm)
            if leg.dh is not None:
                ws.write_number(i, 12, leg.dh, mm)
            ws.write_number(i, 13, leg.corr_h, mm)
        ws.set_column(0, 2, 10)
        ws.set_column(3, 13, 13)

    # Detail shots
    ws = wb.add_worksheet(t["detail"])
    ws.write_row(
        0,
        0,
        [
            t["station"],
            t["point"],
            f"Hz ({unit})",
            f"V ({unit})",
            "SD",
            "S",
            f"α ({unit})",
            "X",
            "Y",
            "Z",
            t["code"],
            t["check"],
        ],
        h,
    )
    for i, s in enumerate(result.detail, 1):
        ws.write_row(i, 0, [s.station, s.target])
        ws.write_number(i, 2, from_rad(s.direction, unit), ang)
        if s.zenith is not None:
            ws.write_number(i, 3, from_rad(s.zenith, unit), ang)
        if s.sd is not None:
            ws.write_number(i, 4, s.sd, mm)
        if s.distance_grid is not None:
            ws.write_number(i, 5, s.distance_grid, mm)
        ws.write_number(i, 6, from_rad(s.azimuth, unit), ang)
        for c, v in ((7, s.x), (8, s.y), (9, s.z)):
            if v is not None:
                ws.write_number(i, c, round(v, d), num)
        ws.write_string(i, 10, s.code or "")
        if s.check:
            ws.write_string(i, 11, f"{(s.residual or 0) * 1000:.1f} mm")
    ws.set_column(0, 11, 12)

    # Issues
    ws = wb.add_worksheet(t["issues"])
    ws.write_row(0, 0, [t["severity"], t["code"], t["message"]], h)
    for i, iss in enumerate(result.issues, 1):
        ws.write_row(i, 0, [iss.severity, iss.code, localize(iss, lang)])
    ws.set_column(0, 1, 26)
    ws.set_column(2, 2, 100)

    wb.close()
    return buf.getvalue()
