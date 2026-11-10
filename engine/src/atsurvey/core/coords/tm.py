"""Transverse Mercator (Gauss–Krüger) projection: Krüger n-series to 6th order.

Reference: C. F. F. Karney, "Transverse Mercator with an accuracy of a few nanometers",
J. Geodesy 85(8), 475–485 (2011), doi:10.1007/s00190-011-0445-3, eqs. (7)–(36). With six
terms the series is accurate to ≈ 5 nm within 3 900 km of the central meridian, far below
anything a survey can see. Also gives the point scale factor k and the meridian
convergence γ (bearing of grid north, clockwise from true north; positive east of the
central meridian in the northern hemisphere).

Same algorithm as GeographicLib's ``TransverseMercator`` and PROJ's default ``tmerc``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .ellipsoid import Ellipsoid

#: Points farther than this from the central meridian are refused (the 6th-order series is
#: specified to ≈ 35° of longitude; no Greek system is used beyond ~6°).
MAX_DLON_RAD = math.radians(30.0)
_NEWTON_MAX_ITER = 10
_NEWTON_TOL = 1e-15


def _alpha(n: float) -> tuple[float, ...]:
    """Forward coefficients α₁…α₆ (Karney 2011, eq. 35)."""
    n2, n3, n4, n5, n6 = n**2, n**3, n**4, n**5, n**6
    return (
        n / 2 - 2 * n2 / 3 + 5 * n3 / 16 + 41 * n4 / 180 - 127 * n5 / 288 + 7891 * n6 / 37800,
        13 * n2 / 48 - 3 * n3 / 5 + 557 * n4 / 1440 + 281 * n5 / 630 - 1983433 * n6 / 1935360,
        61 * n3 / 240 - 103 * n4 / 140 + 15061 * n5 / 26880 + 167603 * n6 / 181440,
        49561 * n4 / 161280 - 179 * n5 / 168 + 6601661 * n6 / 7257600,
        34729 * n5 / 80640 - 3418889 * n6 / 1995840,
        212378941 * n6 / 319334400,
    )


def _beta(n: float) -> tuple[float, ...]:
    """Inverse coefficients β₁…β₆ (Karney 2011, eq. 36)."""
    n2, n3, n4, n5, n6 = n**2, n**3, n**4, n**5, n**6
    return (
        n / 2 - 2 * n2 / 3 + 37 * n3 / 96 - n4 / 360 - 81 * n5 / 512 + 96199 * n6 / 604800,
        n2 / 48 + n3 / 15 - 437 * n4 / 1440 + 46 * n5 / 105 - 1118711 * n6 / 3870720,
        17 * n3 / 480 - 37 * n4 / 840 - 209 * n5 / 4480 + 5569 * n6 / 90720,
        4397 * n4 / 161280 - 11 * n5 / 504 - 830251 * n6 / 7257600,
        4583 * n5 / 161280 - 108847 * n6 / 3991680,
        20648693 * n6 / 638668800,
    )


def _tau_prime(tau: float, e: float) -> float:
    """Conformal latitude as τ' = tan χ from τ = tan φ (Karney 2011, eqs. 7–9)."""
    tau1 = math.hypot(1.0, tau)
    sig = math.sinh(e * math.atanh(e * tau / tau1))
    return tau * math.hypot(1.0, sig) - sig * tau1


