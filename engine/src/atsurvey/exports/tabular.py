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
from .sanitize import safe_text
from .theme import color, load_theme


def _fmt(v: float | None, d: int) -> str:
    return "" if v is None else f"{v:.{d}f}"


def to_csv(result: ProjectResult, opts: ExportOptions) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=opts.csv_delimiter, lineterminator="\r\n")
    if opts.csv_header:
        w.writerow(["name", "x", "y", "z", "code", "kind"])
    d = opts.decimals
    for p in selected_points(result, opts):
        w.writerow(
            [safe_text(p.name), _fmt(p.x, d), _fmt(p.y, d), _fmt(p.z, d), safe_text(p.code), p.kind]
        )
    # BOM so Excel opens UTF-8 (Greek point names/codes) correctly
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def to_xlsx(
    project_name: str, inp: ProjectInput, result: ProjectResult, opts: ExportOptions
) -> bytes:
    lang = opts.language
    t = L[lang]
    unit = opts.angle_unit
    d = opts.decimals
    buf = io.BytesIO()
    font = load_theme()["font"]
    wb = xlsxwriter.Workbook(
        buf,
        {
            "in_memory": True,
            # user text is never a formula or a hyperlink (formula / DDE injection)
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "default_format_properties": {
                "font_name": font,
                "font_size": 10,
                "font_color": color("text"),
            },
        },
    )
    wb.set_properties({"title": project_name, "author": "ATSurvey"})
    hair = color("border")
    h = wb.add_format(
        {
            "bold": True,
            "font_color": color("text-muted"),
            "bg_color": color("surface-sunken"),
            "bottom": 1,
            "bottom_color": color("border-strong"),
            "valign": "vcenter",
        }
    )
    h_num = wb.add_format(
        {
            "bold": True,
            "font_color": color("text-muted"),
            "bg_color": color("surface-sunken"),
            "bottom": 1,
            "bottom_color": color("border-strong"),
            "valign": "vcenter",
            "align": "right",
        }
    )

    def head(ws, row: int, labels: list[str], text_cols: tuple[int, ...]) -> None:
        for col, label in enumerate(labels):
            ws.write_string(row, col, label, h if col in text_cols else h_num)

    title = wb.add_format({"bold": True, "font_size": 14})
    num = wb.add_format({"num_format": "0." + "0" * d if d else "0"})
    ang = wb.add_format({"num_format": "0.0000" if unit in ("gon", "deg") else "0.000000"})
    cc = wb.add_format({"num_format": "+0.0;-0.0;0.0"})
    mm = wb.add_format({"num_format": "+0.000;-0.000;0.000"})
    scale = wb.add_format({"num_format": "0.0000000"})
    red = wb.add_format({"font_color": color("danger"), "bold": True})
    green = wb.add_format({"font_color": color("success"), "bold": True})
    muted = wb.add_format({"font_color": color("text-muted")})

    def finish(ws, rows: int, cols: int) -> None:
        """Hairline row separators, hidden gridlines, frozen header."""
        ws.hide_gridlines(2)
        ws.freeze_panes(1, 0)
        ws.set_row(0, 22)
        if rows > 0:
            ws.conditional_format(
                1,
                0,
                rows,
                cols - 1,
                {"type": "no_errors", "format": wb.add_format({"bottom": 1, "bottom_color": hair})},
            )

    # Points
    ws = wb.add_worksheet(t["points"])
    head(ws, 0, [t["name"], "X", "Y", "Z", t["code"], t["kind"], t["source"]], (0, 4, 5, 6))
    for i, p in enumerate(selected_points(result, opts), 1):
        ws.write_string(i, 0, p.name)
        ws.write_number(i, 1, round(p.x, d), num)
        ws.write_number(i, 2, round(p.y, d), num)
        if p.z is not None:
            ws.write_number(i, 3, round(p.z, d), num)
        ws.write_string(i, 4, p.code or "")
        ws.write_string(i, 5, KIND_LABELS[lang][p.kind], muted)
        ws.write_string(i, 6, p.source or "", muted)
    ws.set_column(0, 0, 12)
    ws.set_column(1, 3, 14)
    ws.set_column(4, 6, 16)
    finish(ws, len(selected_points(result, opts)), 7)
    ws.autofilter(0, 0, max(1, len(selected_points(result, opts))), 6)

    # Traverse summary
    ws = wb.add_worksheet(t["traverses"])
    head(
        ws,
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
        (0, 1, 12),
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
    finish(ws, len(result.traverses), 13)

    # One sheet per traverse (computation sheet)
    for k, tr in enumerate(result.traverses, 1):
        ws = wb.add_worksheet(f"{t['traverse_short']} {k}"[:31])
        ws.hide_gridlines(2)
        ws.write(0, 0, tr.name, title)
        head(
            ws,
            2,
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
            (0, 1, 2),
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
        head(
            ws,
            r0,
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
            (0, 1),
        )
        for i, leg in enumerate(tr.legs, r0 + 1):
            ws.write_row(i, 0, [leg.frm, leg.to])
            ws.write_number(i, 2, leg.hd_measured, mm)
            ws.write_number(i, 3, leg.n_measurements)
            ws.write_number(i, 4, leg.reduction_scale, scale)
            ws.write_number(i, 5, leg.elevation_factor, scale)
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
    head(
        ws,
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
        (0, 1, 10, 11),
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
    finish(ws, len(result.detail), 12)

    # Least-squares adjustment
    adj = result.adjustment
    if adj is not None:
        el = lang == "el"
        ws = wb.add_worksheet("Συνόρθωση" if el else "Adjustment")
        ws.hide_gridlines(2)
        ws.write(
            0, 0, "Συνόρθωση ελαχίστων τετραγώνων" if el else "Least-squares adjustment", title
        )
        gt = adj.global_test
        stats = [
            ("σ0", adj.sigma0),
            ("Βαθμοί ελευθερίας" if el else "Degrees of freedom", adj.dof),
            ("Μετρήσεις" if el else "Observations", adj.n_observations),
            ("Άγνωστοι" if el else "Unknowns", adj.n_unknowns),
            ("Κρίσιμη τιμή w" if el else "Critical w", adj.w_critical),
            ("Μέγιστο |w|" if el else "Max |w|", adj.max_w),
            ("χ² (vᵀPv)", gt.statistic if gt else None),
            ("χ² κάτω όριο" if el else "χ² lower", gt.lower if gt else None),
            ("χ² άνω όριο" if el else "χ² upper", gt.upper if gt else None),
        ]
        for i, (label, value) in enumerate(stats, 2):
            ws.write_string(i, 0, label, muted)
            if value is not None:
                ws.write_number(i, 1, value)
        r0 = len(stats) + 4
        head(
            ws,
            r0,
            [t["name"], "σX (mm)", "σY (mm)", "σZ (mm)", "a95 (mm)", "b95 (mm)", "θ (gon)"],
            (0,),
        )
        row = r0
        for pnt in result.points:
            if pnt.sx is None and pnt.sz is None:
                continue
            row += 1
            ws.write_string(row, 0, safe_text(pnt.name))
            for c, v in ((1, pnt.sx), (2, pnt.sy), (3, pnt.sz)):
                if v is not None:
                    ws.write_number(row, c, round(v * 1000, 2))
            if pnt.ellipse is not None:
                e = pnt.ellipse
                ws.write_number(row, 4, round(e.a * e.k95 * 1000, 2))
                ws.write_number(row, 5, round(e.b * e.k95 * 1000, 2))
                ws.write_number(row, 6, round(from_rad(e.theta, "gon"), 2))
        r1 = row + 3
        kinds = {
            "direction": "διεύθυνση" if el else "direction",
            "distance": "απόσταση" if el else "distance",
            "height": "υψομ. διαφορά" if el else "height diff.",
        }
        head(
            ws,
            r1,
            [
                t["kind"],
                t["station"],
                t["point"],
                "υπόλοιπο" if el else "residual",
                "μονάδα" if el else "unit",
                "r",
                "w",
                "!",
            ],
            (0, 1, 2, 4, 7),
        )
        flag = wb.add_format({"font_color": color("danger"), "bold": True})
        for i, o in enumerate(sorted(adj.observations, key=lambda o: -abs(o.w or 0)), r1 + 1):
            ws.write_string(i, 0, kinds[o.kind])
            ws.write_string(i, 1, safe_text(o.station))
            ws.write_string(i, 2, safe_text(o.target))
            if o.kind == "direction":
                ws.write_number(i, 3, round(rad_to_cc(o.residual), 2))
                ws.write_string(i, 4, "cc")
            else:
                ws.write_number(i, 3, round(o.residual * 1000, 2))
                ws.write_string(i, 4, "mm")
            ws.write_number(i, 5, round(o.redundancy, 3))
            if o.w is not None:
                ws.write_number(i, 6, round(o.w, 2))
            if o.flagged:
                ws.write_string(i, 7, "●", flag)
        ws.set_column(0, 0, 22)
        ws.set_column(1, 7, 12)

    # Line work
    if result.linework:
        ws = wb.add_worksheet("Γραμμές" if lang == "el" else "Lines")
        head(
            ws,
            0,
            [t["name"], t["code"], t["points"], t["kind"], "m", "m²"],
            (0, 1, 2, 3),
        )
        for i, ln in enumerate(result.linework, 1):
            ws.write_string(i, 0, safe_text(ln.name))
            ws.write_string(i, 1, safe_text(ln.code))
            ws.write_string(i, 2, safe_text(" → ".join(ln.points)))
            closed = ("κλειστή" if lang == "el" else "closed") if ln.closed else "–"
            ws.write_string(i, 3, closed)
            ws.write_number(i, 4, round(ln.length, d))
            if ln.area is not None:
                ws.write_number(i, 5, round(ln.area, 3))
        ws.set_column(0, 1, 14)
        ws.set_column(2, 2, 50)
        ws.set_column(3, 5, 12)
        finish(ws, len(result.linework), 6)

    # Issues
    ws = wb.add_worksheet(t["issues"])
    head(ws, 0, [t["severity"], t["code"], t["message"]], (0, 1, 2))
    for i, iss in enumerate(result.issues, 1):
        ws.write_row(i, 0, [iss.severity, iss.code, localize(iss, lang)])
    ws.set_column(0, 1, 26)
    ws.set_column(2, 2, 100)
    finish(ws, len(result.issues), 3)

    wb.close()
    return buf.getvalue()
