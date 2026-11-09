"""Detail points (radiation / polar shots) from oriented setups.

Each setup at a known station is oriented on **all** known targets it observes (mean
orientation unknown ω, with the spread reported). Unknown targets become detail points;
known targets that also have a distance are reported as check shots. Setups whose
station only becomes known through radiation are processed in a following pass.
"""

from __future__ import annotations

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
from .models import DetailShot, ReductionSettings, SetupOrientation, Tolerances
from .reduce import ReducedSetup, ReducedTarget
from .traverse import KnownPoint
from .units import circular_mean, circular_spread, rad_to_cc, wrap_2pi, wrap_pi


@dataclass(slots=True)
class _Candidate:
    name: str
    xs: list[float]
    ys: list[float]
    zs: list[float]
    code: str | None
    stations: list[str]


def _polar(
    st: KnownPoint, t: ReducedTarget, az: float, rs: ReductionSettings
) -> tuple[float, float, float | None, float]:
    assert t.hd is not None
    zt = st.z + t.dh if st.z is not None and t.dh is not None else None
    if st.z is not None and zt is not None:
        hm = (st.z + zt) / 2.0
    elif st.z is not None:
        hm = st.z
    else:
        hm = rs.default_elevation
    e_prov = st.x + t.hd * math.sin(az)
    k = scale_for_line(rs, st.x, e_prov, egsa87_point_scale(st.x))
    d = t.hd * elevation_factor(rs, hm) * k
    return st.x + d * math.sin(az), st.y + d * math.cos(az), zt, d


