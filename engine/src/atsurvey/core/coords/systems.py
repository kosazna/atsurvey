"""Coordinate systems offered by the tools and their definitions.

| id | datum | definition |
|---|---|---|
| egsa87 | GGRS87 (GRS80) | TM, λ₀ 24°, k₀ 0.9996, FE 500 000, FN 0 (EPSG:2100) |
| ggrs87_geo | GGRS87 | φ, λ on GRS80 (EPSG:4121) |
| wgs84_geo | WGS84 | φ, λ, h (EPSG:4326; ETRS89/HTRS07 within the approximate shift) |
| utm34 / utm35 | WGS84 | TM, λ₀ 21° / 27°, k₀ 0.9996, FE 500 000 (EPSG:32634/32635) |
| tm3_west / _central / _east | Old Greek (Bessel 1841) | TM, λ₀ = −3° / 0° / +3° from Athens, k₀ 0.9999, FE 200 000, origin of northings φ₀ = 34° |
| greek_geo | Old Greek | φ, λ on Bessel 1841 (EPSG:4120, Greenwich longitudes) |
| hatt | Old Greek | azimuthal equidistant about the sheet centre (``hatt.py``) |

TM3 sources: Katsougiannopoulos & Vergos (2004) §5.2; Ντέρης (2014) §2.4.2 after Φωτίου
(2007); see docs/coords.md for the citations and the open questions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from .datum import DatumId
from .ellipsoid import BESSEL1841, GRS80, WGS84
from .hatt import ATHENS_MERIDIAN_RAD
from .models import SystemId
from .tm import TransverseMercator


class Projection(Protocol):
    def forward(self, lat: float, lon: float) -> tuple[float, float]: ...

    def inverse(self, x: float, y: float) -> tuple[float, float]: ...


@dataclass(frozen=True)
class SystemDef:
    id: SystemId
    datum: DatumId
    kind: Literal["geographic", "grid"]
    projection: TransverseMercator | None = None
    #: Half width of the normal zone in longitude about the central meridian (rad)
    half_width: float | None = None


_DEG = math.radians
TM3_K0 = 0.9999
TM3_FALSE_EASTING = 200_000.0
TM3_LAT0 = _DEG(34.0)


def _tm3(offset_deg: float) -> TransverseMercator:
    return TransverseMercator(
        BESSEL1841, ATHENS_MERIDIAN_RAD + _DEG(offset_deg), TM3_K0, TM3_FALSE_EASTING, 0.0, TM3_LAT0
    )


EGSA87_TM = TransverseMercator(GRS80, _DEG(24.0), 0.9996, 500_000.0)

SYSTEMS: dict[SystemId, SystemDef] = {
    "egsa87": SystemDef("egsa87", "ggrs87", "grid", EGSA87_TM, _DEG(6.0)),
    "ggrs87_geo": SystemDef("ggrs87_geo", "ggrs87", "geographic"),
    "wgs84_geo": SystemDef("wgs84_geo", "wgs84", "geographic"),
    "utm34": SystemDef(
        "utm34", "wgs84", "grid", TransverseMercator(WGS84, _DEG(21.0), 0.9996, 500_000.0), _DEG(3)
    ),
    "utm35": SystemDef(
        "utm35", "wgs84", "grid", TransverseMercator(WGS84, _DEG(27.0), 0.9996, 500_000.0), _DEG(3)
    ),
    "tm3_west": SystemDef("tm3_west", "greek", "grid", _tm3(-3.0), _DEG(1.5)),
    "tm3_central": SystemDef("tm3_central", "greek", "grid", _tm3(0.0), _DEG(1.5)),
    "tm3_east": SystemDef("tm3_east", "greek", "grid", _tm3(3.0), _DEG(1.5)),
    "greek_geo": SystemDef("greek_geo", "greek", "geographic"),
    "hatt": SystemDef("hatt", "greek", "grid"),
}

#: Tolerance outside a zone edge before a point is reported as outside its zone (zones overlap
#: in practice; e.g. UTM is routinely used ½° beyond its edge).
ZONE_MARGIN = _DEG(0.5)


def utm_zone(lon: float) -> int:
    """UTM zone number (1–60) for a Greenwich longitude in radians."""
    deg = math.degrees(math.remainder(lon, 2 * math.pi))
    return min(60, math.floor((deg + 180.0) / 6.0) + 1)


def tm3_zone(lon: float) -> Literal["tm3_west", "tm3_central", "tm3_east"] | None:
    """TM3 zone whose central meridian is nearest (None outside the three zones)."""
    d = math.degrees(lon - ATHENS_MERIDIAN_RAD)
    if d < -4.5 or d > 4.5:
        return None
    if d < -1.5:
        return "tm3_west"
    return "tm3_central" if d <= 1.5 else "tm3_east"


def outside_zone(system: SystemDef, lon: float) -> bool:
    if system.projection is None or system.half_width is None:
        return False
    d = abs(math.remainder(lon - system.projection.lon0, 2 * math.pi))
    return d > system.half_width + ZONE_MARGIN
