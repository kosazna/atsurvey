"""Contracts for parcels (ιδιοκτησίες / γεωτεμάχια): geometry, area comparison, subdivision
(κατάτμηση) and merge (συνένωση).

Conventions: x = Easting, y = Northing, metres (ΕΓΣΑ87 grid), azimuths in radians clockwise
from grid north. Areas are **grid (projection) areas**, as registered by the Hellenic Cadastre.
Implementations: ``core/parcels.py``, ``core/parcels_subdivide.py``, ``core/parcels_merge.py``.
API routes: ``/v1/parcels/*`` (see docs/parcels.md).

Arc convention (one convention only): an arc is attached to the **side that starts at a
vertex** (vertex i → vertex i+1) and is given by its ``radius`` and the ``side`` towards which it
bulges, relative to the direction of travel i → i+1 (``left`` / ``right``). The minor arc
(central angle ≤ π) is meant unless ``large`` is set.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import Issue

#: Coordinates and lengths must be finite and of survey magnitude (no NaN/inf, no 1e300).
Coord = Annotated[float, Field(allow_inf_nan=False, ge=-1e8, le=1e8)]
Length = Annotated[float, Field(allow_inf_nan=False, gt=0, le=1e7)]
AreaM2 = Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e12)]
Name = Annotated[str, Field(max_length=64)]

MAX_VERTICES = 1000
MAX_MERGE_PARCELS = 20
MAX_PARTS = 50


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArcSpec(_M):
    """Circular arc on the side from this vertex to the next one."""

    radius: Length
    side: Literal["left", "right"] = Field(
        description="Side towards which the arc bulges, looking from this vertex to the next"
    )
    large: bool = Field(default=False, description="Major arc (central angle > π)")


class ParcelVertex(_M):
    name: Name
    x: Coord
    y: Coord
    arc: ArcSpec | None = Field(default=None, description="Arc on the side to the next vertex")


class Parcel(_M):
    label: Annotated[str, Field(max_length=100)] = Field(
        default="", description="Free text, e.g. owner or parcel number"
    )
    kaek: Annotated[str, Field(max_length=32)] | None = Field(
        default=None, description="ΚΑΕΚ (Hellenic Cadastre parcel code), free text"
    )
    vertices: list[ParcelVertex] = Field(min_length=1, max_length=MAX_VERTICES)


class XYPoint(_M):
    x: float
    y: float


class SideRow(_M):
    frm: str
    to: str
    length: float = Field(description="Chord length, m")
    azimuth: float = Field(description="Chord azimuth, rad")
    arc_length: float | None = Field(default=None, description="Arc length (arcs only), m")
    radius: float | None = None
    central_angle: float | None = Field(default=None, description="rad")
    segment_area: float | None = Field(
        default=None, description="Area between chord and arc (added or removed), m²"
    )


class ParcelGeometry(_M):
    """Everything a parcel table needs. ``area`` etc. are None when the parcel is invalid."""

    label: str
    kaek: str | None
    vertices: list[ParcelVertex] = Field(description="Cleaned vertices (duplicates removed)")
    sides: list[SideRow]
    area: float | None = Field(description="Grid area, m² (arcs included)")
    perimeter: float | None = Field(description="m (arc lengths for arcs)")
    orientation: Literal["clockwise", "counterclockwise"] | None
    centroid: XYPoint | None
    has_arcs: bool
    valid: bool
    issues: list[Issue]


# ------------------------------------------------------------------------ area comparison


class AreaToleranceRule(_M):
    """A tolerance T(E) in m², where E is the reference area (deed or Cadastre):

    * ``fixed``:    T = ``value`` m²
    * ``percent``:  T = ``value`` % · E
    * ``formula``:  T = ``a`` + ``b`` · √E
    * ``cadastre``: T = U0 · Π · (1 + U0 / √E)  ≡ [(√E + 2·U0)² − E] · Π / (4·√E), with Π the
      parcel perimeter and U0 = ``u0`` (Hellenic Cadastre, ΟΚΧΕ 461/03/2008, ΦΕΚ Β΄ 1510/2008).

    ``cap_percent`` optionally caps T at that percentage of E (7 % for areas surveyed under the
    2007 specifications). ``source`` names where the rule comes from; it is shown next to every
    verdict.
    """

    kind: Literal["fixed", "percent", "formula", "cadastre"]
    value: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e9)] | None = None
    a: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e9)] | None = None
    b: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e6)] | None = None
    u0: Annotated[float, Field(allow_inf_nan=False, gt=0, le=100)] | None = Field(
        default=None, description="Positional uncertainty U0 of the cadastral formula, m"
    )
    cap_percent: Annotated[float, Field(allow_inf_nan=False, gt=0, le=100)] | None = None
    source: Annotated[str, Field(max_length=300)] = ""


class AreaTolerancePreset(_M):
    id: str
    label: str
    rule: AreaToleranceRule
    to_be_confirmed: bool = Field(
        default=False, description="Value still awaiting confirmation by the owner"
    )


class AreaCompareRequest(_M):
    """Give either ``surveyed_area`` or a ``parcel`` to compute it from."""

    surveyed_area: AreaM2 | None = None
    parcel: Parcel | None = None
    deed_area: AreaM2 | None = Field(default=None, description="Τίτλος / συμβόλαιο, m²")
    cadastre_area: AreaM2 | None = Field(
        default=None, description="Area on the cadastral diagram (Κτηματολόγιο), m²"
    )
    perimeter: Length | None = Field(
        default=None,
        description="Parcel perimeter Π for the cadastral rule (computed from ``parcel``)",
    )
    tolerance: AreaToleranceRule | None = None


class AreaCompareRow(_M):
    kind: Literal["surveyed_vs_deed", "surveyed_vs_cadastre", "cadastre_vs_deed"]
    area: float = Field(description="Compared area, m²")
    reference_area: float = Field(description="Reference area E, m²")
    difference: float = Field(description="area − reference, m²")
    difference_percent: float | None = Field(description="difference / reference · 100")
    tolerance: float | None = Field(default=None, description="T(E), m²")
    within: bool | None = Field(default=None, description="|difference| ≤ T(E)")


class AreaCompareResult(_M):
    surveyed_area: float
    perimeter: float | None = Field(default=None, description="Π used by the cadastral rule")
    rows: list[AreaCompareRow]
    tolerance: AreaToleranceRule | None
    issues: list[Issue]


# --------------------------------------------------------------------------- subdivision


class SubdivideRequest(_M):
    """Cut a parcel into parts (κατάτμηση). Straight sides only.

    ``method``:
    * ``parallel``: cut lines parallel to side ``side`` (index of the side that starts at vertex
      ``side``); part 1 contains that side.
    * ``perpendicular``: cut lines perpendicular to side ``side``; part 1 lies at the start
      vertex end of the side (``from_end = "start"``) or at its end vertex (``"end"``).
    * ``pivot``: every cut line passes through ``pivot`` (a vertex name, or coordinates on the
      boundary); part 1 starts at the pivot and runs towards the neighbouring vertex
      ``towards`` (default: the next vertex in input order).

    ``parts``: areas in m² (``mode = "areas"``) or ratios (``mode = "ratios"``). Parts are cut
    off in order; the remainder becomes the last part. With areas whose sum is smaller than the
    parcel, an extra remainder part is returned.
    """

    parcel: Parcel
    method: Literal["parallel", "perpendicular", "pivot"]
    mode: Literal["areas", "ratios"] = "areas"
    parts: list[Annotated[float, Field(allow_inf_nan=False, gt=0, le=1e12)]] = Field(
        min_length=1, max_length=MAX_PARTS
    )
    side: int | None = Field(default=None, ge=0, description="Side index (parallel/perp.)")
    from_end: Literal["start", "end"] = "start"
    pivot: Name | None = Field(default=None, description="Vertex name for a pivot cut")
    pivot_point: XYPoint | None = Field(
        default=None, description="Or: pivot coordinates on the boundary"
    )
    towards: Name | None = None
    new_point_prefix: Annotated[str, Field(max_length=16)] = "Ν"
    new_point_start: int = Field(default=1, ge=0, le=1_000_000)
    part_labels: list[Annotated[str, Field(max_length=100)]] | None = Field(
        default=None, max_length=MAX_PARTS + 1
    )
    frontage_side: int | None = Field(
        default=None, ge=0, description="Side of the original parcel used as frontage (road)"
    )
    min_frontage: Length | None = None


class CutLine(_M):
    a: ParcelVertex
    b: ParcelVertex
    length: float
    azimuth: float


class SubdivisionPart(_M):
    geometry: ParcelGeometry
    requested_area: float | None = Field(description="None for the remainder")
    area_error: float | None = Field(description="area − requested, m²")
    frontage: float | None = None


class SubdivisionResult(_M):
    original: ParcelGeometry
    parts: list[SubdivisionPart]
    cut_lines: list[CutLine]
    new_points: list[ParcelVertex]
    issues: list[Issue]


# ---------------------------------------------------------------------------------- merge


class MergeRequest(_M):
    parcels: list[Parcel] = Field(min_length=2, max_length=MAX_MERGE_PARCELS)
    snap_tolerance: Annotated[float, Field(allow_inf_nan=False, gt=0, le=1.0)] = 0.001
    label: Annotated[str, Field(max_length=100)] = ""


class MergeResult(_M):
    merged: ParcelGeometry | None
    max_snap: float = Field(description="Largest distance a vertex was snapped by, m")
    inserted: list[str] = Field(
        default_factory=list, description="Vertices inserted on a neighbour's side (T-junctions)"
    )
    area_sum: float = Field(description="Sum of the input parcel areas, m²")
    issues: list[Issue]


# ------------------------------------------------------------------------------ coverage


class CoverageRequest(_M):
    """Do ``parts`` cover ``outline`` exactly (no gaps, no overlaps, nothing outside)?"""

    outline: Parcel
    parts: list[Parcel] = Field(min_length=1, max_length=MAX_PARTS + 1)
    tolerance: Annotated[float, Field(allow_inf_nan=False, gt=0, le=1.0)] = Field(
        default=1e-6, description="Vertex coincidence tolerance, m (exact-match by default)"
    )
    area_tolerance: Annotated[float, Field(allow_inf_nan=False, gt=0, le=100.0)] = Field(
        default=1e-4, description="Allowed |Σ parts − outline| in m²"
    )


class CoverageResult(_M):
    ok: bool
    outline_area: float | None
    parts_area: float
    difference: float | None = Field(description="Σ parts − outline, m²")
    issues: list[Issue]
