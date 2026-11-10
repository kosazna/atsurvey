"""DXF writer for the ΔΓΜ, per the Cadastre's specification and layer template.

* AutoCAD 2004 (AC1018), $INSUNITS = 6 (metres), $DWGCODEPAGE = ANSI_1253 (Greek text in
  cp1253), the 27 layers of Table I with the template's colours, linetypes and lineweights
  ([S1], [S9]);
* polygons are closed 2D LWPOLYLINEs, lines open LWPOLYLINEs, text is TEXT only; coordinates
  are written unrounded (shortest round-trip repr of the float64 value);
* the KAEK TEXT lies inside each PST_KAEK polygon (insertion point checked);
* everything else is on **free layers** (allowed by [S1] §4.4.1.ii):

  ======== ==========================================================================
  ATS_NEIGHBOURS  cadastral parcels not changed by a deed (context only)
  ATS_PTS   vertex numbers next to the vertices
  ATS_LBL   labels of final parcels, parts A1…/Δ1…
  ATS_TAB   coordinate table (3 decimals), areas before/after (2), change table (2)
  ATS_TTL   title block (μελετητής, εργοδότης, θέση, κλίμακα, ημερομηνία, Δήμος/ΠΕ, ΚΑΕΚ,
            ΕΓΣΑ87, μεθοδολογία εξάρτησης)
  ATS_NOTE  notes and, for a ΤΔΓΜ, the engineer's declaration ([S4] §6.2)
  ======== ==========================================================================

Every written file is re-read by the validator in the tests.
"""

from __future__ import annotations

import io
import math
import textwrap
from collections.abc import Sequence
from datetime import date

from shapely.geometry import Point, Polygon

from .geom import label_point
from .models import DgmResult, TitleBlock
from .spec import DASHED, DASHED_DESCRIPTION, DASHED_PATTERN, KIND_TITLES, LAYERS, TDGM_DECLARATION

FREE_LAYERS = {
    "ATS_NEIGHBOURS": 8,
    "ATS_PTS": 8,
    "ATS_LBL": 5,
    "ATS_TAB": 7,
    "ATS_TTL": 7,
    "ATS_NOTE": 7,
}
STYLE = "ATS"
#: Text heights on paper (mm); multiplied by scale/1000 in the drawing
KAEK_MM, LABEL_MM, POINT_MM, TABLE_MM, TITLE_MM = 2.5, 2.5, 1.8, 2.0, 3.0
WRAP = 95


def write_dgm_dxf(result: DgmResult, title: TitleBlock) -> bytes:
    import ezdxf

    doc = ezdxf.new("R2004", setup=False)  # pyright: ignore[reportPrivateImportUsage]
    doc.encoding = "cp1253"
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2
    doc.header["$LUPREC"] = 3
    if DASHED not in doc.linetypes:
        doc.linetypes.add(DASHED, pattern=list(DASHED_PATTERN), description=DASHED_DESCRIPTION)
    for spec in LAYERS:
        doc.layers.add(
            spec.name, color=spec.color, linetype=spec.linetype, lineweight=spec.lineweight
        )
    for name, color in FREE_LAYERS.items():
        doc.layers.add(name, color=color)
    doc.styles.add(STYLE, font="arial.ttf")
    msp = doc.modelspace()
    k = title.scale / 1000.0
    _geometry(msp, result, k)
    _tables(msp, result, title, k)
    return doc.encode(_to_text(doc))


def _to_text(doc) -> str:
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue()


def _text(msp, layer: str, text: str, x: float, y: float, h: float) -> None:
    msp.add_text(text, height=h, dxfattribs={"layer": layer, "style": STYLE, "insert": (x, y)})


def _kaek_insert(poly: Polygon, kaek: str, h: float) -> tuple[float, float]:
    """Centre the KAEK text on the label point if its insertion point stays inside."""
    lx, ly = label_point(poly)
    cand = (lx - 0.5 * h * 0.6 * len(kaek), ly - 0.5 * h)
    return cand if poly.contains(Point(cand)) else (lx, ly)


def _geometry(msp, result: DgmResult, k: float) -> None:
    labels_done: set[str] = set()
    for poly in result.polygons:
        coords = [(v.x, v.y) for v in poly.vertices]
        msp.add_lwpolyline(coords, format="xy", close=True, dxfattribs={"layer": poly.layer})
        shp = Polygon(coords)
        if poly.layer == "PST_KAEK" and poly.kaek:
            x, y = _kaek_insert(shp, poly.kaek, KAEK_MM * k)
            _text(msp, "PST_KAEK", poly.kaek, x, y, KAEK_MM * k)
        elif poly.layer == "ATS_NEIGHBOURS" and poly.kaek:
            x, y = label_point(shp)
            _text(msp, "ATS_LBL", poly.kaek, x, y, KAEK_MM * k)
        elif poly.layer == "BLD":
            x, y = label_point(shp)
            _text(msp, "BLD", poly.label, x, y, LABEL_MM * k)
        elif poly.layer in ("DGM_PROP_FINAL", "AREA_A", "AREA_D"):
            x, y = label_point(shp)
            dy = -1.5 * LABEL_MM * k if poly.layer == "DGM_PROP_FINAL" else 0.0
            _text(msp, "ATS_LBL", poly.label, x, y + dy, LABEL_MM * k)
        for v in poly.vertices:
            if v.name not in labels_done:
                labels_done.add(v.name)
                _text(
                    msp,
                    "ATS_PTS",
                    v.name,
                    v.x + 0.4 * POINT_MM * k,
                    v.y + 0.4 * POINT_MM * k,
                    POINT_MM * k,
                )
    for line in result.lines:
        msp.add_lwpolyline(
            [(v.x, v.y) for v in line.vertices], format="xy", dxfattribs={"layer": line.layer}
        )