@dataclass(frozen=True)
class TransverseMercator:
    """A TM grid: E = FE + k₀ A η,  N = FN + k₀ A (ξ − ξ(φ₀))."""

    ellipsoid: Ellipsoid
    lon0: float
    k0: float
    false_easting: float
    false_northing: float = 0.0
    lat0: float = 0.0
    _a1: float = field(init=False, repr=False)
    _alp: tuple[float, ...] = field(init=False, repr=False)
    _bet: tuple[float, ...] = field(init=False, repr=False)
    _xi0: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        n = self.ellipsoid.n
        # Rectifying radius A (Karney 2011, eq. 14)
        a1 = self.ellipsoid.a / (1 + n) * (1 + n**2 / 4 + n**4 / 64 + n**6 / 256)
        object.__setattr__(self, "_a1", a1)
        object.__setattr__(self, "_alp", _alpha(n))
        object.__setattr__(self, "_bet", _beta(n))
        object.__setattr__(self, "_xi0", self._xi_eta(self.lat0, 0.0)[0])

    # ------------------------------------------------------------------ internals

    def _primes(self, lat: float, dlon: float) -> tuple[float, float, float]:
        """ξ', η' (spherical TM of the conformal sphere) and τ'."""
        taup = _tau_prime(math.tan(lat), self.ellipsoid.e)
        xip = math.atan2(taup, math.cos(dlon))
        etap = math.asinh(math.sin(dlon) / math.hypot(taup, math.cos(dlon)))
        return xip, etap, taup

    def _xi_eta(self, lat: float, dlon: float) -> tuple[float, float]:
        xip, etap, _ = self._primes(lat, dlon)
        xi, eta = xip, etap
        for j, a in enumerate(self._alp, start=1):
            xi += a * math.sin(2 * j * xip) * math.cosh(2 * j * etap)
            eta += a * math.cos(2 * j * xip) * math.sinh(2 * j * etap)
        return xi, eta

    def _check_dlon(self, dlon: float) -> float:
        d = math.remainder(dlon, 2 * math.pi)
        if abs(d) > MAX_DLON_RAD:
            raise ValueError(
                f"Longitude {math.degrees(d):.1f}° from the central meridian: outside the projection"
            )
        return d

    @staticmethod
    def _check_lat(lat: float) -> None:
        if not math.isfinite(lat) or abs(lat) >= math.pi / 2:
            raise ValueError("Latitude must be between −90° and 90° (exclusive)")

    # ------------------------------------------------------------------ public API

    def forward(self, lat: float, lon: float) -> tuple[float, float]:
        """(φ, λ) → (E, N)."""
        self._check_lat(lat)
        dlon = self._check_dlon(lon - self.lon0)
        xi, eta = self._xi_eta(lat, dlon)
        k0a = self.k0 * self._a1
        return self.false_easting + k0a * eta, self.false_northing + k0a * (xi - self._xi0)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """(E, N) → (φ, λ). Newton iteration for φ from the conformal latitude (eqs. 19–21)."""
        k0a = self.k0 * self._a1
        xi = (y - self.false_northing) / k0a + self._xi0
        eta = (x - self.false_easting) / k0a
        if not (math.isfinite(xi) and math.isfinite(eta)) or abs(eta) > 1.5:
            raise ValueError("Grid coordinates outside the projection")
        xip, etap = xi, eta
        for j, b in enumerate(self._bet, start=1):
            xip -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
            etap -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
        s, c = math.sinh(etap), math.cos(xip)
        r = math.hypot(s, c)
        dlon = math.atan2(s, c)
        taup = math.sin(xip) / r
        ell = self.ellipsoid
        tau = taup
        for _ in range(_NEWTON_MAX_ITER):
            tp = _tau_prime(tau, ell.e)
            dtau = (
                (taup - tp)
                / math.hypot(1.0, tp)
                * (1 + (1 - ell.e2) * tau * tau)
                / ((1 - ell.e2) * math.hypot(1.0, tau))
            )
            tau += dtau
            if abs(dtau) < _NEWTON_TOL * max(1.0, abs(tau)):
                break
        lat = math.atan(tau)
        lon = math.remainder(self.lon0 + dlon, 2 * math.pi)
        return lat, lon

    def scale_convergence(self, lat: float, lon: float) -> tuple[float, float]:
        """Point scale factor k and meridian convergence γ (rad) at (φ, λ) (eqs. 25–28)."""
        self._check_lat(lat)
        dlon = self._check_dlon(lon - self.lon0)
        xip, etap, taup = self._primes(lat, dlon)
        pp, qq = 1.0, 0.0
        for j, a in enumerate(self._alp, start=1):
            pp += 2 * j * a * math.cos(2 * j * xip) * math.cosh(2 * j * etap)
            qq += 2 * j * a * math.sin(2 * j * xip) * math.sinh(2 * j * etap)
        ell = self.ellipsoid
        tau = math.tan(lat)
        cl = math.cos(dlon)
        gamma = math.atan2(taup * math.tan(dlon), math.hypot(1.0, taup)) + math.atan2(qq, pp)
        s = math.sin(lat)
        k1 = math.sqrt(1 - ell.e2 * s * s) * math.hypot(1.0, tau) / math.hypot(taup, cl)
        k2 = self._a1 / ell.a * math.hypot(pp, qq)
        return self.k0 * k1 * k2, gamma
