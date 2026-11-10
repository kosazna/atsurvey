"""Projection maths of the coordinate tools against independent truths.

* PROJ (pyproj) as an independent implementation: ΕΓΣΑ87, UTM 34/35, TM3, Hatt-as-aeqd.
* The EPSG Guidance Note 7-2 published Transverse Mercator example (exercises φ₀ ≠ 0).
* Round trips grid → geo → grid.
"""

from __future__ import annotations

import math
import random

import pytest

from atsurvey.core.coords import geodesic
from atsurvey.core.coords.convert import tissot
from atsurvey.core.coords.ellipsoid import (
    BESSEL1841,
    GRS80,
    Ellipsoid,
    ecef_to_geodetic,
    geodetic_to_ecef,
)
from atsurvey.core.coords.hatt import ATHENS_MERIDIAN_DEG, HattProjection
from atsurvey.core.coords.systems import SYSTEMS, tm3_zone, utm_zone
from atsurvey.core.coords.tm import TransverseMercator

pyproj = pytest.importorskip("pyproj")

R = math.radians
N_SAMPLES = 500
SUB_0_1_MM = 1e-4  # metres


def _samples(seed: int, lat: tuple[float, float], lon: tuple[float, float]):
    rnd = random.Random(seed)
    return [(rnd.uniform(*lat), rnd.uniform(*lon)) for _ in range(N_SAMPLES)]


def _proj_tm(definition: str):
    return pyproj.Transformer.from_crs(
        pyproj.CRS.from_proj4(definition).geodetic_crs,
        pyproj.CRS.from_proj4(definition),
        always_xy=True,
    )


# ------------------------------------------------------------------ Transverse Mercator


@pytest.mark.parametrize(
    ("system", "proj4", "lon_range"),
    [
        (
            "egsa87",
            "+proj=tmerc +lat_0=0 +lon_0=24 +k=0.9996 +x_0=500000 +y_0=0 +ellps=GRS80",
            (19.0, 30.0),
        ),
        ("utm34", "+proj=utm +zone=34 +ellps=WGS84", (18.0, 24.5)),
        ("utm35", "+proj=utm +zone=35 +ellps=WGS84", (23.5, 30.0)),
        (
            "tm3_west",
            f"+proj=tmerc +lat_0=34 +lon_0={ATHENS_MERIDIAN_DEG - 3} +k=0.9999 +x_0=200000 +y_0=0 +ellps=bessel",
            (19.0, 22.5),
        ),
        (
            "tm3_central",
            f"+proj=tmerc +lat_0=34 +lon_0={ATHENS_MERIDIAN_DEG} +k=0.9999 +x_0=200000 +y_0=0 +ellps=bessel",
            (22.0, 25.5),
        ),
        (
            "tm3_east",
            f"+proj=tmerc +lat_0=34 +lon_0={ATHENS_MERIDIAN_DEG + 3} +k=0.9999 +x_0=200000 +y_0=0 +ellps=bessel",
            (25.0, 29.9),
        ),
    ],
)
def test_tm_matches_proj_over_greece(system, proj4, lon_range):
    tm = SYSTEMS[system].projection
    assert tm is not None
    t = _proj_tm(proj4 + " +algo=poder_engsager +no_defs")
    worst = 0.0
    for lat, lon in _samples(hash(system) & 0xFFFF, (34.5, 42.0), lon_range):
        e, n = tm.forward(R(lat), R(lon))
        ee, nn = t.transform(lon, lat)
        worst = max(worst, abs(e - ee), abs(n - nn))
    assert worst < SUB_0_1_MM


def test_egsa87_matches_epsg_2100_from_database():
    """The CRS definition itself comes from the EPSG database, not from our transcription."""
    t = pyproj.Transformer.from_crs("EPSG:4121", "EPSG:2100", always_xy=True)
    tm = SYSTEMS["egsa87"].projection
    assert tm is not None
    for lat, lon in _samples(7, (34.8, 41.8), (19.5, 29.7)):
        e, n = tm.forward(R(lat), R(lon))
        ee, nn = t.transform(lon, lat)
        assert abs(e - ee) < SUB_0_1_MM and abs(n - nn) < SUB_0_1_MM