def _extent(result: DgmResult) -> tuple[float, float, float, float]:
    xs = [v.x for p in result.polygons for v in p.vertices] or [0.0]
    ys = [v.y for p in result.polygons for v in p.vertices] or [0.0]
    return min(xs), min(ys), max(xs), max(ys)


class _Cursor:
    """Writes text rows downwards from (x, y)."""

    def __init__(self, msp, layer: str, x: float, y: float, h: float) -> None:
        self.msp, self.layer, self.x, self.y, self.h = msp, layer, x, y, h

    def row(self, cells: list[str], widths: Sequence[float]) -> None:
        x = self.x
        for cell, w in zip(cells, widths, strict=False):
            if cell:
                _text(self.msp, self.layer, cell, x, self.y, self.h)
            x += w * self.h
        self.y -= 1.6 * self.h

    def gap(self, n: float = 1.0) -> None:
        self.y -= 1.6 * self.h * n


def _fmt(v: float | None, d: int) -> str:
    return "" if v is None or not math.isfinite(v) else f"{v:.{d}f}"


def _tables(msp, result: DgmResult, title: TitleBlock, k: float) -> None:
    _, y0, x1, y1 = _extent(result)
    h = TABLE_MM * k
    cur = _Cursor(msp, "ATS_TAB", x1 + 15 * h, y1, h)
    cur.row(["ΠΙΝΑΚΑΣ ΣΥΝΤΕΤΑΓΜΕΝΩΝ (ΕΓΣΑ 87)"], [40])
    cur.row(["Σ", "X", "Y"], [8, 14, 14])
    for p in result.points:
        cur.row([p.name, f"{p.x:.3f}", f"{p.y:.3f}"], [8, 14, 14])
    cur.gap()
    cur.row(["ΠΙΝΑΚΑΣ ΕΜΒΑΔΩΝ (τ.μ.)"], [40])
    cur.row(["ΓΕΩΤΕΜΑΧΙΟ", "ΑΡΧΙΚΟ", "ΤΕΛΙΚΟ", "ΔΙΑΦΟΡΑ"], [16, 10, 10, 10])
    for a in result.areas:
        cur.row(
            [a.kaek or a.label, _fmt(a.before, 2), _fmt(a.after, 2), _fmt(a.difference, 2)],
            [16, 10, 10, 10],
        )
    cur.row(
        ["ΣΥΝΟΛΟ", _fmt(result.total_before, 2), _fmt(result.total_after, 2), ""], [16, 10, 10, 10]
    )
    if result.changes:
        cur.gap()
        cur.row(["ΠΙΝΑΚΑΣ ΜΕΤΑΒΟΛΩΝ"], [40])
        widths = [8, 30, 10, 16, 16]
        cur.row(["ΤΜΗΜΑ", "ΠΕΡΙΓΡΑΦΗ", "ΕΜΒΑΔΟ", "ΑΠΟ ΚΑΕΚ", "ΣΕ ΚΑΕΚ"], widths)
        for c in result.changes:
            desc = textwrap.wrap("(" + ",".join(c.description) + ")", 26) or [""]
            cur.row([c.part, desc[0], _fmt(c.area, 2), c.from_kaek, c.to_kaek], widths)
            for more in desc[1:]:
                cur.row(["", more], widths)
    _title(msp, result, title, k, x1 + 15 * h, y0)


def _title(msp, result: DgmResult, title: TitleBlock, k: float, x: float, y_bottom: float) -> None:
    h = TITLE_MM * k
    kaeks = ", ".join(p.kaek for p in result.polygons if p.layer == "PST_KAEK" and p.kaek)
    method = "HEPOS" if title.method == "hepos" else f"Άλλη: {title.method_other}".strip()
    kind_title = KIND_TITLES["correction"] if result.kind == "correction" else KIND_TITLES["deed"]
    if title.tdgm:
        kind_title = "ΤΟΠΟΓΡΑΦΙΚΟ ΔΙΑΓΡΑΜΜΑ ΓΕΩΜΕΤΡΙΚΩΝ ΜΕΤΑΒΟΛΩΝ (ΤΔΓΜ)"
    lines = [
        kind_title,
        title.title,
        f"Θέση / τοπωνύμιο: {title.location}",
        f"Δήμος / Π.Ε.: {title.municipality}",
        f"ΚΑΕΚ: {kaeks}",
        f"Εργοδότης: {title.client}",
        f"Μελετητής: {title.author} {title.author_details}".rstrip(),
        f"Κλίμακα 1:{title.scale}    Ημερομηνία: {title.date or date.today().strftime('%d/%m/%Y')}",
        f"Σύστημα αναφοράς: ΕΓΣΑ 87    Μεθοδολογία εξάρτησης: {method}",
    ]
    notes: list[str] = []
    for para in title.notes.splitlines():
        notes.extend(textwrap.wrap(para, WRAP) or [""])
    if title.tdgm:
        notes.append("")
        notes.extend(textwrap.wrap(TDGM_DECLARATION, WRAP))
        notes.append("")
        notes.append("Ο συντάξας μηχανικός")
    y = y_bottom + (len(lines) + len(notes) + 2) * 1.6 * h
    cur = _Cursor(msp, "ATS_TTL", x, y, h)
    for ln in lines:
        if ln.strip():
            cur.row([ln], [WRAP])
    cur.gap()
    note = _Cursor(msp, "ATS_NOTE", x, cur.y, h * 0.8)
    for ln in notes:
        note.row([ln], [WRAP])
