"""Hatt projection (ΓΥΣ map sheets, Old Greek datum, Bessel 1841).

Definition (Katsougiannopoulos & Vergos 2004, §5.2.1; Ντέρης 2014 §2.3 after Φωτίου 2007):
the oblique **azimuthal equidistant** projection of the Bessel ellipsoid on the plane tangent
at the sheet centre T₀(φ₀, λ₀). A point T at geodesic distance S and geodesic azimuth α from
T₀ maps to

    x = S · sin α   (east)        y = S · cos α   (north, tangent to the meridian of T₀)

so lengths and azimuths of lines through the centre are preserved. Longitudes of the sheet
centres are counted from the Athens Observatory meridian (23°42′58.815″ E of Greenwich,
EPSG:8912). Greek textbooks evaluate S, α with series expansions valid to ≈ 40 km from the
centre; here they come from the exact geodesic (Vincenty), i.e. the same definition as
PROJ ``+proj=aeqd`` on the ellipsoid.

The official sheet table (≈ 130 sheets of 30′ × 30′, centres at whole degrees + 15′/45′)
and the ΟΚΧΕ/ΓΥΣ per-sheet 2nd-degree polynomials Hatt → ΕΓΣΑ87 are **not** bundled: they
plug into ``HATT_SHEETS`` (see docs/coords.md).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from . import geodesic
from .ellipsoid import BESSEL1841, Ellipsoid

#: Athens Observatory prime meridian, degrees east of Greenwich (EPSG:8912: 23°42′58.815″).
ATHENS_MERIDIAN_DEG = 23.7163375
ATHENS_MERIDIAN_RAD = math.radians(ATHENS_MERIDIAN_DEG)
#: Beyond this distance from the sheet centre the Greek textbook series lose accuracy and the
#: coordinates were never used in practice (reported as info).
HATT_PRACTICAL_RADIUS_M = 40_000.0
#: Hard limit of the implementation (refused beyond).
HATT_MAX_RADIUS_M = 500_000.0


@dataclass(frozen=True)
class HattProjection:
    lat0: float
    lon0: float  # Greenwich
    ellipsoid: Ellipsoid = BESSEL1841

    def forward(self, lat: float, lon: float) -> tuple[float, float]:
        """(φ, λ) → (x east, y north) relative to the sheet centre."""
        if not math.isfinite(lat) or abs(lat) >= math.pi / 2:
            raise ValueError("Latitude must be between −90° and 90° (exclusive)")
        s, az = geodesic.inverse(self.ellipsoid, self.lat0, self.lon0, lat, lon)
        if s > HATT_MAX_RADIUS_M:
            raise ValueError(f"Point {s / 1000:.0f} km from the Hatt sheet centre")
        return s * math.sin(az), s * math.cos(az)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        s = math.hypot(x, y)
        if not math.isfinite(s) or s > HATT_MAX_RADIUS_M:
            raise ValueError("Hatt coordinates too far from the sheet centre")
        if s == 0.0:
            return self.lat0, self.lon0
        return geodesic.direct(self.ellipsoid, self.lat0, self.lon0, math.atan2(x, y), s)


@dataclass(frozen=True)
class HattPolynomial:
    """Second-degree polynomial Hatt (x, y) → ΕΓΣΑ87 (E, N) for one sheet:

    E = e0 + ex·x + ey·y + exx·x² + eyy·y² + exy·x·y   (likewise N with n*)

    i.e. A0…A5 / B0…B5 in the term order given by secondary sources for the ΟΚΧΕ 1995 tables
    («Πίνακες συντελεστών μετατροπής συντεταγμένων … HATT … ΕΓΣΑ'87»); not verified against
    the booklet itself.

    Coefficient names state the term explicitly so that whoever loads the official ΟΚΧΕ
    booklet maps its columns (and any unit scaling of x, y) consciously.
    """

    e0: float
    ex: float
    ey: float
    exx: float
    eyy: float
    exy: float
    n0: float
    nx: float
    ny: float
    nxx: float
    nyy: float
    nxy: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        e = math.fsum(
            (
                self.e0,
                self.ex * x,
                self.ey * y,
                self.exx * x * x,
                self.eyy * y * y,
                self.exy * x * y,
            )
        )
        n = math.fsum(
            (
                self.n0,
                self.nx * x,
                self.ny * y,
                self.nxx * x * x,
                self.nyy * y * y,
                self.nxy * x * y,
            )
        )
        return e, n


@dataclass(frozen=True)
class HattSheet:
    code: str
    name: str
    lat0: float  # rad
    lon0_athens: float  # rad, from the Athens meridian
    polynomial: HattPolynomial | None = None

    @property
    def projection(self) -> HattProjection:
        return HattProjection(self.lat0, self.lon0_athens + ATHENS_MERIDIAN_RAD)


#: Official sheet table: EMPTY until the owner supplies the ΓΥΣ/ΟΚΧΕ data and licence.
#: Requesting a sheet code raises ``COORD_HATT_TABLE_MISSING``.
HATT_SHEETS: Mapping[str, HattSheet] = MappingProxyType({})