@pytest.mark.parametrize(
    "system", ["egsa87", "utm34", "utm35", "tm3_west", "tm3_central", "tm3_east"]
)
def test_tm_round_trip(system):
    tm = SYSTEMS[system].projection
    assert tm is not None
    lon0 = math.degrees(tm.lon0)
    for lat, dlon in _samples(11, (34.0, 42.0), (-4.0, 4.0)):
        e, n = tm.forward(R(lat), R(lon0 + dlon))
        lat2, lon2 = tm.inverse(e, n)
        e2, n2 = tm.forward(lat2, lon2)
        assert abs(e2 - e) < 1e-6 and abs(n2 - n) < 1e-6
        assert abs(lat2 - R(lat)) < 1e-12 and abs(lon2 - R(lon0 + dlon)) < 1e-12


def test_tm_ordnance_survey_published_example():
    """Ordnance Survey, "A guide to coordinate systems in Great Britain" (2020), Annex C worked
    example (National Grid, Airy 1830, φ₀ = 49° ≠ 0 like TM3): φ = 52°39′27.2531″N,
    λ = 1°43′4.5177″E → E = 651 409.903, N = 313 177.270 (published to 1 mm)."""
    airy = Ellipsoid("Airy 1830", 6377563.396, 299.3249646)
    tm = TransverseMercator(airy, R(-2.0), 0.9996012717, 400_000.0, -100_000.0, R(49.0))
    lat, lon = R(52 + 39 / 60 + 27.2531 / 3600), R(1 + 43 / 60 + 4.5177 / 3600)
    e, n = tm.forward(lat, lon)
    assert e == pytest.approx(651409.903, abs=0.0006)
    assert n == pytest.approx(313177.270, abs=0.0006)


def test_scale_and_convergence_match_proj_factors():
    p = pyproj.Proj("EPSG:2100")
    tm = SYSTEMS["egsa87"].projection
    assert tm is not None
    for lat, lon in _samples(3, (34.8, 41.8), (19.5, 29.7)):
        k, gamma = tm.scale_convergence(R(lat), R(lon))
        f = p.get_factors(lon, lat)
        assert k == pytest.approx(f.meridional_scale, abs=1e-10)
        assert math.degrees(gamma) == pytest.approx(f.meridian_convergence, abs=1e-8)


def test_scale_factor_on_central_meridian_is_k0_and_convergence_zero():
    tm = SYSTEMS["egsa87"].projection
    assert tm is not None
    k, gamma = tm.scale_convergence(R(38.0), R(24.0))
    assert k == pytest.approx(0.9996, abs=1e-15)
    assert gamma == pytest.approx(0.0, abs=1e-15)


def test_numerical_tissot_agrees_with_analytic_tm():
    """The finite-difference indicatrix (used for Hatt) reproduces Karney's analytic k, γ."""
    tm = SYSTEMS["egsa87"].projection
    assert tm is not None
    for lat, lon in [(35.2, 19.8), (38.0, 24.0), (41.5, 29.5)]:
        a, b, gamma = tissot(tm, "ggrs87", R(lat), R(lon))
        k, g = tm.scale_convergence(R(lat), R(lon))
        assert a == pytest.approx(k, abs=1e-9) and b == pytest.approx(k, abs=1e-9)
        assert gamma == pytest.approx(g, abs=1e-9)


def test_tm_refuses_far_longitudes():
    tm = SYSTEMS["egsa87"].projection
    assert tm is not None
    with pytest.raises(ValueError):
        tm.forward(R(38.0), R(80.0))
    with pytest.raises(ValueError):
        tm.forward(R(90.0), R(24.0))


# ----------------------------------------------------------------------------- Hatt


def _hatt_proj(lat0: float, lon0_greenwich: float):
    return _proj_tm(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0_greenwich} +x_0=0 +y_0=0 +ellps=bessel")


