"""HEPOS HTRS07 ↔ ΕΓΣΑ87: the official worked example (ΚΤΗΜΑΤΟΛΟΓΙΟ / ΑΠΘ 2008, pp. 8–12).

The correction grids may not be redistributed, so the committed tests use synthetic grids;
the full official example runs only where ``ATSURVEY_HEPOS_GRID_DIR`` points to the real
files (it is skipped otherwise). No grid values are embedded here.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from atsurvey.core.coords import ConvertRequest, convert, hepos
from atsurvey.core.coords import datum as datum_mod
from atsurvey.core.coords.ellipsoid import GRS80, ecef_to_geodetic, geodetic_to_ecef

# Official example, forward (HTRS07 → ΕΓΣΑ87)
XYZ = (4382064.771, 2023782.319, 4155326.131)
STEP1 = (4382266.647, 2023708.046, 4155081.709)
TM07_POS = (566446.108, 2529618.096)
BEFORE_GRID = (566296.660, 4529332.491)
FINAL = (566296.538, 4529332.307)
# Official example, inverse (ΕΓΣΑ87 → HTRS07), from FINAL with h = 6.501
INV_STEP3 = (4382064.931, 2023782.257, 4155325.993)
INV_STEP5 = (566445.986, 2529617.912)
INV_FINAL_TM07 = (566446.108, 2529618.096)
INV_FINAL_LAT = (40, 54, 53.90608)
INV_FINAL_LON = (24, 47, 20.59229)
MM = 1e-3


def _dms(d: int, m: int, s: float) -> float:
    return math.radians(d + m / 60 + s / 3600)


def test_similarity_step_matches_official_example():
    out = hepos._similarity(*XYZ, sign=1.0)
    assert out == pytest.approx(STEP1, abs=MM)


def test_tm07_position_and_tm87_before_grid():
    lat, lon, _ = ecef_to_geodetic(GRS80, *XYZ)
    assert hepos.TM07.forward(lat, lon) == pytest.approx(TM07_POS, abs=MM)
    lat1, lon1, _ = ecef_to_geodetic(GRS80, *hepos._similarity(*XYZ, sign=1.0))
    assert hepos.TM87.forward(lat1, lon1) == pytest.approx(BEFORE_GRID, abs=MM)


def test_inverse_steps_match_official_example():
    lat, lon = hepos.TM87.inverse(*FINAL)
    x = hepos._similarity(*geodetic_to_ecef(GRS80, lat, lon, 6.501), sign=-1.0)
    assert x == pytest.approx(INV_STEP3, abs=MM)
    lat1, lon1, _ = ecef_to_geodetic(GRS80, *x)
    assert hepos.TM07.forward(lat1, lon1) == pytest.approx(INV_STEP5, abs=MM)


# ------------------------------------------------------------------- synthetic grids


def _grid_text(rows: int, cols: int, spacing: float, n0: float, e0: float, fn) -> str:
    head = [str(rows), str(cols), f"{spacing:.2f}", f"{n0:.3f}", f"{e0:.3f}"]
    vals = [
        f"{fn(e0 + j * spacing, n0 + i * spacing):.4f}" for i in range(rows) for j in range(cols)
    ]
    return "\r\n".join(head) + "\r\n" + " ".join(vals) + "\r\n"


def test_parse_and_bilinear_is_exact_for_bilinear_surfaces():
    def f(e, n):
        return 3.0 + 2e-3 * (e - 1000) - 1e-3 * (n - 5000) + 1e-7 * (e - 1000) * (n - 5000)

    g = hepos.parse_grid(_grid_text(4, 5, 100.0, 5000.0, 1000.0, f))
    assert (g.rows, g.cols) == (4, 5)
    for e, n in [(1000.0, 5000.0), (1234.5, 5111.1), (1400.0, 5300.0), (1399.9, 5299.9)]:
        assert g.interpolate(e, n) == pytest.approx(f(e, n) / 100, abs=1e-9)  # cm → m
    with pytest.raises(ValueError, match="outside"):
        g.interpolate(999.0, 5000.0)
    with pytest.raises(ValueError, match="outside"):
        g.interpolate(1000.0, 5300.1)


def test_parse_rejects_truncated_files():
    with pytest.raises(ValueError):
        hepos.parse_grid("3 3 100 0")
    with pytest.raises(ValueError):
        hepos.parse_grid("3 3 100 0 0 1 2 3")


def _write_constant_grids(directory: Path, de_cm: float, dn_cm: float) -> None:
    for name, value in zip(hepos.GRID_FILES, (de_cm, dn_cm), strict=True):
        text = _grid_text(10, 10, 2000.0, 2520000.0, 556000.0, lambda e, n, v=value: v)
        (directory / name).write_text(text, encoding="ascii")


def test_forward_and_inverse_with_synthetic_grid(tmp_path):
    _write_constant_grids(tmp_path, -12.0, -18.0)
    t = hepos.load(tmp_path)
    lat, lon, h = ecef_to_geodetic(GRS80, *XYZ)
    lat2, lon2, _ = t.forward((lat, lon, h))
    e, n = hepos.TM87.forward(lat2, lon2)
    assert (e, n) == pytest.approx((BEFORE_GRID[0] - 0.12, BEFORE_GRID[1] - 0.18), abs=MM)
    back = t.inverse((lat2, lon2, 6.5))
    e07, n07 = hepos.TM07.forward(back[0], back[1])
    assert (e07, n07) == pytest.approx(TM07_POS, abs=2 * MM)


def test_environment_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(datum_mod, "HEPOS_TRANSFORMATION", None)
    monkeypatch.delenv(hepos.GRID_ENV, raising=False)
    assert hepos.from_environment() is None
    _write_constant_grids(tmp_path, 0.0, 0.0)
    monkeypatch.setenv(hepos.GRID_ENV, str(tmp_path))
    hepos._load_cached.cache_clear()
    lat, lon, h = ecef_to_geodetic(GRS80, *XYZ)
    req = ConvertRequest.model_validate(
        {
            "src": "wgs84_geo",
            "dst": "egsa87",
            "points": [{"x": lon, "y": lat, "z": h}],
            "datum_method": "official",
            "height_in": "ellipsoidal",
            "height_out": "ellipsoidal",
        }
    )
    res = convert(req)
    assert not res.approximate and res.accuracy_m == hepos.ACCURACY_M
    assert "COORD_APPROXIMATE" not in {i.code for i in res.issues}
    p = res.points[0]
    assert (p.x, p.y) == pytest.approx(BEFORE_GRID, abs=MM)
    hepos._load_cached.cache_clear()


# --------------------------------------------------------------- real grids (optional)

_REAL = hepos.from_environment()


@pytest.mark.skipif(
    _REAL is None, reason="official HEPOS grids not installed (ATSURVEY_HEPOS_GRID_DIR)"
)
def test_official_example_with_real_grids():
    assert _REAL is not None
    lat, lon, h = ecef_to_geodetic(GRS80, *XYZ)
    lat2, lon2, _ = _REAL.forward((lat, lon, h))
    assert hepos.TM87.forward(lat2, lon2) == pytest.approx(FINAL, abs=MM)
    lat_i, lon_i = hepos.TM87.inverse(*FINAL)
    back = _REAL.inverse((lat_i, lon_i, 6.501))
    assert hepos.TM07.forward(back[0], back[1]) == pytest.approx(INV_FINAL_TM07, abs=MM)
    assert back[0] == pytest.approx(_dms(*INV_FINAL_LAT), abs=1e-10)
    assert back[1] == pytest.approx(_dms(*INV_FINAL_LON), abs=1e-10)
