# pyright: reportArgumentType=false
# (pyshp's type hints reject BytesIO streams and None field values that it handles fine)
"""ESRI Shapefile export (PointZ for points, PolyLineZ for traverses), zipped, EPSG:2100."""

from __future__ import annotations

import io
import zipfile

import shapefile  # pyshp

from ..core.models import ProjectResult
from . import ExportOptions, selected_points

_PRJ_CACHE: str | None = None


def egsa87_prj() -> str:
    global _PRJ_CACHE
    if _PRJ_CACHE is None:
        from pyproj import CRS

        _PRJ_CACHE = CRS.from_epsg(2100).to_wkt("WKT1_ESRI")
    return _PRJ_CACHE


def _write(kind: int, fill) -> dict[str, bytes]:
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=kind, encoding="utf-8")
    fill(w)
    w.close()
    return {"shp": shp.getvalue(), "shx": shx.getvalue(), "dbf": dbf.getvalue()}


def to_shapefile_zip(base: str, result: ProjectResult, opts: ExportOptions) -> bytes:
    d = opts.decimals
    pts = selected_points(result, opts)

    def fill_points(w: shapefile.Writer) -> None:
        w.field("NAME", "C", size=40)
        w.field("KIND", "C", size=12)
        w.field("CODE", "C", size=40)
        w.field("X", "N", size=14, decimal=d)
        w.field("Y", "N", size=14, decimal=d)
        w.field("Z", "N", size=10, decimal=d)
        w.field("LABEL_Z", "C", size=12)
        for p in pts:
            z = p.z if p.z is not None else 0.0
            w.pointz(p.x, p.y, z)
            w.record(
                p.name,
                p.kind,
                p.code or "",
                round(p.x, d),
                round(p.y, d),
                round(p.z, d) if p.z is not None else None,
                f"{p.z:.2f}" if p.z is not None else "",
            )

    files = {
        f"{base}_points.{ext}": data for ext, data in _write(shapefile.POINTZ, fill_points).items()
    }

    if result.traverses:
        lookup = {p.name: p for p in result.points}

        def fill_lines(w: shapefile.Writer) -> None:
            w.field("NAME", "C", size=80)
            w.field("KIND", "C", size=10)
            w.field("LENGTH", "N", size=12, decimal=3)
            w.field("W_LIN_MM", "N", size=10, decimal=1)
            for t in result.traverses:
                coords = []
                for leg in t.legs:
                    for n in (leg.frm, leg.to):
                        p = lookup.get(n)
                        if p and (not coords or coords[-1][:2] != [p.x, p.y]):
                            coords.append([p.x, p.y, p.z or 0.0])
                if len(coords) < 2:
                    continue
                w.linez([coords])
                w.record(
                    t.name,
                    t.kind,
                    round(t.length, 3),
                    round(t.linear_misclosure * 1000, 1)
                    if t.linear_misclosure is not None
                    else None,
                )

        files.update(
            {
                f"{base}_traverses.{ext}": data
                for ext, data in _write(shapefile.POLYLINEZ, fill_lines).items()
            }
        )

    prj = egsa87_prj().encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
        for stem in {n.rsplit(".", 1)[0] for n in files}:
            z.writestr(f"{stem}.prj", prj)
            z.writestr(f"{stem}.cpg", b"UTF-8")
    return out.getvalue()
