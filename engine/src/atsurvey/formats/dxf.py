"""Import points from DXF drawings (design points, existing control).

Recognised in model space:

* ``INSERT`` with attributes: the name comes from an attribute tagged NAME / POINT / PNT /
  PT / ID / ONOMA / ΟΝΟΜΑ (else the first attribute), the height from ELEV / Z / H /
  ELEVATION / ΥΨΟΜΕΤΡΟ (else the insert's z), the code from CODE / DESC / ΚΩΔΙΚΟΣ. Points
  exported by ATSurvey (block ``ATS_PT``) round-trip exactly.
* ``POINT``: named after the nearest ``TEXT``/``MTEXT`` within twice its height (at least
  1 m); otherwise numbered ``DXF1``, ``DXF2`` … A z of 0 is treated as "no height".

Both ASCII and binary DXF are read with ezdxf's recover mode, which tolerates the small
structural errors common in drawings from different CAD programs.
"""

from __future__ import annotations

import io
import math

from ..core.models import ControlPoint
from .base import ParseError, ParseResult

NAME_TAGS = {"NAME", "POINT", "PNT", "PT", "ID", "ONOMA", "ΟΝΟΜΑ", "ΣΗΜΕΙΟ"}
ELEV_TAGS = {"ELEV", "Z", "H", "ELEVATION", "ΥΨΟΜΕΤΡΟ", "ΥΨ"}
CODE_TAGS = {"CODE", "DESC", "DESCRIPTION", "ΚΩΔΙΚΟΣ", "ΚΩΔ"}
MAX_POINTS = 200_000


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.strip().replace(",", "."))
    except ValueError:
        return None


def parse_dxf(data: bytes) -> ParseResult:
    try:
        from ezdxf import recover
    except ImportError as exc:  # pragma: no cover - ezdxf is an export dependency
        raise ParseError("DXF support is not installed") from exc
    try:
        doc, auditor = recover.read(io.BytesIO(data))
    except Exception as exc:  # ezdxf raises several structure errors
        raise ParseError(f"Invalid DXF file: {exc}") from exc

    res = ParseResult(format="dxf")
    if auditor.has_errors:
        res.warnings.append(f"The DXF had {len(auditor.errors)} structural errors (recovered)")
    msp = doc.modelspace()
    points: list[ControlPoint] = []
    seen: set[str] = set()

    def add(name: str, x: float, y: float, z: float | None, code: str | None) -> None:
        if not all(math.isfinite(v) for v in (x, y)):
            return
        base, n = name, 1
        while name in seen:
            n += 1
            name = f"{base}_{n}"
        seen.add(name)
        points.append(ControlPoint(name=name, x=x, y=y, z=z, code=code or None))

    # ---- block inserts with attributes
    for ins in msp.query("INSERT"):
        attribs = {a.dxf.tag.strip().upper(): a.dxf.text.strip() for a in ins.attribs}
        if not attribs:
            continue
        name = next((v for k, v in attribs.items() if k in NAME_TAGS and v), None)
        name = name or next(iter(attribs.values()), "")
        if not name:
            continue
        loc = ins.dxf.insert
        z = next(
            (_num(v) for k, v in attribs.items() if k in ELEV_TAGS and _num(v) is not None), None
        )
        if z is None and loc.z:
            z = float(loc.z)
        code = next((v for k, v in attribs.items() if k in CODE_TAGS and v), None)
        add(name, float(loc.x), float(loc.y), z, code)
        if len(points) >= MAX_POINTS:
            raise ParseError(f"Too many points (more than {MAX_POINTS:,})")

    # ---- plain POINT entities labelled by nearby text
    labels: list[tuple[float, float, float, str]] = []
    for t in msp.query("TEXT MTEXT"):
        text = t.plain_text() if t.dxftype() == "MTEXT" else t.dxf.text
        text = (text or "").strip()
        if not text:
            continue
        ins = t.dxf.insert
        height = float(getattr(t.dxf, "char_height", 0) or getattr(t.dxf, "height", 0) or 1.0)
        labels.append((float(ins.x), float(ins.y), max(2.0 * height, 1.0), text))
    auto = 0
    for pt in msp.query("POINT"):
        loc = pt.dxf.location
        x, y = float(loc.x), float(loc.y)
        best, best_d = None, math.inf
        for lx, ly, radius, text in labels:
            d = math.hypot(lx - x, ly - y)
            if d <= radius and d < best_d:
                best, best_d = text, d
        if best is None:
            auto += 1
            best = f"DXF{auto}"
        add(best, x, y, float(loc.z) if loc.z else None, pt.dxf.layer)
        if len(points) >= MAX_POINTS:
            raise ParseError(f"Too many points (more than {MAX_POINTS:,})")

    if not points:
        raise ParseError(
            "No points found in the DXF (expected POINT entities or blocks with attributes)"
        )
    # ATSurvey's own export writes a POINT under every INSERT: keep the named insert only
    by_xy: dict[tuple[float, float], ControlPoint] = {}
    for p in points:
        key = (round(p.x, 4), round(p.y, 4))
        if key not in by_xy or by_xy[key].name.startswith("DXF"):
            by_xy[key] = p
    res.control_points = list(by_xy.values())
    unlabelled = sum(p.name.startswith("DXF") for p in res.control_points)
    if unlabelled:
        res.warnings.append(f"{unlabelled} points had no nearby label and were numbered DXF1…")
    return res.finalise()
