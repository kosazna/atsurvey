"""Setting out (χάραξη) of design points and the as-staked check (έλεγχος χάραξης).

Batch setting out. From a station S oriented on a backsight B (or a known zero azimuth α₀)
each design point P gets (Anderson & Mikhail, *Surveying: Theory and Practice*, ch. 23):

* grid azimuth           α = atan2(ΔE, ΔN)
* direction to set       Hz = α − α(S→B)         (clockwise, backsight read as zero)
* grid distance          D = √(ΔE² + ΔN²)
* ground distance        HD = D / (k · R/(R + Hm + N))  (ΕΓΣΑ87 scale and height reduction,
  the same chain and settings as core/geodesy.py; ``core/cogo.stakeout`` does this part)
* vertical, with heights V = ΔZ − hi + ht − (1 − κ) · HD² / 2R   (curvature and refraction
  when enabled; the exact inverse of ``geodesy.height_difference``),
  zenith z = atan2(HD, V), slope distance S = √(HD² + V²).

The field order sorts the points by direction from the backsight (one sweep of the alidade),
nearer points first when two directions coincide.

As-staked check. Design and measured points are matched by name; Δ = measured − design.
Radial error √(ΔE² + ΔN²); with a reference line A→B also the along/across components
(across positive to the right). Statistics: max, RMS = √(Σr²/n), mean shift.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import cogo
from .cogo_models import XY, InverseRequest, StakeoutRequest
from .issues import IssueSink
from .models import Issue, ReductionSettings
from .units import wrap_2pi

MAX_POINTS = 10_000
Coord = Annotated[float, Field(allow_inf_nan=False, ge=-1e8, le=1e8)]
Height = Annotated[float, Field(allow_inf_nan=False, ge=-1e4, le=1e5)]
#: Duplicate names closer than this are the same point (no warning)
SAME_POINT_M = 1e-6


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SPoint(_M):
    name: Annotated[str, Field(max_length=64)] | None = None
    x: Coord
    y: Coord
    z: Height | None = None


# ---------------------------------------------------------------------- batch setting out


class SetoutRequest(_M):
    """Setting-out data from a station oriented on a backsight (or a known zero azimuth)."""

    station: SPoint
    backsight: SPoint | None = None
    backsight_azimuth: Annotated[float, Field(allow_inf_nan=False, ge=-100.0, le=100.0)] | None = (
        Field(default=None, description="Azimuth of the zero direction (rad), instead of B")
    )
    instrument_height: Annotated[float, Field(allow_inf_nan=False, ge=0, le=100)] = 0.0
    target_height: Annotated[float, Field(allow_inf_nan=False, ge=0, le=100)] = 0.0
    points: list[SPoint] = Field(min_length=1, max_length=MAX_POINTS)
    reduction: ReductionSettings | None = Field(
        default=None, description="ΕΓΣΑ87 scale/height reduction and curvature-refraction"
    )


class SetoutRow(_M):
    index: int = Field(description="Position in the input list")
    name: str | None
    de: float = Field(description="ΔE station → point, m")
    dn: float = Field(description="ΔN station → point, m")
    azimuth: float
    direction: float = Field(description="Horizontal direction to set, clockwise from B, rad")
    distance_grid: float
    distance: float = Field(description="Horizontal distance to set (ground when reduced), m")
    scale: float | None = Field(default=None, description="Grid / ground ratio applied")
    dz: float | None = Field(default=None, description="Height difference station → point, m")
    zenith: float | None = None
    slope_distance: float | None = None


class SetoutResult(_M):
    zero_azimuth: float = Field(description="Azimuth of the backsight direction (Hz = 0)")
    backsight_distance_grid: float | None = None
    backsight_distance: float | None = Field(
        default=None, description="Distance to the backsight to check in the field"
    )
    rows: list[SetoutRow] = Field(description="In input order")
    field_order: list[int] = Field(description="Indices of rows sorted by direction")
    issues: list[Issue] = Field(default_factory=list)


def _xy(p: SPoint) -> XY:
    return XY(x=p.x, y=p.y, z=p.z, name=p.name)


def _vertical(
    req: SetoutRequest, hd: float, dz: float
) -> tuple[float, float]:  # (zenith, slope distance)
    v = dz - req.instrument_height + req.target_height
    rs = req.reduction
    if rs is not None and rs.curvature_refraction:
        v -= (1.0 - rs.refraction_coefficient) * hd * hd / (2.0 * rs.earth_radius)
    return math.atan2(hd, v), math.hypot(hd, v)


def _duplicates(points: list[SPoint], sink: IssueSink) -> None:
    seen: dict[str, SPoint] = {}
    for p in points:
        if not p.name:
            continue
        q = seen.get(p.name)
        if q is not None and math.hypot(p.x - q.x, p.y - q.y) > SAME_POINT_M:
            sink.warning(
                "SETOUT_DUPLICATE_NAME",
                f"Point name {p.name} is used for different coordinates",
                point=p.name,
            )
        seen.setdefault(p.name, p)


def setout_points(req: SetoutRequest) -> SetoutResult:
    """Directions, distances and vertical data to set out a list of design points."""
    sink = IssueSink()
    _duplicates(req.points, sink)
    base = cogo.stakeout(
        StakeoutRequest(
            station=_xy(req.station),
            backsight=_xy(req.backsight) if req.backsight is not None else None,
            backsight_azimuth=req.backsight_azimuth,
            points=[_xy(p) for p in req.points],
            reduction=req.reduction,
        )
    )
    st = req.station
    if st.z is None and any(p.z is not None for p in req.points):
        sink.info(
            "SETOUT_NO_STATION_HEIGHT",
            "The station has no height: heights are not set out",
            station=st.name or "",
        )
    rows: list[SetoutRow] = []
    for i, (p, b) in enumerate(zip(req.points, base.rows, strict=True)):
        hd = b.distance_ground if b.distance_ground is not None else b.distance
        dz = zen = sd = None
        if st.z is not None and p.z is not None:
            dz = p.z - st.z
            zen, sd = _vertical(req, hd, dz)
        rows.append(
            SetoutRow(
                index=i,
                name=p.name,
                de=p.x - st.x,
                dn=p.y - st.y,
                azimuth=b.azimuth,
                direction=b.angle,
                distance_grid=b.distance,
                distance=hd,
                scale=b.distance / b.distance_ground if b.distance_ground else None,
                dz=dz,
                zenith=zen,
                slope_distance=sd,
            )
        )
    zero = wrap_2pi(rows[0].azimuth - rows[0].direction)
    bs_grid = bs_ground = None
    if req.backsight is not None:
        inv = cogo.inverse(InverseRequest(a=_xy(st), b=_xy(req.backsight), reduction=req.reduction))
        bs_grid = inv.distance
        bs_ground = inv.distance_ground if inv.distance_ground is not None else inv.distance
    order = sorted(range(len(rows)), key=lambda k: (rows[k].direction, rows[k].distance))
    return SetoutResult(
        zero_azimuth=zero,
        backsight_distance_grid=bs_grid,
        backsight_distance=bs_ground,
        rows=rows,
        field_order=order,
        issues=sink.items,
    )


# ------------------------------------------------------------------------- as-staked check


class ReferenceLine(_M):
    a: SPoint
    b: SPoint


class CheckRequest(_M):
    design: list[SPoint] = Field(min_length=1, max_length=MAX_POINTS)
    measured: list[SPoint] = Field(min_length=1, max_length=MAX_POINTS)
    tolerance_xy: Annotated[float, Field(allow_inf_nan=False, gt=0, le=100)] = 0.02
    tolerance_z: Annotated[float, Field(allow_inf_nan=False, gt=0, le=100)] | None = 0.02
    reference_line: ReferenceLine | None = Field(
        default=None, description="Gives along/across components (e.g. a kerb or building line)"
    )


class CheckRow(_M):
    name: str
    design_x: float
    design_y: float
    design_z: float | None
    x: float
    y: float
    z: float | None
    dx: float = Field(description="Measured − design, Easting")
    dy: float = Field(description="Measured − design, Northing")
    dz: float | None = None
    radial: float
    along: float | None = Field(default=None, description="Along the reference line A→B")
    across: float | None = Field(default=None, description="Right of the reference line")
    ok_xy: bool
    ok_z: bool | None = None
    ok: bool


class CheckSummary(_M):
    matched: int
    out_of_tolerance: int
    out_xy: int
    out_z: int
    max_radial: float
    rms_radial: float
    mean_dx: float
    mean_dy: float
    max_abs_dz: float | None = None
    rms_dz: float | None = None
    mean_dz: float | None = None


class CheckResult(_M):
    rows: list[CheckRow]
    summary: CheckSummary | None = Field(description="None when no point matched")
    unmatched_design: list[str]
    unmatched_measured: list[str]
    issues: list[Issue] = Field(default_factory=list)


def _by_name(
    points: list[SPoint], role: Literal["design", "measured"], sink: IssueSink
) -> dict[str, SPoint]:
    """Name → point; the last measurement of a re-staked point wins."""
    out: dict[str, SPoint] = {}
    unnamed = 0
    for p in points:
        name = (p.name or "").strip()
        if not name:
            unnamed += 1
            continue
        if name in out and role == "design":
            sink.warning(
                "SETOUT_DUPLICATE_NAME",
                f"Point name {name} is used twice in the design; the first is used",
                point=name,
            )
            continue
        if name in out:
            sink.info(
                "SETOUT_RESTAKED",
                f"Point {name} was measured more than once; the last measurement is used",
                point=name,
            )
        out[name] = p
    if unnamed:
        sink.warning(
            "SETOUT_UNNAMED",
            f"{unnamed} points without a name were ignored",
            count=unnamed,
            role=role,
        )
    return out


def _line_axes(line: ReferenceLine | None) -> tuple[float, float] | None:
    if line is None:
        return None
    dx, dy = line.b.x - line.a.x, line.b.y - line.a.y
    length = math.hypot(dx, dy)
    if length < 1e-6:
        raise ValueError("The reference line points coincide")
    return dx / length, dy / length


def check_staked(req: CheckRequest) -> CheckResult:
    """Compare measured (as-staked) points against the design, matched by name."""
    sink = IssueSink()
    design = _by_name(req.design, "design", sink)
    measured = _by_name(req.measured, "measured", sink)
    axes = _line_axes(req.reference_line)
    rows: list[CheckRow] = []
    for name, d in design.items():
        m = measured.get(name)
        if m is None:
            continue
        dx, dy = m.x - d.x, m.y - d.y
        dz = m.z - d.z if m.z is not None and d.z is not None else None
        radial = math.hypot(dx, dy)
        along = across = None
        if axes is not None:
            ux, uy = axes
            along, across = dx * ux + dy * uy, dx * uy - dy * ux
        ok_xy = radial <= req.tolerance_xy
        ok_z = None if dz is None or req.tolerance_z is None else abs(dz) <= req.tolerance_z
        rows.append(
            CheckRow(
                name=name,
                design_x=d.x,
                design_y=d.y,
                design_z=d.z,
                x=m.x,
                y=m.y,
                z=m.z,
                dx=dx,
                dy=dy,
                dz=dz,
                radial=radial,
                along=along,
                across=across,
                ok_xy=ok_xy,
                ok_z=ok_z,
                ok=ok_xy and ok_z is not False,
            )
        )
    return CheckResult(
        rows=rows,
        summary=_summary(rows),
        unmatched_design=[n for n in design if n not in measured],
        unmatched_measured=[n for n in measured if n not in design],
        issues=sink.items,
    )


def _summary(rows: list[CheckRow]) -> CheckSummary | None:
    n = len(rows)
    if n == 0:
        return None
    dzs = [r.dz for r in rows if r.dz is not None]
    return CheckSummary(
        matched=n,
        out_of_tolerance=sum(not r.ok for r in rows),
        out_xy=sum(not r.ok_xy for r in rows),
        out_z=sum(r.ok_z is False for r in rows),
        max_radial=max(r.radial for r in rows),
        rms_radial=math.sqrt(math.fsum(r.radial**2 for r in rows) / n),
        mean_dx=math.fsum(r.dx for r in rows) / n,
        mean_dy=math.fsum(r.dy for r in rows) / n,
        max_abs_dz=max(abs(v) for v in dzs) if dzs else None,
        rms_dz=math.sqrt(math.fsum(v * v for v in dzs) / len(dzs)) if dzs else None,
        mean_dz=math.fsum(dzs) / len(dzs) if dzs else None,
    )
