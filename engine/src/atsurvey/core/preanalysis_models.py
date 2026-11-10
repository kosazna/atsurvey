"""Contracts of the network pre-analysis (προανάλυση): ``POST /v1/analysis/preanalysis``.

Coordinates in metres (x = Easting, y = Northing). Angles (σ of directions, MDB of
directions, azimuth σ, ellipse orientation) in radians; the UI converts to cc/mgon.
Implementation: ``core/preanalysis.py``; documentation: docs/analysis.md.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import ErrorEllipse, Issue

MAX_POINTS = 500
MAX_OBSERVATIONS = 5000
MAX_PAIRS = 1000
COORD_LIMIT = 1e8  # |x|, |y| in metres

Name = Annotated[str, Field(min_length=1, max_length=64)]

PlannedKind = Literal["direction", "distance", "height"]
ObservationStatus = Literal["ok", "weak", "uncontrolled", "excluded"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PlannedPoint(_M):
    name: Name
    x: float = Field(ge=-COORD_LIMIT, le=COORD_LIMIT)
    y: float = Field(ge=-COORD_LIMIT, le=COORD_LIMIT)
    fixed: bool = Field(default=False, description="Control point (datum, also for heights)")


class PlannedObservation(_M):
    kind: PlannedKind
    station: Name
    target: Name
    setup: str | None = Field(
        default=None,
        max_length=64,
        description="Orientation group of directions; default: one setup per station",
    )


class InstrumentSpec(_M):
    """A priori precision. Direction σ is for the mean of the planned sets of readings."""

    sigma_direction_cc: float = Field(default=10.0, gt=0, le=1000)
    sigma_distance_mm: float = Field(default=2.0, gt=0, le=1000)
    sigma_distance_ppm: float = Field(default=2.0, ge=0, le=1000)
    sigma_centering_instrument_mm: float = Field(default=1.0, ge=0, le=100)
    sigma_centering_target_mm: float = Field(default=1.0, ge=0, le=100)
    sigma_height_mm: float = Field(default=5.0, gt=0, le=1000, description="σ of Δh at 1 km")


class PreanalysisRequest(_M):
    points: list[PlannedPoint] = Field(min_length=2, max_length=MAX_POINTS)
    observations: list[PlannedObservation] = Field(min_length=1, max_length=MAX_OBSERVATIONS)
    instrument: InstrumentSpec = Field(default_factory=InstrumentSpec)
    relative_pairs: list[tuple[str, str]] = Field(default_factory=list, max_length=MAX_PAIRS)
    alpha0: float = Field(default=0.001, ge=1e-6, le=0.2, description="Significance of the w-test")
    beta0: float = Field(default=0.80, ge=0.5, le=0.999, description="Power of the w-test")


class PointPrecision(_M):
    name: str
    sx: float | None = Field(default=None, description="σ of X (σ0 = 1), m")
    sy: float | None = None
    spos: float | None = Field(default=None, description="Helmert point error √(σx² + σy²), m")
    ellipse: ErrorEllipse | None = Field(default=None, description="Standard (1σ) ellipse")
    a95: float | None = Field(default=None, description="Semi-major axis of the 95 % ellipse, m")
    b95: float | None = None
    sz: float | None = Field(default=None, description="σ of the height, m")


class RelativePrecision(_M):
    frm: str
    to: str
    distance: float
    s_distance: float = Field(description="σ of the distance between the two points, m")
    s_azimuth: float = Field(description="σ of the azimuth, rad")
    s_transverse: float = Field(description="Transverse σ = D·σ_azimuth, m")
    ellipse: ErrorEllipse
    a95: float
    b95: float


class ObservationReliability(_M):
    kind: PlannedKind
    station: str
    target: str
    sigma: float | None = Field(description="A priori σ (rad for directions, m otherwise)")
    redundancy: float = Field(description="Redundancy number r_i in [0, 1]")
    mdb: float | None = Field(
        description="Minimal detectable bias ∇_i = δ0·σ_i/√r_i (rad or m); None if uncontrolled"
    )
    external: float | None = Field(
        description="Baarda's external reliability factor δ̄_i = δ0·√((1 − r_i)/r_i)"
    )
    max_shift: float | None = Field(
        description="Largest point displacement caused by an undetected ∇_i, m"
    )
    max_shift_point: str | None
    status: ObservationStatus


class PreanalysisResult(_M):
    n_observations: int
    n_unknowns: int
    dof: int
    alpha0: float
    beta0: float
    delta0: float = Field(description="Non-centrality δ0 = N⁻¹(1 − α0/2) + N⁻¹(β0)")
    lambda0: float = Field(description="λ0 = δ0²")
    k95: float = Field(description="√χ²₂(0.95): 1σ ellipse → 95 % ellipse")
    points: list[PointPrecision]
    relative: list[RelativePrecision]
    observations: list[ObservationReliability] = Field(description="Same order as the request")
    excluded_points: list[str]
    issues: list[Issue]
