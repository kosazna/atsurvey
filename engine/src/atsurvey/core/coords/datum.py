"""Geodetic datums used in Greece and the shifts between them.

Datums form a chain  greek (Old Greek, Bessel) — ggrs87 (ΕΓΣΑ87, GRS80) — wgs84.

* ggrs87 ↔ wgs84, method ``approximate``: geocentric translation of EPSG:1272
  "GGRS87 to WGS 84 (1)", ΔX = −199.87, ΔY = 74.79, ΔZ = 246.62 m (the ``+towgs84`` of
  EPSG:2100, also used by the web map). EPSG states 1 m; compared with the official HEPOS
  model it is 0.2–1.5 m off across Greece, so 1.5 m is reported. **Not** for cadastral work.
* ggrs87 ↔ wgs84, method ``official``: the HEPOS HTRS07 → ΕΓΣΑ87 transformation
  (``hepos.py``: 7 parameters + 2 km correction grids, ≈ 8 cm). Active only when the grids
  are installed (``ATSURVEY_HEPOS_GRID_DIR``); otherwise ``COORD_HEPOS_UNAVAILABLE``.
* greek ↔ ggrs87, method ``approximate``: geographic offsets of EPSG:1891 "Greek to
  GGRS87 (1)", Δφ = −5.86″, Δλ = +0.28″, accuracy 5 m. EPSG's own remark: "More accurate
  polynomial transformations between Greek / Hatt projection zones and GGRS87 / Greek Grid
  are available from the Military Geographic Service" — those are the per-sheet ΟΚΧΕ/ΓΥΣ
  polynomials (``hatt.HattPolynomial``), applied grid to grid in ``convert``.

Reference for the geocentric translation: EPSG Guidance Note 7-2, method 9603.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from .ellipsoid import BESSEL1841, GRS80, WGS84, Ellipsoid, ecef_to_geodetic, geodetic_to_ecef
from .errors import CoordsError

DatumId = Literal["greek", "ggrs87", "wgs84"]
DatumMethod = Literal["approximate", "official"]

ELLIPSOIDS: dict[DatumId, Ellipsoid] = {"greek": BESSEL1841, "ggrs87": GRS80, "wgs84": WGS84}
_CHAIN: tuple[DatumId, ...] = ("greek", "ggrs87", "wgs84")

ARCSEC = math.pi / (180 * 3600)

Geo = tuple[float, float, float]  # (φ, λ, h)


class DatumShift(Protocol):
    """One edge of the datum chain, from ``src`` to ``dst`` (and back with ``inverse``)."""

    @property
    def src(self) -> DatumId: ...

    @property
    def dst(self) -> DatumId: ...

    @property
    def label(self) -> str: ...

    @property
    def accuracy_m(self) -> float: ...

    @property
    def approximate(self) -> bool: ...

    def forward(self, p: Geo) -> Geo: ...

    def inverse(self, p: Geo) -> Geo: ...


@dataclass(frozen=True)
class GeocentricTranslation:
    src: DatumId
    dst: DatumId
    label: str
    accuracy_m: float
    dx: float
    dy: float
    dz: float
    approximate: bool = True

    def _shift(self, p: Geo, a: Ellipsoid, b: Ellipsoid, sign: float) -> Geo:
        x, y, z = geodetic_to_ecef(a, *p)
        return ecef_to_geodetic(b, x + sign * self.dx, y + sign * self.dy, z + sign * self.dz)

    def forward(self, p: Geo) -> Geo:
        return self._shift(p, ELLIPSOIDS[self.src], ELLIPSOIDS[self.dst], 1.0)

    def inverse(self, p: Geo) -> Geo:
        return self._shift(p, ELLIPSOIDS[self.dst], ELLIPSOIDS[self.src], -1.0)


@dataclass(frozen=True)
class GeographicOffsets:
    src: DatumId
    dst: DatumId
    label: str
    accuracy_m: float
    dlat: float
    dlon: float
    approximate: bool = True

    def forward(self, p: Geo) -> Geo:
        return p[0] + self.dlat, p[1] + self.dlon, p[2]

    def inverse(self, p: Geo) -> Geo:
        return p[0] - self.dlat, p[1] - self.dlon, p[2]


EPSG_1272 = GeocentricTranslation(
    "ggrs87", "wgs84", "EPSG:1272 (3 παράμετροι)", 1.5, -199.87, 74.79, 246.62
)
EPSG_1891 = GeographicOffsets(
    "greek", "ggrs87", "EPSG:1891 (μεταθέσεις φ, λ)", 5.0, -5.86 * ARCSEC, 0.28 * ARCSEC
)

#: Override of the official HEPOS transformation (tests, embedding). When ``None`` the grids
#: are looked up through ``ATSURVEY_HEPOS_GRID_DIR`` (see ``hepos.py``).
HEPOS_TRANSFORMATION: DatumShift | None = None


def hepos_transformation() -> DatumShift | None:
    if HEPOS_TRANSFORMATION is not None:
        return HEPOS_TRANSFORMATION
    from . import hepos  # imports this module: keep the import local

    return hepos.from_environment()


def _edge(a: DatumId, b: DatumId, method: DatumMethod) -> tuple[DatumShift, bool]:
    """The shift between neighbouring datums a, b and whether it runs forward."""
    if {a, b} == {"ggrs87", "wgs84"}:
        if method == "official":
            official = hepos_transformation()
            if official is None:
                raise CoordsError(
                    "COORD_HEPOS_UNAVAILABLE",
                    "The official HEPOS transformation (HTRS07 → ΕΓΣΑ87) is not available: "
                    "its correction grids are not installed on this server",
                )
            shift = official
        else:
            shift = EPSG_1272
    else:  # greek ↔ ggrs87
        if method == "official":
            raise CoordsError(
                "COORD_NO_OFFICIAL_SHIFT",
                "There is no official datum shift for the Old Greek datum; use the per-sheet "
                "Hatt polynomials or a local Helmert/affine fit on common points",
            )
        shift = EPSG_1891
    return shift, shift.src == a


def datum_path(src: DatumId, dst: DatumId, method: DatumMethod) -> list[tuple[DatumShift, bool]]:
    """Ordered shifts (with direction) that take geographic coordinates from src to dst."""
    i, j = _CHAIN.index(src), _CHAIN.index(dst)
    step = 1 if j > i else -1
    return [_edge(_CHAIN[k], _CHAIN[k + step], method) for k in range(i, j, step)]


def apply_path(path: list[tuple[DatumShift, bool]], p: Geo) -> Geo:
    for shift, fwd in path:
        p = shift.forward(p) if fwd else shift.inverse(p)
    return p
