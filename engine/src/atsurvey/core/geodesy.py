"""Distance and height reductions for EGSA87 (EPSG:2100, Transverse Mercator).

Reduction chain for a measured slope distance S with zenith angle z:

1. Horizontal distance        HD = S · sin z
2. Reference surface          D0 = HD · R / (R + Hm + N)
3. Grid (projection) distance  D  = D0 · k

with Hm the mean orthometric height of the line, N the geoid undulation and k the
TM scale factor. Heights: Δh = S · cos z + hi − ht + (1 − κ) · HD² / (2R).
"""

from __future__ import annotations

import math

from .models import ReductionSettings

EGSA87_K0 = 0.9996
EGSA87_FALSE_EASTING = 500000.0
#: k0 / (2 R²) expressed per (1000 km)² — the coefficient of the Greek textbook formula
#: k = 0.9996 + 0.012311 · ((E − 500000) / 10⁶)²
EGSA87_K_COEFF = 0.012311


def egsa87_point_scale(easting: float) -> float:
    """Point scale factor of the EGSA87 projection at a given easting."""
    e = (easting - EGSA87_FALSE_EASTING) / 1e6
    return EGSA87_K0 + EGSA87_K_COEFF * e * e


def egsa87_line_scale(e1: float, e2: float) -> float:
    """Line scale factor between two eastings (Simpson's rule)."""
    return (
        egsa87_point_scale(e1) + 4.0 * egsa87_point_scale((e1 + e2) / 2.0) + egsa87_point_scale(e2)
    ) / 6.0


def scale_for_line(s: ReductionSettings, e1: float, e2: float, traverse_k: float | None) -> float:
    mode = s.scale_mode
    if mode == "none":
        return 1.0
    if mode == "fixed":
        return s.fixed_scale
    if mode == "traverse_mean" and traverse_k is not None:
        return traverse_k
    if mode == "leg_mean":
        return egsa87_point_scale((e1 + e2) / 2.0)
    return egsa87_line_scale(e1, e2)


def elevation_factor(s: ReductionSettings, mean_height: float) -> float:
    """R / (R + H): reduction of a horizontal distance to the reference surface."""
    if not s.elevation_reduction:
        return 1.0
    h = mean_height + s.geoid_undulation
    return s.earth_radius / (s.earth_radius + h)


def horizontal_distance(sd: float, zenith: float | None) -> float:
    if zenith is None:
        return sd
    return sd * math.sin(zenith)


def height_difference(
    s: ReductionSettings,
    sd: float,
    zenith: float,
    instrument_height: float,
    target_height: float,
) -> float:
    hd = sd * math.sin(zenith)
    dh = sd * math.cos(zenith) + instrument_height - target_height
    if s.curvature_refraction:
        dh += (1.0 - s.refraction_coefficient) * hd * hd / (2.0 * s.earth_radius)
    return dh


def grid_azimuth(x1: float, y1: float, x2: float, y2: float) -> float:
    """Grid bearing from point 1 to point 2, clockwise from north, in [0, 2π)."""
    a = math.atan2(x2 - x1, y2 - y1)
    return a + 2.0 * math.pi if a < 0 else a


def grid_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)
