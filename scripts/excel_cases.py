"""Convert the reference Excel workbooks into validation cases (engine/tests/fixtures/excel/).

    uv run --with openpyxl python scripts/excel_cases.py traverse <workbook.xlsx> <name>
    uv run --with openpyxl python scripts/excel_cases.py detail   <workbook.xlsx> <sheet> <name>

Only numbers are extracted (observations, control points, the workbook's own results); the
workbooks themselves are not stored. Layouts supported:

* **traverse** — sheet "ΕΠΙΛΥΣΗ": angle rows M/N/O/P (back, station, fore, β in grad), distance
  rows A/B/C/D/E/F/G (forward row: station B → C; backward row: station B → A; ΥΟ, ΥΣ,
  zenith, slope distance), control points AC/AF/AG/AH rows 3–6, results in the second
  "α/α" column block, scale factor next to the "κ" label.
* **detail** — a radiation sheet (wb "ΤΑΧΥΜΕΤΡΙΚΗ"): station U2, zero point U6, list of known
  points in sheet "LIST", shots A..F (id, Hz, zenith, slope distance, ΥΣ, ΥΟ), results O/P/Q.

The workbooks reduce distances with R = 6371000, one scale factor and one mean height per
traverse, and no curvature/refraction — the matching engine settings are written into the case.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from openpyxl import load_workbook

GON = math.pi / 200.0
OUT = Path(__file__).resolve().parents[1] / "engine" / "tests" / "fixtures" / "excel"


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _name(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "-", "0") else s


def _find_label(ws, label: str, cols: str = "ACDEFGH") -> float | None:
    """Value to the right of a label cell in the control area (e.g. 'κ')."""
    for row in ws.iter_rows(min_row=1, max_row=45):
        for c in row:
            letter = getattr(c, "column_letter", "")
            if letter.startswith("A") and isinstance(c.value, str) and c.value.strip() == label:
                for off in (1, 2, 3, 4):
                    v = ws.cell(row=c.row, column=c.column + off).value
                    if _num(v) is not None:
                        return _num(v)
    return None


def traverse_case(path: str, name: str) -> dict:
    wv = load_workbook(path, data_only=True)
    ws = wv["ΕΠΙΛΥΣΗ"]
    title = load_workbook(path, data_only=True)["ΣΤΟΙΧΕΙΑ"]["A1"].value

    # control points (rows 3–6 of the control block)
    control = {}
    for r in range(3, 7):
        n = _name(ws[f"AC{r}"].value)
        x, y, z = (_num(ws[f"{c}{r}"].value) for c in ("AF", "AG", "AH"))
        if n and x is not None and y is not None:
            control.setdefault(n, {"name": n, "x": x, "y": y, "z": z})

    # angle rows: back, station, fore, β
    angles = []
    for r in range(4, 30):
        bs, st, fs, beta = (ws[f"{c}{r}"].value for c in ("M", "N", "O", "P"))
        if _name(st) is None or _num(beta) is None:
            continue
        angles.append((_name(bs), _name(st), _name(fs), float(beta)))

    # distance rows: forward (B → C) on even rows, backward (B → A) on odd rows
    shots: dict[tuple[str, str], dict] = {}
    hi: dict[str, float] = {}
    for r in range(4, 50):
        a, b, c = (_name(ws[f"{col}{r}"].value) for col in ("A", "B", "C"))
        d, e, f, g = (_num(ws[f"{col}{r}"].value) for col in ("D", "E", "F", "G"))
        if b is None or f is None or g is None:
            continue
        target = c if c is not None else a
        if target is None:
            continue
        shots[(b, target)] = {"v": f, "sd": g, "ht": e or 0.0}
        if d is not None:
            hi.setdefault(b, d)

    # setups: one per angle station, oriented with Hz = 0 on the back point
    setups = []
    for bs, st, fs, beta in angles:
        obs = []
        for tgt, hz in ((bs, 0.0), (fs, beta)):
            o = {"target": tgt, "hz": hz * GON}
            s = shots.get((st, tgt))
            if s:
                o.update({"v": s["v"] * GON, "sd": s["sd"], "target_height": s["ht"]})
            obs.append(o)
        setups.append({"station": st, "instrument_height": hi.get(st, 0.0), "observations": obs})

    # measurements from stations without an angle (e.g. the far end of an open traverse)
    with_angles = {a[1] for a in angles}
    for (st, tgt), sh in shots.items():
        if st in with_angles:
            continue
        setups.append({
            "station": st,
            "instrument_height": hi.get(st, 0.0),
            "observations": [{"target": tgt, "hz": 0.0, "v": sh["v"] * GON, "sd": sh["sd"],
                              "target_height": sh["ht"]}],
        })

    route = [angles[0][0]] + [a[1] for a in angles] + [angles[-1][2]]

    # results block: the second "α/α" header in row 2
    heads = [c.column for c in ws[2] if isinstance(c.value, str) and c.value.strip() == "α/α"]
    res_col = heads[-1]
    expected = {}
    for r in range(3, 30):
        n = _name(ws.cell(row=r, column=res_col).value)
        x, y, z = (_num(ws.cell(row=r, column=res_col + k).value) for k in (1, 2, 3))
        if n and x is not None and y is not None and n not in control:
            expected[n] = [x, y, z]

    k = _find_label(ws, "κ")
    case = {
        "source": f"{title} — {Path(path).name}",
        "kind": "traverse",
        "input": {
            "control_points": list(control.values()),
            "setups": setups,
            "traverses": [{"route": route, "name": name}],
            "settings": {
                "reduction": {
                    "scale_mode": "fixed" if k is not None else "traverse_mean",
                    "fixed_scale": k if k is not None else 1.0,
                    "elevation_mode": "traverse",
                    "curvature_refraction": False,
                    "earth_radius": 6371000.0,
                },
                "compute_detail": False,
            },
        },
        "expected": {"points": expected},
        "tolerance": {"xy_m": 0.0005, "z_m": 0.0005, "angular_cc": 0.5, "misclosure_m": 0.0005},
    }
    return case


def detail_case(path: str, sheet: str, name: str) -> dict:
    wv = load_workbook(path, data_only=True)
    ws = wv[sheet]
    known = {}
    for row in wv["LIST"].iter_rows(values_only=True):
        n = _name(row[0])
        if n and _num(row[1]) is not None:
            known[n] = {"name": n, "x": float(row[1]), "y": float(row[2]), "z": _num(row[3])}
    station, zero = _name(ws["U2"].value), _name(ws["U6"].value)
    obs = [{"target": zero, "hz": 0.0}]
    expected = {}
    for r in range(2, ws.max_row + 1):
        pid, hz, v, sd, ht, hi = (ws.cell(row=r, column=c).value for c in range(1, 7))
        if _name(pid) is None or _num(hz) is None or _num(sd) is None:
            continue
        pid = str(pid).strip()
        obs.append({
            "target": pid, "hz": float(hz) * GON, "v": float(v) * GON, "sd": float(sd),
            "target_height": float(ht),
        })
        instrument_height = float(hi)
        ex, ey, ez = (_num(ws.cell(row=r, column=c).value) for c in (15, 16, 17))
        if ex is not None:
            expected[pid] = [ex, ey, ez]
    k = _num(ws["U11"].value)
    return {
        "source": f"ΤΑΧΥΜΕΤΡΙΚΗ — {Path(path).name} / {sheet}",
        "kind": "detail",
        "input": {
            "control_points": [known[station], known[zero]],
            "setups": [{"station": station, "instrument_height": instrument_height,
                        "observations": obs}],
            "settings": {
                "reduction": {
                    "scale_mode": "fixed", "fixed_scale": k,
                    "curvature_refraction": False, "earth_radius": 6371000.0,
                },
            },
        },
        "expected": {"points": expected},
        # the workbook rounds every intermediate value to the millimetre
        "tolerance": {"xy_m": 0.003, "z_m": 0.002},
    }


def main() -> None:
    kind = sys.argv[1]
    if kind == "traverse":
        path, name = sys.argv[2], sys.argv[3]
        case = traverse_case(path, name)
    elif kind == "detail":
        path, sheet, name = sys.argv[2], sys.argv[3], sys.argv[4]
        case = detail_case(path, sheet, name)
    else:
        raise SystemExit(f"unknown kind {kind}")
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{name}.json"
    out.write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
    pts = case["expected"]["points"]
    print(f"wrote {out.relative_to(OUT.parents[3])}: {len(case['input']['setups'])} setups, "
          f"{len(pts)} expected points")


if __name__ == "__main__":
    main()
