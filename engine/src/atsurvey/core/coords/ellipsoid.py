"""Reference ellipsoids, geodetic ↔ geocentric (ECEF) conversion and radii of curvature.

References: Torge & Müller, *Geodesy* (4th ed., 2012) §6.2; EPSG Guidance Note 7-2
(IOGP 373-7-2, 2019), "Geographic/geocentric conversions" (method code 9602).
Angles are radians, lengths metres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Iteration limit and convergence threshold of the ECEF → geodetic latitude iteration.
_ECEF_MAX_ITER = 20
_ECEF_TOL_RAD = 1e-14


@dataclass(frozen=True)
class Ellipsoid:
    name: str
    a: float
    inv_f: float

    @property
    def f(self) -> float:
        return 1.0 / self.inv_f

    @property
    def b(self) -> float:
        return self.a * (1.0 - self.f)

    @property
    def e2(self) -> float:
        """First eccentricity squared."""
        return self.f * (2.0 - self.f)

    @property
    def e(self) -> float:
        return math.sqrt(self.e2)

    @property
    def n(self) -> float:
        """Third flattening n = f / (2 − f)."""
        return self.f / (2.0 - self.f)

    def prime_vertical_radius(self, lat: float) -> float:
        """N(φ) = a / √(1 − e² sin²φ)."""
        s = math.sin(lat)
        return self.a / math.sqrt(1.0 - self.e2 * s * s)

    def meridian_radius(self, lat: float) -> float:
        """M(φ) = a (1 − e²) / (1 − e² sin²φ)^{3/2}."""
        s = math.sin(lat)
        w2 = 1.0 - self.e2 * s * s
        return self.a * (1.0 - self.e2) / (w2 * math.sqrt(w2))

    def gaussian_radius(self, lat: float) -> float:
        """Mean (Gaussian) radius of curvature √(M N), used for height reductions."""
        return math.sqrt(self.meridian_radius(lat) * self.prime_vertical_radius(lat))


#: GRS80 (ΕΓΣΑ87 / GGRS87, ETRS89, HTRS07). EPSG:7019.
GRS80 = Ellipsoid("GRS80", 6378137.0, 298.257222101)
#: WGS84. EPSG:7030.
WGS84 = Ellipsoid("WGS84", 6378137.0, 298.257223563)
#: Bessel 1841 (Old Greek datum: Hatt, TM3). EPSG:7004.
BESSEL1841 = Ellipsoid("Bessel 1841", 6377397.155, 299.1528128)


def geodetic_to_ecef(
    ell: Ellipsoid, lat: float, lon: float, h: float
) -> tuple[float, float, float]:
    """(φ, λ, h) → geocentric (X, Y, Z)."""
    n = ell.prime_vertical_radius(lat)
    cl = math.cos(lat)
    return (
        (n + h) * cl * math.cos(lon),
        (n + h) * cl * math.sin(lon),
        (n * (1.0 - ell.e2) + h) * math.sin(lat),
    )


def ecef_to_geodetic(ell: Ellipsoid, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Geocentric (X, Y, Z) → (φ, λ, h), fixed-point iteration on φ (Torge & Müller eq. 6.27).

    Converges to < 1e-14 rad in 3–5 iterations for points near the Earth's surface.
    """
    p = math.hypot(x, y)
    lon = math.atan2(y, x)
    if p < 1e-9:  # on the polar axis
        lat = math.copysign(math.pi / 2, z)
        return lat, lon, abs(z) - ell.b
    lat = math.atan2(z, p * (1.0 - ell.e2))
    h = 0.0
    for _ in range(_ECEF_MAX_ITER):
        n = ell.prime_vertical_radius(lat)
        h = p / math.cos(lat) - n
        new = math.atan2(z, p * (1.0 - ell.e2 * n / (n + h)))
        if abs(new - lat) < _ECEF_TOL_RAD:
            lat = new
            break
        lat = new
    n = ell.prime_vertical_radius(lat)
    h = p / math.cos(lat) - n
    return lat, lon, h
