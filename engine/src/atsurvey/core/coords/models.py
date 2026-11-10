"""Contracts of the coordinate-system tools (``/v1/coords/*``).

Point convention: for grid systems ``x`` = Easting, ``y`` = Northing (m); for geographic
systems ``x`` = λ (longitude) and ``y`` = φ (latitude), **radians**, longitudes from
Greenwich. ``z`` is a height in metres whose kind (ellipsoidal / orthometric) is stated by
the request.
"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from ..models import Issue
from .datum import DatumMethod

SystemId = Literal[
    "egsa87",
    "ggrs87_geo",
    "wgs84_geo",
    "utm34",
    "utm35",
    "tm3_west",
    "tm3_central",
    "tm3_east",
    "greek_geo",
    "hatt",
]
HeightKind = Literal["ellipsoidal", "orthometric"]

MAX_POINTS = 10_000
#: Bounds that keep nonsense out (no Greek coordinate comes near them).
MAX_ABS_COORD = 2.0e7
MAX_ABS_HEIGHT = 1.0e5
MAX_ABS_UNDULATION = 150.0


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoordPoint(_M):
    name: str | None = Field(default=None, max_length=64)
    x: FiniteFloat = Field(ge=-MAX_ABS_COORD, le=MAX_ABS_COORD)
    y: FiniteFloat = Field(ge=-MAX_ABS_COORD, le=MAX_ABS_COORD)
    z: FiniteFloat | None = Field(default=None, ge=-MAX_ABS_HEIGHT, le=MAX_ABS_HEIGHT)


class HattSpec(_M):
    """Sheet centre given directly (φ₀, λ₀) or by code from the official table."""

    sheet: str | None = Field(default=None, min_length=1, max_length=32)
    lat0: FiniteFloat | None = Field(default=None, ge=math.radians(30), le=math.radians(45))
    lon0: FiniteFloat | None = Field(default=None, ge=-math.radians(30), le=math.radians(45))
    meridian: Literal["athens", "greenwich"] = Field(
        default="athens", description="λ₀ counted from the Athens Observatory or Greenwich"
    )
    coefficients: list[FiniteFloat] | None = Field(
        default=None,
        min_length=12,
        max_length=12,
        description="User-entered ΟΚΧΕ polynomial of this sheet, A0…A5 then B0…B5: "
        "E = A0 + A1·x + A2·y + A3·x² + A4·y² + A5·x·y (N likewise with B), x, y in metres",
    )

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        has_origin = self.lat0 is not None and self.lon0 is not None
        if self.sheet is None and not has_origin:
            raise ValueError("Give the Hatt sheet centre (lat0, lon0) or a sheet code")
        if self.sheet is not None and (self.lat0 is not None or self.lon0 is not None):
            raise ValueError("Give either a Hatt sheet code or a centre, not both")
        if self.sheet is not None and self.coefficients is not None:
            raise ValueError("Polynomial coefficients go with a sheet centre, not a sheet code")
        return self


class ConvertRequest(_M):
    src: SystemId
    dst: SystemId
    points: list[CoordPoint] = Field(min_length=1, max_length=MAX_POINTS)
    src_hatt: HattSpec | None = None
    dst_hatt: HattSpec | None = None
    datum_method: DatumMethod = Field(
        default="approximate",
        description="approximate: EPSG shifts (1.5–6.5 m); official: HEPOS grids (≈ 8 cm) / ΟΚΧΕ Hatt polynomials",
    )
    height_in: HeightKind = "orthometric"
    height_out: HeightKind = "orthometric"
    geoid_undulation: FiniteFloat | None = Field(
        default=None,
        ge=-MAX_ABS_UNDULATION,
        le=MAX_ABS_UNDULATION,
        description="Constant N (m) relative to the ellipsoid of the system whose heights are "
        "ellipsoidal; h = H + N",
    )


class ConvertedPoint(_M):
    name: str | None = None
    x: float | None = Field(description="None when the point could not be converted")
    y: float | None
    z: float | None = None


class ConvertResult(_M):
    src: SystemId
    dst: SystemId
    points: list[ConvertedPoint]
    datum_shift: list[str] = Field(description="Datum shifts applied, in order (empty: none)")
    approximate: bool
    accuracy_m: float | None = Field(
        description="Nominal accuracy of the datum shift; None = exact (projection only)"
    )
    issues: list[Issue] = Field(default_factory=list)


class PointInfoRequest(_M):
    system: SystemId
    point: CoordPoint
    hatt: HattSpec | None = None
    height_kind: HeightKind = "orthometric"
    geoid_undulation: FiniteFloat | None = Field(
        default=None, ge=-MAX_ABS_UNDULATION, le=MAX_ABS_UNDULATION
    )


class PointInfoResult(_M):
    system: SystemId
    lat: float = Field(description="φ in the system's datum, rad")
    lon: float = Field(description="λ from Greenwich, rad")
    lon_athens: float | None = Field(
        default=None, description="λ from the Athens meridian (Old Greek datum only)"
    )
    x: float | None = Field(default=None, description="Grid easting (grid systems)")
    y: float | None = None
    scale_factor: float | None = Field(
        default=None, description="Point scale factor k (conformal projections)"
    )
    scale_min: float | None = Field(default=None, description="Tissot b (all projections)")
    scale_max: float | None = Field(default=None, description="Tissot a")
    convergence: float | None = Field(
        default=None,
        description="Meridian convergence γ: bearing of grid north from true north, rad",
    )
    elevation_factor: float | None = Field(
        default=None, description="R / (R + h) with h the ellipsoidal height"
    )
    combined_factor: float | None = Field(default=None, description="k · R / (R + h)")
    utm_zone: int
    tm3_zone: Literal["tm3_west", "tm3_central", "tm3_east"] | None = None
    inside_zone: bool = Field(description="Point inside the system's normal area of use")
    issues: list[Issue] = Field(default_factory=list)
