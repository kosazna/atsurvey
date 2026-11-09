"""Traverse computation (compass / Bowditch rule).

Route convention (same as the Greek computation sheet)::

    route = [A, B, P1, P2, ..., E, F]

* ``A`` — start orientation point (known), ``B`` — start station (known).
* Angles are turned at every station from ``B`` to the last station.
* **Link with closing azimuth**: ``E`` (end station) and ``F`` (end orientation) known.
* **Link on position only**: the last point is a known station, no closing azimuth.
* **Closed**: the route returns to ``B`` (``[A, B, ..., B, A]`` with closing azimuth or
  ``[A, B, ..., B]`` on position only).
* **Open (hanging)**: the last point is unknown — no check is possible.

The angular misclosure is distributed equally over all angles; the linear and height
misclosures are distributed proportionally to the leg length.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from .geodesy import (
    egsa87_point_scale,
    elevation_factor,
    grid_azimuth,
    grid_distance,
    scale_for_line,
)
from .issues import IssueSink
from .models import (
    ErrorEllipse,
    ReductionSettings,
    Tolerances,
    TraverseLeg,
    TraverseResult,
    TraverseSpec,
    TraverseStation,
)
from .reduce import LegMeasurement, ObservationIndex
from .units import CC_TO_RAD, rad_to_cc, wrap_2pi, wrap_pi


@dataclass(slots=True)
class KnownPoint:
    name: str
    x: float
    y: float
    z: float | None
    kind: str
    code: str | None = None
    source: str | None = None
    # filled by the least-squares adjustment
    sx: float | None = None
    sy: float | None = None
    sz: float | None = None
    ellipse: ErrorEllipse | None = None


@dataclass(slots=True)
class TraversePlan:
    spec: TraverseSpec
    name: str
    route: list[str]
    end_orientation: bool
    position_closure: bool
    kind: str
    angle_stations: list[int]  # indices into route
    leg_points: list[str]


def traverse_name(spec: TraverseSpec) -> str:
    return spec.name or "-".join(spec.route)


def plan_traverse(
    spec: TraverseSpec, known: dict[str, KnownPoint], sink: IssueSink | None = None
) -> TraversePlan | None:
    """Resolve the traverse geometry. Returns None if the start is not (yet) known."""
    route = [p.strip() for p in spec.route if p and p.strip()]
    name = traverse_name(spec)
    if len(route) < 3:
        if sink:
            sink.error(
                "TRAVERSE_ROUTE_TOO_SHORT",
                f"Traverse {name} needs at least 3 points (orientation, station, next point)",
                traverse=spec.id or name,
                route=route,
            )
        return None

    def both_known(a: str, b: str) -> bool:
        return a in known and b in known

    if not both_known(route[0], route[1]):
        if both_known(route[-1], route[-2]) and spec.kind != "open":
            route = list(reversed(route))
        else:
            return None

    if spec.kind == "open":
        end_orientation = False
    elif spec.end_orientation is not None:
        end_orientation = spec.end_orientation and len(route) >= 4
    else:
        end_orientation = len(route) >= 4 and both_known(route[-1], route[-2])
    if end_orientation and not both_known(route[-1], route[-2]):
        end_orientation = False

    # with a closing azimuth the last point is only sighted; otherwise it is the end station
    leg_points = route[1:-1] if end_orientation else route[1:]
    end_station = leg_points[-1]
    position_closure = spec.kind != "open" and end_station in known and len(leg_points) >= 2
    if position_closure and end_station == route[1]:
        kind = "closed"
    elif position_closure:
        kind = "link"
    else:
        kind = "open"
    # an angle is turned at every route point except the first and the last
    angle_stations = list(range(1, len(route) - 1))
    return TraversePlan(
        spec=spec,
        name=name,
        route=route,
        end_orientation=end_orientation,
        position_closure=position_closure,
        kind=kind,
        angle_stations=angle_stations,
        leg_points=leg_points,
    )


def _failed(plan: TraversePlan) -> TraverseResult:
    return TraverseResult(
        id=plan.spec.id,
        name=plan.name,
        kind=plan.kind,  # type: ignore[arg-type]
        end_orientation=plan.end_orientation,
        route=plan.route,
        status="failed",
        n_angles=len(plan.angle_stations),
        length=0.0,
        angular_misclosure=None,
        angular_tolerance=None,
        wx=None,
        wy=None,
        linear_misclosure=None,
        linear_tolerance=None,
        relative_precision=None,
        wz=None,
        height_tolerance=None,
        within_tolerance=None,
        stations=[],
        legs=[],
        new_points=[],
    )


def compute_traverse(
    plan: TraversePlan,
    index: ObservationIndex,
    known: dict[str, KnownPoint],
    rs: ReductionSettings,
    tol: Tolerances,
    sink: IssueSink,
) -> tuple[TraverseResult, list[KnownPoint]]:
    route = plan.route
    ref = plan.spec.id or plan.name

    # ---- measurements ---------------------------------------------------------------
    angles: list[float] = []
    missing_angles: list[str] = []
    for i in plan.angle_stations:
        a = index.angle(route[i], route[i - 1], route[i + 1])
        if a is None:
            missing_angles.append(f"{route[i - 1]}-{route[i]}-{route[i + 1]}")
        else:
            angles.append(a)
    legs_meas: list[LegMeasurement] = []
    missing_legs: list[str] = []
    lp = plan.leg_points
    for a, b in itertools.pairwise(lp):
        m = index.leg(a, b)
        if m is None:
            missing_legs.append(f"{a}-{b}")
        else:
            legs_meas.append(m)
    for ma in missing_angles:
        st = ma.split("-")[1]
        sink.error(
            "TRAVERSE_MISSING_ANGLE",
            f"Traverse {plan.name}: no observation of angle {ma} (setup at {st} observing both)",
            traverse=ref,
            angle=ma,
            station=st,
        )
    for ml in missing_legs:
        sink.error(
            "TRAVERSE_MISSING_DISTANCE",
            f"Traverse {plan.name}: no distance measured on leg {ml}",
            traverse=ref,
            leg=ml,
        )
    if missing_angles or missing_legs:
        return _failed(plan), []

    for (a, b), m in zip(itertools.pairwise(lp), legs_meas, strict=True):
        if m.fb_diff is not None and abs(m.fb_diff) > tol.leg_distance_fb_m:
            sink.warning(
                "LEG_DISTANCE_FB",
                f"Leg {a}-{b}: forward/backward distances differ by {m.fb_diff * 1000:.1f} mm",
                traverse=ref,
                leg=f"{a}-{b}",
                diff_mm=round(m.fb_diff * 1000, 1),
            )
        if m.dh_fb_diff is not None and abs(m.dh_fb_diff) > tol.leg_height_fb_m:
            sink.warning(
                "LEG_HEIGHT_FB",
                f"Leg {a}-{b}: forward/backward height differences differ by "
                f"{m.dh_fb_diff * 1000:.1f} mm",
                traverse=ref,
                leg=f"{a}-{b}",
                diff_mm=round(m.dh_fb_diff * 1000, 1),
            )

    start = known[route[1]]
    orient = known[route[0]]
    n = len(angles)
    n_legs = len(legs_meas)

    # ---- angular closure ------------------------------------------------------------
    az0 = grid_azimuth(orient.x, orient.y, start.x, start.y)

    def chain(corr: float) -> list[float]:
        out = []
        az = az0
        for beta in angles:
            az = wrap_2pi(az + beta + corr + math.pi)
            out.append(az)
        return out

    raw_az = chain(0.0)
    angular_w: float | None = None
    corr = 0.0
    if plan.end_orientation:
        end_st = known[route[-2]]
        end_or = known[route[-1]]
        az_known = grid_azimuth(end_st.x, end_st.y, end_or.x, end_or.y)
        angular_w = wrap_pi(az_known - raw_az[-1])
        corr = angular_w / n
    az = chain(corr)
    leg_az = az[:n_legs]

    # ---- heights --------------------------------------------------------------------
    end_name = lp[-1]
    end_known = known.get(end_name) if plan.position_closure else None
    heights_ok = start.z is not None and all(m.dh is not None for m in legs_meas)
    prov_z: list[float] | None = None
    if heights_ok:
        prov_z = [start.z]  # type: ignore[list-item]
        for m in legs_meas:
            prov_z.append(prov_z[-1] + m.dh)  # type: ignore[operator]
    else:
        sink.info(
            "TRAVERSE_NO_HEIGHTS",
            f"Traverse {plan.name}: heights not computed (missing start height or zenith angles)",
            traverse=ref,
        )

    def traverse_mean_height() -> float:
        zs = [p.z for p in (start, end_known) if p is not None and p.z is not None]
        if zs:
            return math.fsum(zs) / len(zs)
        return rs.default_elevation

    t_mean_h = traverse_mean_height()
    t_end_e = end_known.x if end_known is not None else orient.x
    traverse_k = egsa87_point_scale((start.x + t_end_e) / 2.0)

    def leg_heights() -> list[float]:
        if rs.elevation_mode == "leg" and prov_z is not None:
            return [(prov_z[j] + prov_z[j + 1]) / 2.0 for j in range(n_legs)]
        return [t_mean_h] * n_legs

    hm = leg_heights()

    def solve(k_list: list[float]):
        efs = [elevation_factor(rs, h) for h in hm]
        dist = [m.hd * ef * k for m, ef, k in zip(legs_meas, efs, k_list, strict=True)]
        dxs = [d * math.sin(a) for d, a in zip(dist, leg_az, strict=True)]
        dys = [d * math.cos(a) for d, a in zip(dist, leg_az, strict=True)]
        length = math.fsum(dist)
        wx = wy = None
        cx = [0.0] * n_legs
        cy = [0.0] * n_legs
        if end_known is not None:
            wx = end_known.x - (start.x + math.fsum(dxs))
            wy = end_known.y - (start.y + math.fsum(dys))
            if length > 0:
                cx = [wx * d / length for d in dist]
                cy = [wy * d / length for d in dist]
        xs = [start.x]
        ys = [start.y]
        for j in range(n_legs):
            xs.append(xs[-1] + dxs[j] + cx[j])
            ys.append(ys[-1] + dys[j] + cy[j])
        return dist, efs, dxs, dys, cx, cy, xs, ys, length, wx, wy

    if rs.scale_mode in ("leg_simpson", "leg_mean"):
        # pass 1 with a single factor for provisional eastings, pass 2 per leg
        k1 = [traverse_k] * n_legs
        *_, xs1, _ys1, _l1, _wx1, _wy1 = solve(k1)
        k_list = [scale_for_line(rs, xs1[j], xs1[j + 1], traverse_k) for j in range(n_legs)]
    else:
        k_list = [scale_for_line(rs, start.x, start.x, traverse_k)] * n_legs
    dist, efs, dxs, dys, cx, cy, xs, ys, length, wx, wy = solve(k_list)

    # heights with closure
    zs: list[float | None] = [None] * (n_legs + 1)
    wz: float | None = None
    cz = [0.0] * n_legs
    if prov_z is not None:
        if end_known is not None and end_known.z is not None:
            wz = end_known.z - prov_z[-1]
            if length > 0:
                cz = [wz * d / length for d in dist]
        z = start.z
        zs[0] = z
        for j, m in enumerate(legs_meas):
            z = z + m.dh + cz[j]  # type: ignore[operator]
            zs[j + 1] = z

    # ---- tolerances -----------------------------------------------------------------
    within: bool | None = None
    angular_tol = linear_tol = height_tol = None
    w_lin = rel = None
    checks: list[bool] = []
    if angular_w is not None:
        angular_tol = (tol.angular_base_cc + tol.angular_per_sqrt_n_cc * math.sqrt(n)) * CC_TO_RAD
        ok = abs(angular_w) <= angular_tol
        checks.append(ok)
        if not ok:
            sink.warning(
                "TRAVERSE_ANGULAR_TOLERANCE",
                f"Traverse {plan.name}: angular misclosure {rad_to_cc(angular_w):+.0f} cc exceeds "
                f"{rad_to_cc(angular_tol):.0f} cc",
                traverse=ref,
                misclosure_cc=round(rad_to_cc(angular_w), 1),
                tolerance_cc=round(rad_to_cc(angular_tol), 1),
            )
    if wx is not None and wy is not None:
        w_lin = math.hypot(wx, wy)
        linear_tol = tol.linear_base_m + tol.linear_per_sqrt_km_m * math.sqrt(length / 1000.0)
        ok = w_lin <= linear_tol
        checks.append(ok)
        if not ok:
            sink.warning(
                "TRAVERSE_LINEAR_TOLERANCE",
                f"Traverse {plan.name}: linear misclosure {w_lin:.3f} m exceeds {linear_tol:.3f} m",
                traverse=ref,
                misclosure_m=round(w_lin, 4),
                tolerance_m=round(linear_tol, 4),
            )
        rel = length / w_lin if w_lin > 0 else None
        if tol.min_relative_precision > 0 and rel is not None and rel < tol.min_relative_precision:
            checks.append(False)
            sink.warning(
                "TRAVERSE_RELATIVE_PRECISION",
                f"Traverse {plan.name}: relative precision 1:{rel:.0f} is worse than "
                f"1:{tol.min_relative_precision:.0f}",
                traverse=ref,
                relative=round(rel),
                minimum=round(tol.min_relative_precision),
            )
    if wz is not None:
        height_tol = tol.height_base_m + tol.height_per_sqrt_km_m * math.sqrt(length / 1000.0)
        ok = abs(wz) <= height_tol
        checks.append(ok)
        if not ok:
            sink.warning(
                "TRAVERSE_HEIGHT_TOLERANCE",
                f"Traverse {plan.name}: height misclosure {wz:+.3f} m exceeds {height_tol:.3f} m",
                traverse=ref,
                misclosure_m=round(wz, 4),
                tolerance_m=round(height_tol, 4),
            )
    if checks:
        within = all(checks)
    elif plan.kind == "open":
        sink.info(
            "TRAVERSE_OPEN",
            f"Traverse {plan.name} is open (hanging): coordinates are not checked",
            traverse=ref,
        )

    # ---- assemble -------------------------------------------------------------------
    coords = {p: (xs[j], ys[j], zs[j]) for j, p in enumerate(lp)}
    stations: list[TraverseStation] = []
    for k, i in enumerate(plan.angle_stations):
        st = route[i]
        if st in coords:
            x, y, z = coords[st]
        else:
            kp = known[st]
            x, y, z = kp.x, kp.y, kp.z
        stations.append(
            TraverseStation(
                station=st,
                backsight=route[i - 1],
                foresight=route[i + 1],
                angle_measured=angles[k],
                angle_correction=corr,
                angle_corrected=wrap_2pi(angles[k] + corr),
                azimuth=az[k],
                x=x,
                y=y,
                z=z,
                known=st in known,
            )
        )
    legs: list[TraverseLeg] = []
    for j, m in enumerate(legs_meas):
        legs.append(
            TraverseLeg(
                frm=lp[j],
                to=lp[j + 1],
                hd_measured=m.hd,
                n_measurements=m.n,
                distance_fb_diff=m.fb_diff,
                reduction_scale=k_list[j],
                elevation_factor=efs[j],
                distance_grid=dist[j],
                azimuth=leg_az[j],
                dx=dxs[j],
                dy=dys[j],
                corr_x=cx[j],
                corr_y=cy[j],
                dh=m.dh,
                height_fb_diff=m.dh_fb_diff,
                corr_h=cz[j],
            )
        )

    new_points: list[KnownPoint] = []
    end_idx = len(lp) - 1 if plan.position_closure else len(lp)
    for j in range(1, end_idx):
        p = lp[j]
        x, y, z = coords[p]
        if p in known:
            kp = known[p]
            d = grid_distance(kp.x, kp.y, x, y)
            sink.warning(
                "TRAVERSE_KNOWN_POINT_MID",
                f"Traverse {plan.name} passes through known point {p} (computed position differs "
                f"by {d * 1000:.0f} mm); the known coordinates are kept. Consider splitting the "
                f"traverse at {p}.",
                traverse=ref,
                point=p,
                diff_mm=round(d * 1000, 1),
            )
            continue
        new_points.append(KnownPoint(name=p, x=x, y=y, z=z, kind="traverse", source=plan.name))

    status = "ok"
    if within is False:
        status = "warning"
    result = TraverseResult(
        id=plan.spec.id,
        name=plan.name,
        kind=plan.kind,  # type: ignore[arg-type]
        end_orientation=plan.end_orientation,
        route=route,
        status=status,  # type: ignore[arg-type]
        n_angles=n,
        length=length,
        angular_misclosure=angular_w,
        angular_tolerance=angular_tol,
        wx=wx,
        wy=wy,
        linear_misclosure=w_lin,
        linear_tolerance=linear_tol,
        relative_precision=rel,
        wz=wz,
        height_tolerance=height_tol,
        within_tolerance=within,
        stations=stations,
        legs=legs,
        new_points=[p.name for p in new_points],
    )
    return result, new_points
