"""Exports: CSV, Excel, ESRI Shapefile (zip), DXF and the PDF computation report."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from ..core.models import PointKind, ProjectInput, ProjectResult, ResultPoint
from ..core.units import AngleUnit

ExportFormat = Literal["csv", "xlsx", "shp", "dxf", "pdf"]

MEDIA_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "shp": "application/zip",
    "dxf": "application/dxf",
    "pdf": "application/pdf",
}
EXTENSIONS = {"csv": "csv", "xlsx": "xlsx", "shp": "zip", "dxf": "dxf", "pdf": "pdf"}


class ExportOptions(BaseModel):
    angle_unit: AngleUnit = "gon"
    decimals: int = Field(default=3, ge=0, le=6)
    csv_delimiter: Literal[",", ";", "\t", " "] = ","
    csv_header: bool = True
    include: list[PointKind] = Field(default_factory=lambda: ["control", "traverse", "detail"])
    dxf_text_height: float = Field(default=0.5, gt=0, le=50)
    dxf_ellipse_scale: float = Field(
        default=1000.0,
        ge=0,
        le=100_000,
        description="Exaggeration of 95 % error ellipses in DXF (0 = omit)",
    )
    language: Literal["el", "en"] = "el"


def selected_points(result: ProjectResult, opts: ExportOptions) -> list[ResultPoint]:
    kinds = set(opts.include)
    return [p for p in result.points if p.kind in kinds]


_GREEK = dict(
    zip(
        "αβγδεζηικλμνξοπρσςτυφχω",
        [
            "a",
            "v",
            "g",
            "d",
            "e",
            "z",
            "i",
            "i",
            "k",
            "l",
            "m",
            "n",
            "x",
            "o",
            "p",
            "r",
            "s",
            "s",
            "t",
            "y",
            "f",
            "ch",
            "o",
        ],
        strict=True,
    )
)
_GREEK.update({"θ": "th", "ψ": "ps"})


def slug(name: str) -> str:
    """ASCII file-name slug (Greek is transliterated after stripping accents)."""
    n = unicodedata.normalize("NFD", name)
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    out = []
    for ch in n:
        low = ch.lower()
        if low in _GREEK:
            tr = _GREEK[low]
            out.append(tr.capitalize() if ch != low else tr)
        else:
            out.append(ch)
    n = "".join(out)
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", n).strip("_")
    return n or "project"


def export(
    fmt: ExportFormat,
    project_name: str,
    inp: ProjectInput,
    result: ProjectResult,
    opts: ExportOptions | None = None,
) -> tuple[bytes, str, str]:
    """Returns (content, filename, media_type)."""
    opts = opts or ExportOptions()
    base = slug(project_name)
    if fmt == "csv":
        from .tabular import to_csv

        data = to_csv(result, opts)
    elif fmt == "xlsx":
        from .tabular import to_xlsx

        data = to_xlsx(project_name, inp, result, opts)
    elif fmt == "shp":
        from .gis import to_shapefile_zip

        data = to_shapefile_zip(base, result, opts)
    elif fmt == "dxf":
        from .cad import to_dxf

        data = to_dxf(result, opts)
    elif fmt == "pdf":
        from .report import to_pdf

        data = to_pdf(project_name, inp, result, opts)
    else:  # pragma: no cover - guarded by the Literal type
        raise ValueError(f"Unknown export format {fmt}")
    return data, f"{base}.{EXTENSIONS[fmt]}", MEDIA_TYPES[fmt]


__all__ = ["MEDIA_TYPES", "ExportFormat", "ExportOptions", "export", "selected_points", "slug"]
