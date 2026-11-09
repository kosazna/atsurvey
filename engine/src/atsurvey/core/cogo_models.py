"""Contracts for the coordinate-geometry (COGO) tools and geometric levelling.

All angles are radians; azimuths are grid bearings clockwise from north; coordinates are
metres (x = Easting, y = Northing). Implementations: ``core/cogo.py``, ``core/leveling.py``.
API routes: ``/v1/cogo/*`` and ``/v1/leveling`` (see docs/contracts.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import ReductionSettings


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class XY(_M):
    x: float
    y: float
    z: float | None = None
    name: str | None = None


# ----------------------------------------------------------------------------- inverse


class InverseRequest(_M):
    a: XY
    b: XY
    reduction: ReductionSettings | None = Field(
        default=None, description="If given, also return the ground (horizontal) distance"
    )


class InverseResult(_M):
    dx: float
    dy: float
    dz: float | None
    distance: float = Field(description="Grid distance")
    azimuth: float
    azimuth_back: float
    distance_ground: float | None = Field(
        default=None, description="Grid distance reduced back to the ground (÷ k ÷ R/(R+H))"
    )
    slope_distance: float | None = None
    gradient_percent: float | None = None


# ------------------------------------------------------------------------------- polar


class PolarRequest(_M):
    """Either ``azimuth``, or ``backsight`` + ``angle`` (clockwise from the backsight)."""

    station: XY
    distance: float = Field(gt=0, description="Grid distance")
    azimuth: float | None = None
    backsight: XY | None = None
    angle: float | None = None
    dz: float | None = None
    name: str | None = None


class PolarResult(_M):
    point: XY
    azimuth: float


# ------------------------------------------------------------------------ intersections


class IntersectionAnglesRequest(_M):
    """Forward intersection. ``angle_a`` is measured at A clockwise from B to P and
    ``angle_b`` at B clockwise from A to P (use 2π − angle for the other side)."""

    a: XY
    b: XY
    angle_a: float
    angle_b: float
    name: str | None = None


class IntersectionDistancesRequest(_M):
    a: XY
    r_a: float = Field(gt=0)
    b: XY
    r_b: float = Field(gt=0)


class IntersectionLinesRequest(_M):
    p1: XY
    p2: XY
    p3: XY
    p4: XY


class IntersectionResult(_M):
    solutions: list[XY] = Field(description="0, 1 or 2 points")
    message: str | None = Field(default=None, description="Why there is no unique solution")


# ---------------------------------------------------------------------------- resection


class ResectionObservation(_M):
    point: XY = Field(description="Known point (name recommended)")
    direction: float = Field(description="Horizontal circle reading to the point")
    distance: float | None = Field(default=None, description="Optional grid distance")


class ResectionRequest(_M):
    station_name: str | None = None
    observations: list[ResectionObservation] = Field(min_length=2)


class ResectionResidual(_M):
    name: str | None
    direction_residual: float = Field(description="rad")
    distance_residual: float | None = Field(default=None, description="m")


class ResectionResult(_M):
    station: XY
    orientation: float = Field(description="Orientation unknown ω (azimuth = direction + ω)")
    sigma0: float | None = Field(default=None, description="Only with redundancy")
    sx: float | None = None
    sy: float | None = None
    residuals: list[ResectionResidual]
    danger_circle: bool = Field(
        default=False, description="Station near the circle through the known points (weak)"
    )
    method: str


# --------------------------------------------------------------------------------- area


class AreaRequest(_M):
    points: list[XY] = Field(min_length=3, description="Polygon vertices in order")
    reduction: ReductionSettings | None = None


class AreaResult(_M):
    area: float = Field(description="Grid (projection) area, m² — used by the Hellenic Cadastre")
    perimeter: float
    orientation: Literal["clockwise", "counterclockwise"]
    centroid: XY
    scale_factor_mean: float | None = None
    area_ellipsoid: float | None = Field(default=None, description="area / k²")


# ------------------------------------------------------------------------ transformation


class CommonPoint(_M):
    name: str
    src: XY
    dst: XY
    use: bool = True


class TransformRequest(_M):
    method: Literal["helmert", "affine"] = "helmert"
    common: list[CommonPoint] = Field(min_length=2)
    points: list[XY] = Field(default_factory=list, description="Points to transform")


class TransformResidual(_M):
    name: str
    vx: float
    vy: float
    v: float
    used: bool


class TransformResult(_M):
    method: Literal["helmert", "affine"]
    params: dict[str, float] = Field(
        description="helmert: tx, ty, scale, rotation (rad), a, b; affine: a0, a1, a2, b0, b1, b2"
    )
    rms: float | None
    residuals: list[TransformResidual]
    points: list[XY]


# ------------------------------------------------------------------------------- offset


class OffsetRequest(_M):
    a: XY
    b: XY
    points: list[XY] = Field(min_length=1)


class OffsetRow(_M):
    name: str | None
    chainage: float = Field(description="Distance along A→B from A")
    offset: float = Field(description="Perpendicular distance; positive to the right of A→B")
    foot: XY


class OffsetResult(_M):
    line_length: float
    azimuth: float
    rows: list[OffsetRow]


# ----------------------------------------------------------------------------- levelling


class LevelingReading(_M):
    point: str
    reading: float = Field(description="Staff reading, m")
    kind: Literal["bs", "fs", "is"] = Field(description="backsight, foresight, intermediate")
    distance: float | None = Field(default=None, ge=0, description="Sight length, m")


class LevelingSetup(_M):
    readings: list[LevelingReading] = Field(min_length=2)


class Benchmark(_M):
    name: str
    h: float


class LevelingRequest(_M):
    benchmarks: list[Benchmark] = Field(min_length=1)
    setups: list[LevelingSetup] = Field(min_length=1)
    tolerance_base_mm: float = 0.0
    tolerance_mm_per_sqrt_km: float = 12.0
    distribute: Literal["distance", "setups"] = "distance"


class LevelingPoint(_M):
    name: str
    h: float
    h_unadjusted: float
    correction: float
    kind: Literal["benchmark", "turning", "intermediate"]


class LevelingRow(_M):
    setup: int
    backsight: str
    foresight: str
    dh: float
    length: float | None


class LevelingResult(_M):
    points: list[LevelingPoint]
    rows: list[LevelingRow]
    start: str
    end: str
    misclosure: float | None = Field(description="m; None for an open line")
    tolerance: float | None
    within_tolerance: bool | None
    length_km: float | None
    n_setups: int
    message: str | None = None
