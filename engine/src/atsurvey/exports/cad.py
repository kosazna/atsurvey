"""DXF export (AutoCAD R2013 format, opens in AutoCAD, BricsCAD, GstarCAD, ZWCAD, QCAD).

* Every point is a 3D ``INSERT`` of block ``ATS_PT`` (cross + circle) with attributes
  ``NAME``, ``ELEV`` and ``CODE``, plus a ``POINT`` entity for snapping.
* Layers: ``ATS_CONTROL``, ``ATS_TRAVERSE``, ``ATS_DETAIL`` (detail points with a code go
  to ``ATS_DETAIL_<CODE>`` so users can freeze/colour by code), ``ATS_TRAVERSE_LINES``.
"""

from __future__ import annotations

import io
import math
import re

import ezdxf
from ezdxf.enums import TextEntityAlignment

from ..core.models import ProjectResult
from . import ExportOptions, selected_points

LAYER_COLORS = {"ATS_CONTROL": 1, "ATS_TRAVERSE": 5, "ATS_DETAIL": 3, "ATS_TRAVERSE_LINES": 8}


def _code_layer(code: str) -> str:
    safe = re.sub(r"[<>/\\\":;?*|=`,]+", "_", code.strip().upper())[:200]
    return f"ATS_DETAIL_{safe}" if safe else "ATS_DETAIL"


def _line_layer(code: str) -> str:
    safe = re.sub(r"[<>/\\\":;?*|=`,]+", "_", code.strip().upper())[:200]
    return f"ATS_LINE_{safe}" if safe else "ATS_LINE"


def to_dxf(result: ProjectResult, opts: ExportOptions) -> bytes:
    doc = ezdxf.new("R2013", setup=True)  # pyright: ignore[reportPrivateImportUsage]
    doc.header["$INSUNITS"] = 6  # metres
    doc.header["$PDMODE"] = 0
    th = opts.dxf_text_height
    for name, color in LAYER_COLORS.items():
        doc.layers.add(name, color=color)
    # brand font; CAD programs substitute a default if IBM Plex Sans is not installed
    doc.styles.add("ATS", font="IBMPlexSans-Regular.ttf")

    blk = doc.blocks.new("ATS_PT")
    s = th * 0.4
    blk.add_line((-s, 0), (s, 0))
    blk.add_line((0, -s), (0, s))
    blk.add_circle((0, 0), s * 0.6)
    blk.add_attdef("NAME", (th * 0.5, th * 0.3), dxfattribs={"height": th, "style": "ATS"})
    blk.add_attdef("ELEV", (th * 0.5, -th * 1.1), dxfattribs={"height": th * 0.8, "style": "ATS"})
    blk.add_attdef("CODE", (th * 0.5, -th * 2.3), dxfattribs={"height": th * 0.7, "style": "ATS"})

    msp = doc.modelspace()
    d = opts.decimals
    for p in selected_points(result, opts):
        if p.kind == "control":
            layer = "ATS_CONTROL"
        elif p.kind == "traverse":
            layer = "ATS_TRAVERSE"
        else:
            layer = _code_layer(p.code) if p.code else "ATS_DETAIL"
            if layer not in doc.layers:
                doc.layers.add(layer, color=3)
        z = p.z if p.z is not None else 0.0
        msp.add_point((p.x, p.y, z), dxfattribs={"layer": layer})
        ref = msp.add_blockref("ATS_PT", (p.x, p.y, z), dxfattribs={"layer": layer})
        ref.add_auto_attribs(
            {
                "NAME": p.name,
                "ELEV": f"{p.z:.{min(d, 3)}f}" if p.z is not None else "",
                "CODE": p.code or "",
            }
        )

    lookup = {p.name: p for p in result.points}
    for t in result.traverses:
        verts = []
        for leg in t.legs:
            for n in (leg.frm, leg.to):
                p = lookup.get(n)
                if p and (not verts or verts[-1][:2] != (p.x, p.y)):
                    verts.append((p.x, p.y, p.z or 0.0))
        if len(verts) >= 2:
            msp.add_polyline3d(verts, dxfattribs={"layer": "ATS_TRAVERSE_LINES"})
            mid = verts[len(verts) // 2]
            msp.add_text(
                t.name, height=th * 0.8, dxfattribs={"layer": "ATS_TRAVERSE_LINES", "style": "ATS"}
            ).set_placement((mid[0], mid[1]), align=TextEntityAlignment.BOTTOM_CENTER)

    # 95 % error ellipses from the least-squares adjustment, exaggerated for visibility
    scale = opts.dxf_ellipse_scale
    with_ellipse = [p for p in selected_points(result, opts) if p.ellipse is not None]
    if scale > 0 and with_ellipse:
        layer = f"ATS_ELLIPSE_X{scale:g}"
        doc.layers.add(layer, color=6)
        for p in with_ellipse:
            e = p.ellipse
            assert e is not None
            a = e.a * e.k95 * scale
            b = e.b * e.k95 * scale
            if a <= 0:
                continue
            major = (a * math.sin(e.theta), a * math.cos(e.theta), 0.0)
            msp.add_ellipse(
                (p.x, p.y, p.z or 0.0),
                major_axis=major,
                ratio=max(min(b / a, 1.0), 1e-6),
                dxfattribs={"layer": layer},
            )

    # field-code line work: one layer per feature code, 3D polylines (closed when coded so)
    for line in result.linework:
        verts = [(lookup[n].x, lookup[n].y, lookup[n].z or 0.0) for n in line.points if n in lookup]
        if len(verts) < 2:
            continue
        layer = _line_layer(line.code)
        if layer not in doc.layers:
            doc.layers.add(layer, color=7)
        pl = msp.add_polyline3d(verts, dxfattribs={"layer": layer})
        if line.closed:
            pl.close(True)

    if result.summary.extent:
        x0, y0, x1, y1 = result.summary.extent
        doc.set_modelspace_vport(
            height=max(y1 - y0, x1 - x0, 10) * 1.2, center=((x0 + x1) / 2, (y0 + y1) / 2)
        )

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