def compute_detail(
    setups: list[ReducedSetup],
    known: dict[str, KnownPoint],
    reserved: set[str],
    rs: ReductionSettings,
    tol: Tolerances,
    sink: IssueSink,
) -> tuple[list[DetailShot], list[SetupOrientation], list[KnownPoint]]:
    """``known`` is extended in place with radiated stations; ``reserved`` are names that
    must come from a traverse and are never computed as detail points."""
    shots: list[DetailShot] = []
    orientations: list[SetupOrientation] = []
    detail: dict[str, _Candidate] = {}
    done: set[int] = set()
    known_before = set(known)
    warned_unknown: set[str] = set()

    progress = True
    while progress:
        progress = False
        for s in setups:
            if s.index in done:
                continue
            st = known.get(s.station)
            if st is None:
                continue
            done.add(s.index)
            progress = True
            refs = [t for t in s.targets.values() if t.target in known and t.target != s.station]
            if not refs:
                unknown_targets = [t for t in s.targets if t not in known]
                sink.warning(
                    "SETUP_NO_ORIENTATION",
                    f"Setup at {s.station} ({s.ref}) observes no known point; "
                    f"{len(unknown_targets)} observations cannot be oriented",
                    setup=s.ref,
                    station=s.station,
                    count=len(unknown_targets),
                )
                orientations.append(
                    SetupOrientation(
                        station=s.station, setup=s.ref, orientation=None, references=[], spread=None
                    )
                )
                continue
            omegas = [
                wrap_2pi(
                    grid_azimuth(st.x, st.y, known[t.target].x, known[t.target].y) - t.direction
                )
                for t in refs
            ]
            omega = circular_mean(omegas)
            spread = circular_spread(omegas)
            if spread > tol.orientation_spread_cc * 1e-4 * math.pi / 200:
                sink.warning(
                    "ORIENTATION_SPREAD",
                    f"Setup at {s.station}: orientations on {', '.join(t.target for t in refs)} "
                    f"disagree by {rad_to_cc(spread):.0f} cc",
                    setup=s.ref,
                    station=s.station,
                    spread_cc=round(rad_to_cc(spread), 1),
                    references=[t.target for t in refs],
                )
            orientations.append(
                SetupOrientation(
                    station=s.station,
                    setup=s.ref,
                    orientation=omega,
                    references=[t.target for t in refs],
                    spread=spread,
                )
            )
            for name in s.order:
                t = s.targets[name]
                az = wrap_2pi(t.direction + omega)
                is_known = name in known
                if t.hd is None:
                    if not is_known and name not in reserved:
                        sink.warning(
                            "DETAIL_NO_DISTANCE",
                            f"{name} observed from {s.station} without distance; not computed",
                            setup=s.ref,
                            station=s.station,
                            target=name,
                        )
                    shots.append(
                        DetailShot(
                            station=s.station,
                            target=name,
                            direction=t.direction,
                            zenith=t.zenith,
                            sd=t.sd,
                            hd=None,
                            distance_grid=None,
                            azimuth=az,
                            x=None,
                            y=None,
                            z=None,
                            code=t.code,
                            check=is_known,
                        )
                    )
                    continue
                x, y, z, d = _polar(st, t, az, rs)
                residual = None
                if is_known:
                    kp = known[name]
                    residual = grid_distance(kp.x, kp.y, x, y)
                    if residual > tol.check_shot_m:
                        sink.warning(
                            "CHECK_SHOT_RESIDUAL",
                            f"Check shot {s.station}→{name}: computed position differs from the "
                            f"known one by {residual * 1000:.0f} mm",
                            setup=s.ref,
                            station=s.station,
                            target=name,
                            residual_mm=round(residual * 1000, 1),
                        )
                elif name not in reserved:
                    c = detail.get(name)
                    if c is None:
                        c = detail[name] = _Candidate(name, [], [], [], t.code, [])
                    c.xs.append(x)
                    c.ys.append(y)
                    if z is not None:
                        c.zs.append(z)
                    c.stations.append(s.station)
                    c.code = c.code or t.code
                shots.append(
                    DetailShot(
                        station=s.station,
                        target=name,
                        direction=t.direction,
                        zenith=t.zenith,
                        sd=t.sd,
                        hd=t.hd,
                        distance_grid=d,
                        azimuth=az,
                        x=x,
                        y=y,
                        z=z,
                        code=t.code,
                        check=is_known,
                        residual=residual,
                    )
                )
        # promote radiated *stations* so their setups can be processed next pass
        stations_waiting = {s.station for s in setups if s.index not in done}
        for name in list(detail):
            if name in stations_waiting and name not in known:
                kp = _finalise(detail[name], tol, sink)
                known[name] = kp
                sink.info(
                    "STATION_BY_RADIATION",
                    f"Station {name} was determined by radiation from {kp.source} (no check)",
                    station=name,
                )
                progress = True

    for s in setups:
        if s.index not in done and s.station not in warned_unknown:
            warned_unknown.add(s.station)
            sink.warning(
                "SETUP_STATION_UNKNOWN",
                f"Station {s.station} has no coordinates; its observations were not computed",
                setup=s.ref,
                station=s.station,
            )

    points: list[KnownPoint] = []
    for name, c in detail.items():
        if name in known and name not in known_before and known[name].kind == "detail":
            points.append(known[name])
        elif name not in known:
            points.append(_finalise(c, tol, sink))
    return shots, orientations, points


def _finalise(c: _Candidate, tol: Tolerances, sink: IssueSink) -> KnownPoint:
    n = len(c.xs)
    x = sum(c.xs) / n
    y = sum(c.ys) / n
    z = sum(c.zs) / len(c.zs) if c.zs else None
    if n > 1:
        spread = max(math.hypot(px - x, py - y) for px, py in zip(c.xs, c.ys, strict=True))
        if spread > tol.detail_duplicate_m:
            sink.warning(
                "DETAIL_DUPLICATE",
                f"Point {c.name} measured {n} times (from {', '.join(c.stations)}); "
                f"determinations differ by up to {spread * 1000:.0f} mm from their mean",
                target=c.name,
                count=n,
                spread_mm=round(spread * 1000, 1),
            )
    return KnownPoint(
        name=c.name,
        x=x,
        y=y,
        z=z,
        kind="detail",
        code=c.code,
        source=", ".join(dict.fromkeys(c.stations)),
    )


__all__ = ["compute_detail", "wrap_pi"]