@pytest.mark.parametrize(("lat0", "lon0_athens"), [(38.25, 0.25), (35.25, 1.75), (41.25, -2.75)])
def test_hatt_matches_proj_aeqd(lat0, lon0_athens):
    lon0 = ATHENS_MERIDIAN_DEG + lon0_athens
    h = HattProjection(R(lat0), R(lon0))
    t = _hatt_proj(lat0, lon0)
    worst = 0.0
    for lat, lon in _samples(5, (lat0 - 0.5, lat0 + 0.5), (lon0 - 0.5, lon0 + 0.5)):
        x, y = h.forward(R(lat), R(lon))
        xx, yy = t.transform(lon, lat)
        worst = max(worst, abs(x - xx), abs(y - yy))
        lat2, lon2 = h.inverse(x, y)
        x2, y2 = h.forward(lat2, lon2)
        assert abs(x2 - x) < 1e-6 and abs(y2 - y) < 1e-6
    assert worst < 1e-5  # Vincenty vs Karney: sub-µm over a 30′ sheet


def test_hatt_preserves_distance_and_azimuth_from_centre():
    h = HattProjection(R(38.25), R(ATHENS_MERIDIAN_DEG + 0.25))
    lat, lon = geodesic.direct(BESSEL1841, h.lat0, h.lon0, R(60.0), 25_000.0)
    x, y = h.forward(lat, lon)
    assert math.hypot(x, y) == pytest.approx(25_000.0, abs=1e-6)
    assert math.degrees(math.atan2(x, y)) == pytest.approx(60.0, abs=1e-9)
    assert h.forward(h.lat0, h.lon0) == (0.0, 0.0)
    assert h.inverse(0.0, 0.0) == (h.lat0, h.lon0)


def test_hatt_tissot_radial_scale_is_one():
    """Azimuthal equidistant: scale along the radius is 1, across it 1 + s²/6R² (approx.)."""
    h = HattProjection(R(38.25), R(ATHENS_MERIDIAN_DEG + 0.25))
    lat, lon = h.inverse(0.0, 30_000.0)  # due north of the centre: radial = meridian
    a, b, _ = tissot(h, "greek", lat, lon)
    rr = BESSEL1841.gaussian_radius(h.lat0)
    assert b == pytest.approx(1.0, abs=1e-9)
    assert a - 1 == pytest.approx(30_000.0**2 / (6 * rr * rr), rel=0.02)


def test_geodesic_matches_proj_geod():
    g = pyproj.Geod(ellps="bessel")
    rnd = random.Random(2)
    for _ in range(200):
        lat1, lon1 = rnd.uniform(34, 42), rnd.uniform(19, 30)
        lat2, lon2 = lat1 + rnd.uniform(-1, 1), lon1 + rnd.uniform(-1, 1)
        s, az = geodesic.inverse(BESSEL1841, R(lat1), R(lon1), R(lat2), R(lon2))
        az_p, _, s_p = g.inv(lon1, lat1, lon2, lat2)
        assert s == pytest.approx(s_p, abs=1e-6)
        assert math.degrees(az) == pytest.approx(az_p, abs=1e-9)


# ------------------------------------------------------------------- ellipsoid / zones


def test_ecef_round_trip_and_proj():
    t = pyproj.Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)  # WGS84 3D → ECEF
    from atsurvey.core.coords.ellipsoid import WGS84

    for lat, lon in _samples(9, (34, 42), (19, 30))[:100]:
        h = 1234.5
        x, y, z = geodetic_to_ecef(WGS84, R(lat), R(lon), h)
        xx, yy, zz = t.transform(lon, lat, h)
        assert max(abs(x - xx), abs(y - yy), abs(z - zz)) < 1e-6
        lat2, lon2, h2 = ecef_to_geodetic(WGS84, x, y, z)
        assert abs(lat2 - R(lat)) < 1e-13 and abs(lon2 - R(lon)) < 1e-13 and abs(h2 - h) < 1e-6
    assert ecef_to_geodetic(GRS80, 0.0, 0.0, GRS80.b)[0] == pytest.approx(math.pi / 2)


def test_zone_helpers():
    assert utm_zone(R(23.7)) == 34
    assert utm_zone(R(24.1)) == 35
    assert tm3_zone(R(21.0)) == "tm3_west"
    assert tm3_zone(R(23.7)) == "tm3_central"
    assert tm3_zone(R(27.5)) == "tm3_east"
    assert tm3_zone(R(10.0)) is None
