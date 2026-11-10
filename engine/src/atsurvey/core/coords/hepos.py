"""Official HEPOS transformation HTRS07 ↔ ΕΓΣΑ87 (mainland Greece and islands except Kastelorizo).

Reference: Kotsakis, Katsambalos, Gianniou, «Μοντέλο Μετασχηματισμού Συντεταγμένων μεταξύ
HTRS07 και ΕΓΣΑ87 — Βασική Μεθοδολογία και αριθμητικά παραδείγματα», ΚΤΗΜΑΤΟΛΟΓΙΟ Α.Ε. / ΑΠΘ
(2008), with the 2 km correction grids ``dE_2km_V1-0.grd``, ``dN_2km_V1-0.grd`` (2009).

Forward (HTRS07 → ΕΓΣΑ87):
1. (X, Y, Z) HTRS07 → 7-parameter similarity, coordinate-frame rotation convention
   X' = T + (1 + δs)·R·X with R = [[1, εz, −εy], [−εz, 1, εx], [εy, −εx, 1]]
   (EPSG method 1032; matches the official worked example to 1 mm).
2. (X', Y', Z') → (φ', λ', h') on GRS80 → TM87 (E', N').
3. δE, δN by bilinear interpolation of the grids at the point's **TM07** position (TM87 with
   FN = −2 000 000 m) computed from the original HTRS07 coordinates; E = E' + δE, N = N' + δN.

Inverse (as specified, not iterated): the same similarity with all seven parameters negated,
TM07 (E', N') of the result, grid corrections interpolated there and **subtracted**.

The grids are NOT bundled: their terms of use (hepos.gr) forbid redistribution. A server
operator who holds them sets ``ATSURVEY_HEPOS_GRID_DIR`` to the folder with both files; without
it the "official" method reports ``COORD_HEPOS_UNAVAILABLE``. Nominal accuracy ≈ 8 cm RMS
(Katsambalos et al., 2009); the transformed h is not better than 1 m.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .datum import DatumId
from .ellipsoid import GRS80, ecef_to_geodetic, geodetic_to_ecef
from .tm import TransverseMercator

ARCSEC = math.pi / (180 * 3600)

#: Official similarity parameters HTRS07 → ΕΓΣΑ87.
TX, TY, TZ = 203.437, -73.461, -243.594
EX, EY, EZ = -0.170 * ARCSEC, -0.060 * ARCSEC, -0.151 * ARCSEC
DS = -0.294e-6

TM87 = TransverseMercator(GRS80, math.radians(24.0), 0.9996, 500_000.0)
TM07 = TransverseMercator(GRS80, math.radians(24.0), 0.9996, 500_000.0, -2_000_000.0)

GRID_ENV = "ATSURVEY_HEPOS_GRID_DIR"
GRID_FILES = ("dE_2km_V1-0.grd", "dN_2km_V1-0.grd")
ACCURACY_M = 0.08
_CM = 0.01

Geo = tuple[float, float, float]


def _similarity(x: float, y: float, z: float, sign: float) -> tuple[float, float, float]:
    """Coordinate-frame similarity with the official parameters (sign = −1: inverse)."""
    ex, ey, ez, s = sign * EX, sign * EY, sign * EZ, 1.0 + sign * DS
    return (
        sign * TX + s * (x + ez * y - ey * z),
        sign * TY + s * (-ez * x + y + ex * z),
        sign * TZ + s * (ey * x - ex * y + z),
    )


@dataclass(frozen=True)
class CorrectionGrid:
    """Regular grid of node values (m) on TM07: rows S→N, columns W→E from the SW node."""

    rows: int
    cols: int
    spacing: float
    north0: float
    east0: float
    values: tuple[float, ...]

    def interpolate(self, e: float, n: float) -> float:
        """Bilinear interpolation from the four surrounding nodes."""
        u = (e - self.east0) / self.spacing
        v = (n - self.north0) / self.spacing
        if not (0.0 <= u <= self.cols - 1 and 0.0 <= v <= self.rows - 1):
            raise ValueError("Point outside the HEPOS correction grid")
        i, j = min(int(v), self.rows - 2), min(int(u), self.cols - 2)
        fu, fv = u - j, v - i
        k = i * self.cols + j
        z00, z01 = self.values[k], self.values[k + 1]
        z10, z11 = self.values[k + self.cols], self.values[k + self.cols + 1]
        return (z00 * (1 - fu) + z01 * fu) * (1 - fv) + (z10 * (1 - fu) + z11 * fu) * fv


def parse_grid(text: str) -> CorrectionGrid:
    """ASCII grid of the HEPOS package: rows, cols, spacing, N_sw, E_sw, then values in cm."""
    tokens = text.split()
    if len(tokens) < 5:
        raise ValueError("HEPOS grid file: header incomplete")
    rows, cols = int(tokens[0]), int(tokens[1])
    spacing, north0, east0 = float(tokens[2]), float(tokens[3]), float(tokens[4])
    values = tuple(float(t) * _CM for t in tokens[5:])
    if rows < 2 or cols < 2 or spacing <= 0 or len(values) != rows * cols:
        raise ValueError(f"HEPOS grid file: expected {rows}×{cols} values, found {len(values)}")
    return CorrectionGrid(rows, cols, spacing, north0, east0, values)


@dataclass(frozen=True)
class HeposTransformation:
    """``DatumShift`` from "wgs84" (read as HTRS07 on GRS80) to "ggrs87"."""

    grid_e: CorrectionGrid
    grid_n: CorrectionGrid
    src: DatumId = "wgs84"
    dst: DatumId = "ggrs87"
    label: str = "HEPOS HTRS07 → ΕΓΣΑ87 (επίσημος, κάνναβοι 2 km)"
    accuracy_m: float = ACCURACY_M
    approximate: bool = False

    def _corrections(self, e07: float, n07: float) -> tuple[float, float]:
        return self.grid_e.interpolate(e07, n07), self.grid_n.interpolate(e07, n07)

    def forward(self, p: Geo) -> Geo:
        lat, lon, h = p
        e07, n07 = TM07.forward(lat, lon)
        x, y, z = _similarity(*geodetic_to_ecef(GRS80, lat, lon, h), sign=1.0)
        lat1, lon1, h1 = ecef_to_geodetic(GRS80, x, y, z)
        e, n = TM87.forward(lat1, lon1)
        de, dn = self._corrections(e07, n07)
        lat2, lon2 = TM87.inverse(e + de, n + dn)
        return lat2, lon2, h1

    def inverse(self, p: Geo) -> Geo:
        lat, lon, h = p
        x, y, z = _similarity(*geodetic_to_ecef(GRS80, lat, lon, h), sign=-1.0)
        lat1, lon1, h1 = ecef_to_geodetic(GRS80, x, y, z)
        e07, n07 = TM07.forward(lat1, lon1)
        de, dn = self._corrections(e07, n07)
        lat2, lon2 = TM07.inverse(e07 - de, n07 - dn)
        return lat2, lon2, h1


def load(directory: str | Path) -> HeposTransformation:
    d = Path(directory)
    grids = [parse_grid((d / name).read_text(encoding="ascii")) for name in GRID_FILES]
    return HeposTransformation(grids[0], grids[1])


@lru_cache(maxsize=1)
def _load_cached(directory: str) -> HeposTransformation:
    return load(directory)


def from_environment() -> HeposTransformation | None:
    """The transformation if ``ATSURVEY_HEPOS_GRID_DIR`` points to readable grids, else None."""
    directory = os.environ.get(GRID_ENV, "").strip()
    if not directory or not all((Path(directory) / f).is_file() for f in GRID_FILES):
        return None
    return _load_cached(directory)
