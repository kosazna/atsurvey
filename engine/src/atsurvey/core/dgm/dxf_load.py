"""Safe DXF loading from bytes and conversion of entities to plain coordinates.

ASCII DXF is read with ezdxf's recover mode (tolerates small structural errors of CAD
programs; text encoding from $DWGCODEPAGE for DXF ≤ 2004, UTF-8 from 2007 on, ``\\U+XXXX``
escapes decoded). Binary DXF goes through ezdxf's file reader. Any failure is a
:class:`DxfLoadError` with a short reason, never an unhandled exception.
"""

from __future__ import annotations

import io
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any

#: Model-space entities beyond this are not analysed (bounds CPU and memory)
MAX_ENTITIES = 200_000


class DxfLoadError(ValueError):
    pass


@dataclass(frozen=True)
class Loaded:
    doc: Any
    recovered: int


def load_dxf(data: bytes) -> Loaded:
    try:
        import ezdxf
        from ezdxf import recover
    except ImportError as exc:  # pragma: no cover - ezdxf is an export dependency
        raise DxfLoadError("DXF support is not installed") from exc
    if not data.strip():
        raise DxfLoadError("Empty file")
    try:
        if data.startswith(b"AutoCAD Binary DXF"):
            fd, tmp = tempfile.mkstemp(suffix=".dxf")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                return Loaded(ezdxf.readfile(tmp), 0)  # pyright: ignore[reportPrivateImportUsage]
            finally:
                os.unlink(tmp)
        doc, auditor = recover.read(io.BytesIO(data))
        return Loaded(doc, len(auditor.errors) if auditor.has_errors else 0)
    except DxfLoadError:
        raise
    except Exception as exc:  # ezdxf raises DXFStructureError and several others
        raise DxfLoadError(f"Not a readable DXF file ({type(exc).__name__})") from exc


Pt = tuple[float, float]


def finite(*vals: float) -> bool:
    return all(math.isfinite(v) for v in vals)


def lwpolyline_points(e: Any) -> tuple[list[Pt], bool, bool]:
    """(points, closed flag, has arcs) of an LWPOLYLINE in WCS-equivalent x/y (OCS assumed
    to be the default; a non-default extrusion is reported separately)."""
    pts = [(float(x), float(y)) for x, y, *_ in e.get_points("xy")]
    bulges = any(abs(float(b)) > 1e-12 for *_, b in e.get_points("xyb"))
    return pts, bool(e.closed), bulges


def polyline_points(e: Any) -> tuple[list[Pt], bool, list[float]]:
    """(points, closed flag, z values) of a heavy POLYLINE (2D or 3D)."""
    pts: list[Pt] = []
    zs: list[float] = []
    for v in e.vertices:
        loc = v.dxf.location
        pts.append((float(loc.x), float(loc.y)))
        zs.append(float(loc.z))
    return pts, bool(e.is_closed), zs


def strip_closing(pts: list[Pt], tol: float = 1e-9) -> tuple[list[Pt], bool]:
    """Remove a repeated closing vertex; returns (points, whether it was repeated)."""
    if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= tol:
        return pts[:-1], True
    return pts, False


def dedupe(pts: list[Pt], tol: float = 1e-9) -> list[Pt]:
    out: list[Pt] = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(p)
    return out
