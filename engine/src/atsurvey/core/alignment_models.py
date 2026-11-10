"""Contracts for road alignments (οριζοντιογραφία, μηκοτομή ερυθράς). Implementation:
``core/alignment.py``; API routes ``/v1/setout/alignment*``.

Conventions: x = Easting, y = Northing (metres); azimuths are grid bearings clockwise from north
in radians; deflection angles are positive for a turn to the right (clockwise); offsets are
positive to the right of the direction of increasing chainage; grades are fractions (0.05 = 5 %).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Issue

#: Bounds that keep one request cheap (the geometry is O(vertices), queries O(points · log)).
MAX_VERTICES = 200
MAX_PVIS = 500
MAX_LOCATE = 10_000
MAX_OFFSETS = 20
MAX_STAKEOUT_ROWS = 50_000

Coord = Annotated[float, Field(allow_inf_nan=False, ge=-1e8, le=1e8)]
Length = Annotated[float, Field(allow_inf_nan=False, gt=0, le=1e6)]
Chainage = Annotated[float, Field(allow_inf_nan=False, ge=-1e7, le=1e7)]
Offset = Annotated[float, Field(allow_inf_nan=False, ge=-1e4, le=1e4)]
Name = Annotated[str, Field(max_length=64)]

ElementKind = Literal["tangent", "clothoid", "arc"]
#: Main points (international codes; see docs/setout.md for the Greek descriptions).
#: BP/EP start/end of the alignment; TS tangent→spiral; SC spiral→circle; MC middle of the
#: circular arc; CS circle→spiral; ST spiral→tangent; PC/PT start/end of an arc without spirals.
MainPointCode = Literal["BP", "TS", "SC", "MC", "CS", "ST", "PC", "PT", "EP"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------- input


class AlignmentVertex(_M):
    """Vertex (κορυφή) of the tangent polygon. Interior vertices carry the curve: radius R and
    optional clothoids given by parameter A or length L (L = A² / R). When neither exit value is
    given, the exit clothoid equals the entry one (symmetric curve); give 0 for none."""

    name: Name | None = None
    x: Coord
    y: Coord
    radius: Length | None = None
    a_in: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e5)] | None = None
    l_in: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e5)] | None = None
    a_out: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e5)] | None = None
    l_out: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e5)] | None = None

    @model_validator(mode="after")
    def _check(self) -> AlignmentVertex:
        if self.a_in is not None and self.l_in is not None:
            raise ValueError("Give the entry clothoid as A or as L, not both")
        if self.a_out is not None and self.l_out is not None:
            raise ValueError("Give the exit clothoid as A or as L, not both")
        spirals = (self.a_in, self.l_in, self.a_out, self.l_out)
        if self.radius is None and any(v for v in spirals):
            raise ValueError("A clothoid needs the radius R of the circular arc")
        return self


class ProfilePVI(_M):
    """Vertex of the vertical profile (κορυφή μηκοτομής). The parabolic vertical curve is given
    by its length L or by its parameter H (radius at the crest/sag, L = H · |g₂ − g₁|)."""

    name: Name | None = None
    chainage: Chainage
    elevation: Annotated[float, Field(allow_inf_nan=False, ge=-1e4, le=1e5)]
    length: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1e5)] | None = None
    radius: Annotated[float, Field(allow_inf_nan=False, gt=0, le=1e7)] | None = None

    @model_validator(mode="after")
    def _check(self) -> ProfilePVI:
        if self.length is not None and self.radius is not None:
            raise ValueError("Give the vertical curve as length L or parameter H, not both")
        return self


class VerticalProfile(_M):
    pvis: list[ProfilePVI] = Field(min_length=2, max_length=MAX_PVIS)


class AlignmentRequest(_M):
    vertices: list[AlignmentVertex] = Field(min_length=2, max_length=MAX_VERTICES)
    start_chainage: Chainage = 0.0
    profile: VerticalProfile | None = None


# --------------------------------------------------------------------------- output


class VertexRow(_M):
    """Curve data at a vertex (the Greek computation-sheet columns in brackets)."""

    name: str | None
    x: float
    y: float
    deflection: float | None = Field(
        default=None, description="Signed deflection Δ (rad), positive = right turn"
    )
    radius: float | None = None
    a_in: float | None = None
    l_in: float | None = None
    a_out: float | None = None
    l_out: float | None = None
    tau_in: float | None = Field(default=None, description="Clothoid tangent angle τ = L / 2R")
    tau_out: float | None = None
    shift_in: float | None = Field(default=None, description="Shift ΔR of the arc (p)")
    shift_out: float | None = None
    xm_in: float | None = Field(default=None, description="Abscissa of the shifted centre XM (k)")
    xm_out: float | None = None
    t_in: float | None = Field(default=None, description="Tangent length vertex → TS/PC (T)")
    t_out: float | None = Field(default=None, description="Tangent length vertex → ST/PT")
    arc_angle: float | None = Field(default=None, description="Central angle of the arc (rad)")
    arc_length: float | None = None
    curve_length: float | None = Field(default=None, description="L₁ + arc + L₂")
    external: float | None = Field(default=None, description="Vertex → arc distance (E)")
    centre_x: float | None = None
    centre_y: float | None = None
    chainage_start: float | None = None
    chainage_end: float | None = None


class AlignmentElement(_M):
    kind: ElementKind
    vertex: str | None = Field(default=None, description="Vertex of the curve it belongs to")
    start_chainage: float
    end_chainage: float
    length: float
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    start_azimuth: float
    end_azimuth: float
    radius: float | None = Field(default=None, description="Arc radius, or R at the clothoid end")
    a: float | None = Field(default=None, description="Clothoid parameter A")
    turn: Literal["left", "right"] | None = None


class MainPoint(_M):
    code: MainPointCode
    vertex: str | None = None
    chainage: float
    x: float
    y: float
    azimuth: float
    z: float | None = Field(default=None, description="Design elevation (with a profile)")


class GradeRow(_M):
    from_chainage: float
    to_chainage: float
    grade: float = Field(description="Fraction (0.05 = 5 %)")


class VerticalCurveRow(_M):
    name: str | None
    chainage: float
    elevation: float
    kind: Literal["crest", "sag", "none"]
    length: float
    radius: float | None = Field(default=None, description="Parameter H = L / |g₂ − g₁|")
    pvc_chainage: float
    pvc_elevation: float
    pvt_chainage: float
    pvt_elevation: float
    extreme_chainage: float | None = Field(default=None, description="High/low point in the curve")
    extreme_elevation: float | None = None


class ProfileResult(_M):
    grades: list[GradeRow]
    curves: list[VerticalCurveRow]


class AlignmentResult(_M):
    vertices: list[VertexRow]
    elements: list[AlignmentElement]
    main_points: list[MainPoint]
    start_chainage: float
    end_chainage: float
    length: float
    polyline: list[tuple[float, float]] = Field(description="Densified axis for previews")
    profile: ProfileResult | None = None
    issues: list[Issue] = Field(default_factory=list)


# --------------------------------------------------------------------------- queries


class StationQuery(_M):
    name: Name | None = None
    chainage: Chainage
    offset: Offset = 0.0


class PointQuery(_M):
    name: Name | None = None
    x: Coord
    y: Coord
    z: Annotated[float, Field(allow_inf_nan=False, ge=-1e4, le=1e5)] | None = None


class LocateRequest(_M):
    alignment: AlignmentRequest
    stations: list[StationQuery] = Field(default_factory=list, max_length=MAX_LOCATE)
    points: list[PointQuery] = Field(default_factory=list, max_length=MAX_LOCATE)


class StationRow(_M):
    """(chainage, offset) → coordinates."""

    name: str | None
    chainage: float
    offset: float
    x: float
    y: float
    azimuth: float = Field(description="Azimuth of the axis at the chainage")
    z: float | None = Field(default=None, description="Design elevation of the axis")
    inside: bool = Field(description="False when the chainage is beyond the ends (extended)")


class PointRow(_M):
    """Coordinates → (chainage, offset) by perpendicular projection on the axis."""

    name: str | None
    x: float
    y: float
    chainage: float
    offset: float
    azimuth: float
    element: int | None = Field(description="Index of the element it projects on")
    inside: bool = Field(description="False when the foot lies on the extension of an end")
    z_design: float | None = None
    dz: float | None = Field(default=None, description="Point z − design elevation of the axis")


class LocateResult(_M):
    stations: list[StationRow]
    points: list[PointRow]


class AlignmentStakeoutRequest(_M):
    alignment: AlignmentRequest
    interval: Annotated[float, Field(allow_inf_nan=False, gt=0, le=10_000)] = 20.0
    offsets: list[Offset] = Field(
        default_factory=lambda: [0.0], min_length=1, max_length=MAX_OFFSETS
    )
    include_main_points: bool = True
    from_chainage: Chainage | None = None
    to_chainage: Chainage | None = None


class AlignmentStakeoutRow(_M):
    chainage: float
    offset: float
    code: MainPointCode | None = None
    vertex: str | None = None
    x: float
    y: float
    azimuth: float
    z: float | None = None


class AlignmentStakeoutResult(_M):
    rows: list[AlignmentStakeoutRow]
