"""Synthetic, geometrically exact observations generated from true coordinates.

The generator inverts the engine's reduction chain (grid → reference → horizontal,
plus curvature/refraction) so that perfect data must close to ~0 and reproduce the
true coordinates. Each setup gets an arbitrary circle orientation so the engine must
form angles from directions rather than assume a zeroed backsight.
"""

from __future__ import annotations

import math
import random

from atsurvey.core.geodesy import egsa87_line_scale, elevation_factor, grid_azimuth
from atsurvey.core.models import Observation, ReductionSettings, Setup
from atsurvey.core.units import CC_TO_RAD, wrap_2pi

Coords = dict[str, tuple[float, float, float]]


def observe(
    truth: Coords,
    station: str,
    targets: list[str],
    *,
    rs: ReductionSettings | None = None,
    hi: float = 1.55,
    ht: float = 1.80,
    orientation: float | None = None,
    face2: bool = False,
    rng: random.Random | None = None,
    angle_noise_cc: float = 0.0,
    dist_noise_m: float = 0.0,
    codes: dict[str, str] | None = None,
) -> Setup:
    rs = rs or ReductionSettings()
    rng = rng or random.Random(1)
    omega = orientation if orientation is not None else rng.uniform(0, 2 * math.pi)
    xs, ys, zs = truth[station]
    obs: list[Observation] = []
    for t in targets:
        xt, yt, zt = truth[t]
        d_grid = math.hypot(xt - xs, yt - ys)
        k = egsa87_line_scale(xs, xt) if rs.scale_mode in ("leg_simpson",) else 1.0
        if rs.scale_mode == "none":
            k = 1.0
        ef = elevation_factor(rs, (zs + zt) / 2)
        hd = d_grid / (k * ef)
        c = (1 - rs.refraction_coefficient) * hd * hd / (2 * rs.earth_radius)
        if not rs.curvature_refraction:
            c = 0.0
        vert = (zt - zs) - hi + ht - c
        sd = math.hypot(hd, vert) + (rng.gauss(0, dist_noise_m) if dist_noise_m else 0.0)
        zen = math.atan2(hd, vert)
        hz = wrap_2pi(grid_azimuth(xs, ys, xt, yt) - omega)
        if angle_noise_cc:
            hz = wrap_2pi(hz + rng.gauss(0, angle_noise_cc) * CC_TO_RAD)
        obs.append(
            Observation(
                target=t,
                hz=hz,
                v=zen,
                sd=sd,
                target_height=ht,
                code=(codes or {}).get(t),
            )
        )
        if face2:
            obs.append(
                Observation(
                    target=t,
                    hz=wrap_2pi(hz + math.pi),
                    v=2 * math.pi - zen,
                    sd=sd,
                    target_height=ht,
                )
            )
    return Setup(station=station, instrument_height=hi, observations=obs)


def traverse_setups(truth: Coords, route: list[str], **kw) -> list[Setup]:
    """One setup per angle station observing its back and forward neighbours."""
    rng = kw.pop("rng", None) or random.Random(7)
    setups = []
    for i in range(1, len(route) - 1):
        setups.append(observe(truth, route[i], [route[i - 1], route[i + 1]], rng=rng, **kw))
    return setups


# A realistic network near Athens (EGSA87), metres
TRUTH: Coords = {
    "T1": (476120.412, 4205333.187, 182.341),
    "T2": (476402.955, 4205418.664, 190.006),
    "S1": (476611.203, 4205290.118, 195.772),
    "S2": (476853.871, 4205377.540, 201.338),
    "S3": (477071.334, 4205246.905, 199.910),
    "T3": (477322.018, 4205351.773, 205.447),
    "T4": (477583.640, 4205522.091, 211.083),
    "D1": (476650.100, 4205330.000, 196.100),
    "D2": (476580.250, 4205250.750, 195.050),
    "D3": (476900.000, 4205400.000, 201.900),
    "D4": (477050.500, 4205300.250, 200.200),
}
CONTROL = ["T1", "T2", "T3", "T4"]
