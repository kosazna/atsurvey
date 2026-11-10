"""Long profile along a polyline and cross-sections at a chainage interval.

The long profile has a station at every alignment vertex on the surface and at every
crossing of a TIN edge (the heights in between are linear, so these stations describe the
ground line exactly). Where the line leaves the surface a new ``run`` starts.

Cross-sections are perpendicular to the alignment segment they fall on (at a vertex, the
following segment; at the end, the last one), from −half_width (left) to +half_width
(right), and are sampled the same way.
"""

from __future__ import annotations

import math

import numpy as np

from ..models import Issue
from .geom import F64
from .models import MAX_SECTIONS, CrossSection, ProfileStation
from .sample import Sampler

JOIN_EPS = 1e-9


def _azimuth(dx: float, dy: float) -> float:
    a = math.atan2(dx, dy)
    return a + 2 * math.pi if a < 0 else a


def long_profile(s: Sampler, verts: F64) -> tuple[float, list[ProfileStation], bool]:
    """Stations along the polyline (local coordinates), total length, and whether gaps exist."""
    ox, oy = s.tin.origin
    stations: list[ProfileStation] = []
    chain0 = 0.0
    run = -1
    open_end = False  # the previous segment reached t = 1 on the surface
    gaps = False
    for i in range(len(verts) - 1):
        p0, p1 = verts[i], verts[i + 1]
        seg_len = float(np.hypot(*(p1 - p0)))
        if seg_len == 0:
            continue
        runs = s.segment(p0, p1)
        if not runs or runs[0][0][0] > JOIN_EPS or runs[-1][-1][0] < 1 - JOIN_EPS or len(runs) > 1:
            gaps = True
        for j, r in enumerate(runs):
            continues = j == 0 and open_end and r[0][0] <= JOIN_EPS
            if not continues:
                run += 1
            for k, (t, z) in enumerate(r):
                if continues and k == 0:
                    continue  # same point as the end of the previous segment
                x = p0[0] + t * (p1[0] - p0[0])
                y = p0[1] + t * (p1[1] - p0[1])
                stations.append(
                    ProfileStation(chainage=chain0 + t * seg_len, x=x + ox, y=y + oy, z=z, run=run)
                )
        open_end = bool(runs) and runs[-1][-1][0] >= 1 - JOIN_EPS
        chain0 += seg_len
    return chain0, stations, gaps


def cross_sections(
    s: Sampler, verts: F64, interval: float, half_width: float
) -> list[CrossSection]:
    seg = np.diff(verts, axis=0)
    lens = np.hypot(seg[:, 0], seg[:, 1])
    keep = lens > 0
    verts_k = np.concatenate([verts[:1], verts[1:][keep]])
    seg, lens = seg[keep], lens[keep]
    cum = np.concatenate([[0.0], np.cumsum(lens)])
    total = float(cum[-1])
    n = math.floor(total / interval + 1e-9) + 1
    chainages = [k * interval for k in range(n)]
    if total - chainages[-1] > 1e-6:
        chainages.append(total)
    if len(chainages) > MAX_SECTIONS:
        raise ValueError(
            f"Too many cross-sections ({len(chainages)} > {MAX_SECTIONS}): increase the interval"
        )
    ox, oy = s.tin.origin
    out: list[CrossSection] = []
    centres = []
    for c in chainages:
        i = min(int(np.searchsorted(cum, c, side="right")) - 1, len(seg) - 1)
        t = (c - cum[i]) / lens[i]
        p = verts_k[i] + t * seg[i]
        u = seg[i] / lens[i]
        right = np.array([u[1], -u[0]])
        centres.append(p)
        a, b = p - half_width * right, p + half_width * right
        stations: list[ProfileStation] = []
        for run, r in enumerate(s.segment(a, b)):
            for tt, z in r:
                q = a + tt * (b - a)
                stations.append(
                    ProfileStation(
                        chainage=-half_width + tt * 2 * half_width,
                        x=float(q[0] + ox),
                        y=float(q[1] + oy),
                        z=z,
                        run=run,
                    )
                )
        out.append(
            CrossSection(
                chainage=c,
                x=float(p[0] + ox),
                y=float(p[1] + oy),
                z=None,
                azimuth=_azimuth(float(u[0]), float(u[1])),
                stations=stations,
            )
        )
    zc, _ = s.heights(np.array(centres))
    return [
        cs.model_copy(update={"z": None if math.isnan(z) else float(z)})
        for cs, z in zip(out, zc.tolist(), strict=True)
    ]


def gap_issue() -> Issue:
    return Issue(
        severity="info",
        code="SURF_PROFILE_GAP",
        message="Parts of the line are outside the surface (no heights there)",
        params={},
    )
