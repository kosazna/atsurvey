"""Reduction of raw setups: face II → face I, averaging of rounds, per-target means.

After reduction each setup holds one mean direction / zenith / horizontal distance /
height difference per target. Angles at a station and leg measurements between two
stations are then looked up across *all* setups, so re-occupations and forward /
backward measurements are averaged automatically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geodesy import height_difference, horizontal_distance
from .issues import IssueSink
from .models import ReductionSettings, Setup, Tolerances
from .units import CC_TO_RAD, circular_mean, circular_spread, rad_to_cc, wrap_2pi


@dataclass(slots=True)
class ReducedTarget:
    target: str
    direction: float
    zenith: float | None
    sd: float | None
    hd: float | None
    dh: float | None
    n: int
    direction_spread: float
    code: str | None


@dataclass(slots=True)
class ReducedSetup:
    index: int
    ref: str
    station: str
    instrument_height: float
    targets: dict[str, ReducedTarget] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)


def reduce_setups(
    setups: list[Setup], rs: ReductionSettings, tol: Tolerances, sink: IssueSink
) -> list[ReducedSetup]:
    out: list[ReducedSetup] = []
    for i, setup in enumerate(setups):
        ref = setup.id or f"#{i + 1}"
        rset = ReducedSetup(
            index=i, ref=ref, station=setup.station, instrument_height=setup.instrument_height
        )
        groups: dict[str, list] = {}
        for obs in setup.observations:
            if obs.excluded:
                continue
            if obs.target == setup.station:
                continue
            if obs.target not in groups:
                groups[obs.target] = []
                rset.order.append(obs.target)
            groups[obs.target].append(obs)

        for target, obs_list in groups.items():
            dirs: list[float] = []
            zens: list[float] = []
            sds: list[float] = []
            hds: list[float] = []
            dhs: list[float] = []
            code = None
            for o in obs_list:
                hz = o.hz
                v = o.v
                if v is not None and v > math.pi:  # face II
                    hz = wrap_2pi(hz - math.pi)
                    v = 2.0 * math.pi - v
                dirs.append(wrap_2pi(hz))
                if v is not None:
                    zens.append(v)
                if o.sd is not None and o.sd > 0:
                    sds.append(o.sd)
                    hds.append(horizontal_distance(o.sd, v))
                    if v is not None:
                        dhs.append(
                            height_difference(rs, o.sd, v, setup.instrument_height, o.target_height)
                        )
                code = code or o.code
            spread = circular_spread(dirs)
            if spread > tol.round_spread_cc * CC_TO_RAD:
                sink.warning(
                    "ROUND_SPREAD",
                    f"Directions to {target} from {setup.station} differ by "
                    f"{rad_to_cc(spread):.0f} cc between rounds/faces",
                    setup=ref,
                    station=setup.station,
                    target=target,
                    spread_cc=round(rad_to_cc(spread), 1),
                )
            rset.targets[target] = ReducedTarget(
                target=target,
                direction=circular_mean(dirs),
                zenith=sum(zens) / len(zens) if zens else None,
                sd=sum(sds) / len(sds) if sds else None,
                hd=sum(hds) / len(hds) if hds else None,
                dh=sum(dhs) / len(dhs) if dhs else None,
                n=len(obs_list),
                direction_spread=spread,
                code=code,
            )
        out.append(rset)
    return out


@dataclass(slots=True)
class LegMeasurement:
    hd: float
    n: int
    fb_diff: float | None
    dh: float | None
    dh_fb_diff: float | None


class ObservationIndex:
    """Fast lookups of angles and legs across all reduced setups."""

    def __init__(self, setups: list[ReducedSetup]):
        self.setups = setups
        self.by_station: dict[str, list[ReducedSetup]] = {}
        for s in setups:
            self.by_station.setdefault(s.station, []).append(s)

    def stations(self) -> set[str]:
        return set(self.by_station)

    def angle(self, station: str, bs: str, fs: str) -> float | None:
        """Clockwise angle at ``station`` from ``bs`` to ``fs`` (mean over setups)."""
        values = []
        for s in self.by_station.get(station, []):
            tb = s.targets.get(bs)
            tf = s.targets.get(fs)
            if tb and tf:
                values.append(wrap_2pi(tf.direction - tb.direction))
        if not values:
            return None
        return circular_mean(values)

    def leg(self, a: str, b: str) -> LegMeasurement | None:
        fwd_hd: list[float] = []
        bwd_hd: list[float] = []
        fwd_dh: list[float] = []
        bwd_dh: list[float] = []
        for s in self.by_station.get(a, []):
            t = s.targets.get(b)
            if t and t.hd is not None:
                fwd_hd.append(t.hd)
                if t.dh is not None:
                    fwd_dh.append(t.dh)
        for s in self.by_station.get(b, []):
            t = s.targets.get(a)
            if t and t.hd is not None:
                bwd_hd.append(t.hd)
                if t.dh is not None:
                    bwd_dh.append(-t.dh)
        all_hd = fwd_hd + bwd_hd
        if not all_hd:
            return None
        fb = None
        if fwd_hd and bwd_hd:
            fb = sum(fwd_hd) / len(fwd_hd) - sum(bwd_hd) / len(bwd_hd)
        dh_fb = None
        if fwd_dh and bwd_dh:
            dh_fb = sum(fwd_dh) / len(fwd_dh) - sum(bwd_dh) / len(bwd_dh)
        # forward and backward groups weigh equally regardless of round count
        groups_hd = [g for g in (fwd_hd, bwd_hd) if g]
        hd = sum(sum(g) / len(g) for g in groups_hd) / len(groups_hd)
        dh = None
        groups_dh = [g for g in (fwd_dh, bwd_dh) if g]
        if groups_dh:
            dh = sum(sum(g) / len(g) for g in groups_dh) / len(groups_dh)
        return LegMeasurement(hd=hd, n=len(all_hd), fb_diff=fb, dh=dh, dh_fb_diff=dh_fb)

    def observed_pairs(self) -> set[tuple[str, str]]:
        """Undirected station/target pairs with a measured distance."""
        pairs: set[tuple[str, str]] = set()
        for s in self.setups:
            for t in s.targets.values():
                if t.hd is not None:
                    pairs.add(tuple(sorted((s.station, t.target))))  # type: ignore[arg-type]
        return pairs
