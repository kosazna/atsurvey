"""Geodesic direct and inverse problems on the ellipsoid (Vincenty 1975).

Reference: T. Vincenty, "Direct and inverse solutions of geodesics on the ellipsoid with
application of nested equations", Survey Review 23(176), 88–93 (1975). Accurate to
≈ 0.1 mm at any distance except near-antipodal points; for the tens of kilometres of a
Hatt sheet the truncation error is at the nanometre level (verified against PROJ, which
uses Karney's algorithm, in the tests).
"""

from __future__ import annotations

import math

from .ellipsoid import Ellipsoid

_MAX_ITER = 200
_TOL = 1e-14


def _series_ab(u2: float) -> tuple[float, float]:
    a = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    b = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    return a, b


def _delta_sigma(b: float, sig: float, ssig: float, csig: float, c2sm: float) -> float:
    return (
        b
        * ssig
        * (
            c2sm
            + b
            / 4
            * (
                csig * (-1 + 2 * c2sm * c2sm)
                - b / 6 * c2sm * (-3 + 4 * ssig * ssig) * (-3 + 4 * c2sm * c2sm)
            )
        )
    )


def inverse(
    ell: Ellipsoid, lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float]:
    """Distance s and forward azimuth α₁ at point 1 (clockwise from north, rad)."""
    a, f = ell.a, ell.f
    bb = ell.b
    u1 = math.atan((1 - f) * math.tan(lat1))
    u2 = math.atan((1 - f) * math.tan(lat2))
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    big_l = math.remainder(lon2 - lon1, 2 * math.pi)
    lam = big_l
    for _ in range(_MAX_ITER):
        sl, cl = math.sin(lam), math.cos(lam)
        ssig = math.hypot(cu2 * sl, cu1 * su2 - su1 * cu2 * cl)
        if ssig == 0.0:
            return 0.0, 0.0  # coincident points
        csig = su1 * su2 + cu1 * cu2 * cl
        sig = math.atan2(ssig, csig)
        salpha = cu1 * cu2 * sl / ssig
        c2alpha = 1 - salpha * salpha
        c2sm = csig - 2 * su1 * su2 / c2alpha if c2alpha != 0 else 0.0
        c = f / 16 * c2alpha * (4 + f * (4 - 3 * c2alpha))
        prev = lam
        lam = big_l + (1 - c) * f * salpha * (
            sig + c * ssig * (c2sm + c * csig * (-1 + 2 * c2sm * c2sm))
        )
        if abs(lam - prev) < _TOL:
            break
    else:
        raise ValueError("Geodesic inverse did not converge (nearly antipodal points)")
    u2sq = c2alpha * (a * a - bb * bb) / (bb * bb)
    aa, b_ = _series_ab(u2sq)
    s = bb * aa * (sig - _delta_sigma(b_, sig, ssig, csig, c2sm))
    alpha1 = math.atan2(cu2 * math.sin(lam), cu1 * su2 - su1 * cu2 * math.cos(lam))
    return s, alpha1


def direct(
    ell: Ellipsoid, lat1: float, lon1: float, alpha1: float, s: float
) -> tuple[float, float]:
    """Point reached from (φ₁, λ₁) along azimuth α₁ after distance s."""
    a, f = ell.a, ell.f
    bb = ell.b
    tu1 = (1 - f) * math.tan(lat1)
    cu1 = 1 / math.sqrt(1 + tu1 * tu1)
    su1 = tu1 * cu1
    sa1, ca1 = math.sin(alpha1), math.cos(alpha1)
    sig1 = math.atan2(tu1, ca1)
    salpha = cu1 * sa1
    c2alpha = 1 - salpha * salpha
    u2sq = c2alpha * (a * a - bb * bb) / (bb * bb)
    aa, b_ = _series_ab(u2sq)
    sig = s / (bb * aa)
    for _ in range(_MAX_ITER):
        c2sm = math.cos(2 * sig1 + sig)
        ssig, csig = math.sin(sig), math.cos(sig)
        new = s / (bb * aa) + _delta_sigma(b_, sig, ssig, csig, c2sm)
        if abs(new - sig) < _TOL:
            sig = new
            break
        sig = new
    c2sm = math.cos(2 * sig1 + sig)
    ssig, csig = math.sin(sig), math.cos(sig)
    tmp = su1 * ssig - cu1 * csig * ca1
    lat2 = math.atan2(su1 * csig + cu1 * ssig * ca1, (1 - f) * math.hypot(salpha, tmp))
    lam = math.atan2(ssig * sa1, cu1 * csig - su1 * ssig * ca1)
    c = f / 16 * c2alpha * (4 + f * (4 - 3 * c2alpha))
    big_l = lam - (1 - c) * f * salpha * (
        sig + c * ssig * (c2sm + c * csig * (-1 + 2 * c2sm * c2sm))
    )
    return lat2, math.remainder(lon1 + big_l, 2 * math.pi)
