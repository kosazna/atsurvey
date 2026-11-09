"""Engine input / output models.

Conventions
-----------
* Coordinates: ``x`` = Easting, ``y`` = Northing, ``z`` = orthometric height (metres).
* Angles: radians. ``hz`` is the horizontal **circle reading** (direction), not an
  angle — the engine forms angles from directions, so the backsight does not need
  to be set to zero. ``v`` is the **zenith** angle (0 = up); readings with v > π
  are treated as face II and reduced automatically.
* Azimuths are grid bearings measured clockwise from grid north.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PointKind = Literal["control", "traverse", "detail"]
Severity = Literal["error", "warning", "info"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- inputs


class ControlPoint(_Model):
    name: str = Field(min_length=1)
    x: float
    y: float
    z: float | None = None
    code: str | None = None


class Observation(_Model):
    target: str = Field(min_length=1)
    hz: float = Field(description="Horizontal circle reading, radians")
    v: float | None = Field(default=None, description="Zenith angle, radians")
    sd: float | None = Field(default=None, ge=0, description="Slope distance, metres")
    target_height: float = 0.0
    code: str | None = None
    excluded: bool = False
    id: str | None = None


class Setup(_Model):
    station: str = Field(min_length=1)
    instrument_height: float = 0.0
    observations: list[Observation] = Field(default_factory=list)
    backsight: str | None = Field(default=None, description="Informational only")
    id: str | None = None


TraverseKind = Literal["auto", "open", "link", "closed"]


class TraverseSpec(_Model):
    route: list[str] = Field(
        description=(
            "Ordered points. route[0] is the start orientation point, route[1] the start "
            "station. For a link traverse with closing orientation the last two entries "
            "are the end station and end orientation point."
        )
    )
    kind: TraverseKind = "auto"
    end_orientation: bool | None = Field(
        default=None,
        description="Close on azimuth at the end. None = automatic (if both end points known).",
    )
    name: str | None = None
    id: str | None = None
    enabled: bool = True


ScaleMode = Literal["leg_simpson", "leg_mean", "traverse_mean", "none", "fixed"]
ElevationMode = Literal["leg", "traverse"]


class ReductionSettings(_Model):
    scale_mode: ScaleMode = Field(
        default="leg_simpson",
        description=(
            "EGSA87 grid scale factor: per leg (Simpson's rule over the leg), per leg at the "
            "mid-point, one factor for the whole traverse (legacy/Excel style), none (k=1, "
            "local grid) or a fixed value."
        ),
    )
    fixed_scale: float = 1.0
    elevation_reduction: bool = True
    elevation_mode: ElevationMode = "leg"
    geoid_undulation: float = Field(
        default=0.0, description="N (m) added to heights for the reduction to the ellipsoid"
    )
    default_elevation: float = Field(
        default=0.0, description="Height used for reductions when no heights are available"
    )
    curvature_refraction: bool = True
    refraction_coefficient: float = 0.13
    earth_radius: float = 6371000.0


class Tolerances(_Model):
    """Misclosure limits. Defaults are generic placeholders — set them to your spec."""

    angular_base_cc: float = 0.0
    angular_per_sqrt_n_cc: float = 40.0
    linear_base_m: float = 0.02
    linear_per_sqrt_km_m: float = 0.05
    min_relative_precision: float = Field(
        default=5000.0, description="Fail if L / w < this (1:N). 0 disables."
    )
    height_base_m: float = 0.02
    height_per_sqrt_km_m: float = 0.05
    round_spread_cc: float = 50.0
    leg_distance_fb_m: float = 0.02
    leg_height_fb_m: float = 0.03
    orientation_spread_cc: float = 60.0
    detail_duplicate_m: float = 0.03
    check_shot_m: float = 0.03


class ComputeSettings(_Model):
    reduction: ReductionSettings = Field(default_factory=ReductionSettings)
    tolerances: Tolerances = Field(default_factory=Tolerances)
    compute_detail: bool = True


class ProjectInput(_Model):
    control_points: list[ControlPoint] = Field(default_factory=list)
    setups: list[Setup] = Field(default_factory=list)
    traverses: list[TraverseSpec] = Field(default_factory=list)
    settings: ComputeSettings = Field(default_factory=ComputeSettings)


# -------------------------------------------------------------------------- outputs


class Issue(_Model):
    severity: Severity
    code: str
    message: str
    params: dict[str, Any] = Field(default_factory=dict)
    traverse: str | None = None
    setup: str | None = None


class ResultPoint(_Model):
    name: str
    x: float
    y: float
    z: float | None
    kind: PointKind
    code: str | None = None
    source: str | None = Field(default=None, description="Traverse name or station")
    n: int = Field(default=1, description="Number of determinations averaged")


class TraverseStation(_Model):
    """One row of a traverse computation sheet (a station where an angle is turned)."""

    station: str
    backsight: str
    foresight: str
    angle_measured: float
    angle_correction: float
    angle_corrected: float
    azimuth: float
    x: float
    y: float
    z: float | None
    known: bool


class TraverseLeg(_Model):
    frm: str
    to: str
    hd_measured: float
    n_measurements: int
    distance_fb_diff: float | None
    reduction_scale: float
    elevation_factor: float
    distance_grid: float
    azimuth: float
    dx: float
    dy: float
    corr_x: float
    corr_y: float
    dh: float | None
    height_fb_diff: float | None
    corr_h: float


class TraverseResult(_Model):
    id: str | None
    name: str
    kind: Literal["open", "link", "closed"]
    end_orientation: bool
    route: list[str]
    status: Literal["ok", "warning", "failed"]
    n_angles: int
    length: float
    angular_misclosure: float | None
    angular_tolerance: float | None
    wx: float | None
    wy: float | None
    linear_misclosure: float | None
    linear_tolerance: float | None
    relative_precision: float | None
    wz: float | None
    height_tolerance: float | None
    within_tolerance: bool | None
    stations: list[TraverseStation]
    legs: list[TraverseLeg]
    new_points: list[str]


class DetailShot(_Model):
    station: str
    target: str
    direction: float
    zenith: float | None
    sd: float | None
    hd: float | None
    distance_grid: float | None
    azimuth: float
    x: float | None
    y: float | None
    z: float | None
    code: str | None
    check: bool = Field(default=False, description="Target is a known point (check shot)")
    residual: float | None = None


class SetupOrientation(_Model):
    station: str
    setup: str | None
    orientation: float | None
    references: list[str]
    spread: float | None


class Summary(_Model):
    n_control: int
    n_traverse_points: int
    n_detail_points: int
    n_traverses: int
    n_traverses_ok: int
    n_errors: int
    n_warnings: int
    extent: tuple[float, float, float, float] | None


class ProjectResult(_Model):
    engine_version: str
    input_hash: str
    points: list[ResultPoint]
    traverses: list[TraverseResult]
    detail: list[DetailShot]
    orientations: list[SetupOrientation]
    issues: list[Issue]
    summary: Summary
