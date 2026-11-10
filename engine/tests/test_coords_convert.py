"""Batch conversion pipeline: datum shifts, heights, hooks for official data, validation."""

from __future__ import annotations

import math
import time

import pytest
from pydantic import ValidationError

from atsurvey.core.coords import (
    ConvertRequest,
    CoordsError,
    PointInfoRequest,
    convert,
    point_info,
)
from atsurvey.core.coords import datum as datum_mod
from atsurvey.core.coords import hatt as hatt_mod
from atsurvey.core.coords.datum import GeographicOffsets
from atsurvey.core.coords.hatt import ATHENS_MERIDIAN_DEG, HattPolynomial, HattSheet
from atsurvey.core.coords.systems import SYSTEMS

pyproj = pytest.importorskip("pyproj")

R = math.radians
ATHENS = (23.7275, 37.9838)  # λ, φ degrees
GREECE = [(20.1, 39.6), (21.7, 38.2), ATHENS, (25.1, 35.3), (26.5, 41.1), (28.2, 36.4)]


def _req(src: str, dst: str, pts: list[dict], **kw) -> ConvertRequest:
    return ConvertRequest.model_validate({"src": src, "dst": dst, "points": pts, **kw})


def _geo(lon: float, lat: float, z: float | None = None, name: str = "P") -> dict:
    return {"name": name, "x": R(lon), "y": R(lat), "z": z}


def _codes(res) -> set[str]:
    return {i.code for i in res.issues}


# ---------------------------------------------------------------------- datum shifts


def test_wgs84_to_egsa87_matches_proj_epsg_1272():
    t = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2100", always_xy=True)
    res = convert(_req("wgs84_geo", "egsa87", [_geo(lon, lat) for lon, lat in GREECE]))
    for p, (lon, lat) in zip(res.points, GREECE, strict=True):
        e, n = t.transform(lon, lat)
        assert p.x == pytest.approx(e, abs=1e-4) and p.y == pytest.approx(n, abs=1e-4)
    assert res.approximate and res.accuracy_m == 1.5
    assert "COORD_APPROXIMATE" in _codes(res)
    assert res.datum_shift == ["EPSG:1272 (3 παράμετροι)"]


def test_egsa87_wgs84_round_trip():
    """With ellipsoidal heights the 3-parameter shift inverts exactly. Without heights each
    direction assumes h = 0 on its own ellipsoid (as PROJ does), so the ~10 m difference of
    the two ellipsoids leaves a residual of 1–2 mm on a round trip."""
    pts = [
        {"name": "A", "x": 476000.0, "y": 4205000.0, "z": 50.0},
        {"name": "B", "x": 300000.0, "y": 4600000.0, "z": 900.0},
    ]
    kw = {"height_in": "ellipsoidal", "height_out": "ellipsoidal"}
    there = convert(_req("egsa87", "wgs84_geo", pts, **kw))
    back = convert(_req("wgs84_geo", "egsa87", [p.model_dump() for p in there.points], **kw))
    for a, b in zip(pts, back.points, strict=True):
        assert b.x == pytest.approx(a["x"], abs=1e-6) and b.y == pytest.approx(a["y"], abs=1e-6)
        assert b.z == pytest.approx(a["z"], abs=1e-6)
    flat = [{"x": p["x"], "y": p["y"]} for p in pts]
    there = convert(_req("egsa87", "wgs84_geo", flat))
    back = convert(_req("wgs84_geo", "egsa87", [p.model_dump() for p in there.points]))
    for a, b in zip(flat, back.points, strict=True):
        assert b.x == pytest.approx(a["x"], abs=3e-3) and b.y == pytest.approx(a["y"], abs=3e-3)


def test_egsa87_to_utm34_matches_proj():
    t = pyproj.Transformer.from_crs("EPSG:2100", "EPSG:32634", always_xy=True)
    pts = [{"x": 476000.0, "y": 4205000.0}, {"x": 250000.0, "y": 4400000.0}]
    res = convert(_req("egsa87", "utm34", pts))
    for p, q in zip(res.points, pts, strict=True):
        e, n = t.transform(q["x"], q["y"])
        assert p.x == pytest.approx(e, abs=1e-4) and p.y == pytest.approx(n, abs=1e-4)


def test_greek_to_ggrs87_matches_proj_epsg_1891():
    t = pyproj.Transformer.from_crs("EPSG:4120", "EPSG:4121", always_xy=True)
    res = convert(_req("greek_geo", "ggrs87_geo", [_geo(lon, lat) for lon, lat in GREECE]))
    for p, (lon, lat) in zip(res.points, GREECE, strict=True):
        lon2, lat2 = t.transform(lon, lat)
        assert p.x == pytest.approx(R(lon2), abs=1e-11) and p.y == pytest.approx(R(lat2), abs=1e-11)
    assert res.accuracy_m == 5.0
    assert {"COORD_APPROXIMATE", "COORD_OLD_DATUM_LOCAL_FIT"} <= _codes(res)


def test_tm3_to_egsa87_chain_matches_proj():
    """TM3 grid → Old Greek φλ (our TM, PROJ-verified) → EPSG:1891 → ΕΓΣΑ87, vs PROJ."""
    tm3 = pyproj.Transformer.from_crs(
        f"+proj=tmerc +lat_0=34 +lon_0={ATHENS_MERIDIAN_DEG} +k=0.9999 +x_0=200000 +y_0=0 "
        "+ellps=bessel +no_defs",
        "EPSG:4120",
        always_xy=True,
    )
    to_egsa = pyproj.Transformer.from_crs("EPSG:4120", "EPSG:2100", always_xy=True)
    pts = [{"x": 201234.5, "y": 440000.0}, {"x": 150000.0, "y": 300000.0}]
    res = convert(_req("tm3_central", "egsa87", pts))
    for p, q in zip(res.points, pts, strict=True):
        e, n = to_egsa.transform(*tm3.transform(q["x"], q["y"]))
        assert p.x == pytest.approx(e, abs=1e-4) and p.y == pytest.approx(n, abs=1e-4)
    assert res.accuracy_m == 5.0


def test_projection_only_conversion_is_exact_and_unflagged():
    res = convert(_req("egsa87", "ggrs87_geo", [{"x": 476000.0, "y": 4205000.0}]))
    assert not res.approximate and res.accuracy_m is None and res.datum_shift == []
    assert "COORD_APPROXIMATE" not in _codes(res)


def test_tm3_zone_change_same_datum_is_exact():
    res = convert(_req("tm3_central", "tm3_east", [{"x": 300000.0, "y": 450000.0}]))
    assert not res.approximate
    back = convert(_req("tm3_east", "tm3_central", [res.points[0].model_dump()]))
    assert back.points[0].x == pytest.approx(300000.0, abs=1e-6)


# ------------------------------------------------------------------- official hooks


def test_official_method_reports_hepos_unavailable():
    with pytest.raises(CoordsError) as exc:
        convert(_req("wgs84_geo", "egsa87", [_geo(*ATHENS)], datum_method="official"))
    assert exc.value.code == "COORD_HEPOS_UNAVAILABLE"


def test_hepos_hook_is_used_when_installed(monkeypatch):
    fake = GeographicOffsets("ggrs87", "wgs84", "HEPOS (test)", 0.08, 0.0, 0.0, approximate=False)
    monkeypatch.setattr(datum_mod, "HEPOS_TRANSFORMATION", fake)
    res = convert(_req("wgs84_geo", "ggrs87_geo", [_geo(*ATHENS)], datum_method="official"))
    assert res.datum_shift == ["HEPOS (test)"]
    assert res.points[0].x == pytest.approx(R(ATHENS[0]), abs=1e-15)
    assert "COORD_APPROXIMATE" not in _codes(res)


def test_official_method_refused_for_old_datum_without_polynomials():
    with pytest.raises(CoordsError) as exc:
        convert(_req("tm3_central", "egsa87", [{"x": 2e5, "y": 4e5}], datum_method="official"))
    assert exc.value.code == "COORD_NO_OFFICIAL_SHIFT"


def test_hatt_sheet_code_without_table():
    with pytest.raises(CoordsError) as exc:
        convert(_req("hatt", "greek_geo", [{"x": 0, "y": 0}], src_hatt={"sheet": "6124"}))
    assert exc.value.code == "COORD_HATT_TABLE_MISSING"
    assert exc.value.params == {"sheet": "6124"}


def test_hatt_requires_origin():
    with pytest.raises(CoordsError) as exc:
        convert(_req("hatt", "greek_geo", [{"x": 0, "y": 0}]))
    assert exc.value.code == "COORD_HATT_ORIGIN_REQUIRED"


def test_hatt_polynomial_hook(monkeypatch):
    """Once the table is loaded, 'official' applies the sheet polynomial grid to grid."""
    poly = HattPolynomial(400000.0, 1.0, 0.0, 0.0, 0.0, 0.0, 4200000.0, 0.0, 1.0, 0.0, 0.0, 0.0)
    sheet = HattSheet("T1", "Test", R(38.25), R(0.25), poly)
    monkeypatch.setattr(hatt_mod, "HATT_SHEETS", {"T1": sheet})
    res = convert(
        _req(
            "hatt",
            "egsa87",
            [{"x": 10.0, "y": 20.0, "z": 5.0}],
            src_hatt={"sheet": "T1"},
            datum_method="official",
        )
    )
    p = res.points[0]
    assert (p.x, p.y, p.z) == pytest.approx((400010.0, 4200020.0, 5.0))
    assert res.datum_shift == ["ΟΚΧΕ Hatt φύλλο T1"] and res.src == "hatt"
    # the sheet centre also defines the projection for the approximate path
    approx = convert(_req("hatt", "greek_geo", [{"x": 0, "y": 0}], src_hatt={"sheet": "T1"}))
    assert approx.points[0].y == pytest.approx(R(38.25))
    assert approx.points[0].x == pytest.approx(R(ATHENS_MERIDIAN_DEG + 0.25))


def test_hatt_polynomial_quadratic_terms():
    poly = HattPolynomial(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    assert poly.apply(2.0, 3.0) == (1 + 4 + 9 + 16 + 45 + 36, 4 + 9 + 6)


def test_hatt_origin_meridian_choice():
    origin = {"lat0": R(38.25), "lon0": R(0.25)}
    a = convert(_req("hatt", "greek_geo", [{"x": 0, "y": 0}], src_hatt=origin))
    b = convert(
        _req(
            "hatt",
            "greek_geo",
            [{"x": 0, "y": 0}],
            src_hatt={
                "lat0": R(38.25),
                "lon0": R(ATHENS_MERIDIAN_DEG + 0.25),
                "meridian": "greenwich",
            },
        )
    )
    assert a.points[0].x == pytest.approx(b.points[0].x, abs=1e-15)
    far = convert(_req("hatt", "greek_geo", [{"x": 45_000, "y": 0, "name": "F"}], src_hatt=origin))
    assert "COORD_HATT_FAR" in _codes(far)


# ----------------------------------------------------------------------------- heights


def test_orthometric_heights_pass_through_datum_shift():
    res = convert(_req("wgs84_geo", "egsa87", [_geo(*ATHENS, z=123.456)]))
    assert res.points[0].z == 123.456


def test_ellipsoidal_heights_follow_the_shift():
    t = pyproj.Transformer.from_pipeline(
        "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad "
        "+step +proj=cart +ellps=WGS84 +step +inv +proj=helmert +x=-199.87 +y=74.79 +z=246.62 "
        "+step +inv +proj=cart +ellps=GRS80 +step +proj=unitconvert +xy_in=rad +xy_out=deg"
    )
    res = convert(
        _req(
            "wgs84_geo",
            "ggrs87_geo",
            [_geo(*ATHENS, z=150.0)],
            height_in="ellipsoidal",
            height_out="ellipsoidal",
        )
    )
    lon, lat, h = t.transform(*ATHENS, 150.0)
    p = res.points[0]
    assert p.z == pytest.approx(h, abs=1e-6)
    assert p.x == pytest.approx(R(lon), abs=1e-12) and p.y == pytest.approx(R(lat), abs=1e-12)


def test_height_kind_change_needs_constant_n():
    pts = [_geo(*ATHENS, z=150.0)]
    with pytest.raises(CoordsError) as exc:
        convert(_req("wgs84_geo", "egsa87", pts, height_in="ellipsoidal"))
    assert exc.value.code == "COORD_GEOID_REQUIRED"
    res = convert(_req("wgs84_geo", "egsa87", pts, height_in="ellipsoidal", geoid_undulation=36.5))
    assert res.points[0].z == pytest.approx(113.5)
    assert "COORD_CONSTANT_GEOID" in _codes(res)
    up = convert(
        _req(
            "egsa87",
            "egsa87",
            [{"x": 4.7e5, "y": 4.2e6, "z": 100.0}],
            height_out="ellipsoidal",
            geoid_undulation=30.0,
        )
    )
    assert up.points[0].z == pytest.approx(130.0)


def test_points_without_heights_stay_without():
    res = convert(_req("wgs84_geo", "egsa87", [_geo(*ATHENS)], height_in="ellipsoidal"))
    assert res.points[0].z is None


# ------------------------------------------------------------------- per-point issues


def test_bad_point_is_reported_and_others_converted():
    pts = [_geo(*ATHENS, name="OK"), {"name": "DEG", "x": 23.7, "y": 37.9}]  # degrees, not rad
    res = convert(_req("wgs84_geo", "egsa87", pts))
    assert res.points[0].x is not None
    assert res.points[1].x is None and res.points[1].y is None
    failed = next(i for i in res.issues if i.code == "COORD_POINT_FAILED")
    assert failed.severity == "error" and failed.params["points"] == ["DEG"]
    assert failed.params["count"] == 1


def test_outside_zone_warning_is_aggregated():
    pts = [_geo(28.0, 36.5, name=f"P{i}") for i in range(8)]
    res = convert(_req("wgs84_geo", "utm34", pts))
    issue = next(i for i in res.issues if i.code == "COORD_OUTSIDE_ZONE")
    assert issue.params["count"] == 8 and len(issue.params["points"]) == 5
    assert issue.params["system"] == "utm34"


# ------------------------------------------------------------------------- validation


def test_request_bounds():
    with pytest.raises(ValidationError):
        _req("egsa87", "wgs84_geo", [])
    with pytest.raises(ValidationError):
        _req("egsa87", "wgs84_geo", [{"x": 0, "y": 0}] * 10_001)
    with pytest.raises(ValidationError):
        _req("egsa87", "wgs84_geo", [{"x": float("nan"), "y": 0}])
    with pytest.raises(ValidationError):
        _req("egsa87", "nowhere", [{"x": 0, "y": 0}])
    with pytest.raises(ValidationError):
        _req(
            "hatt", "egsa87", [{"x": 0, "y": 0}], src_hatt={"sheet": "1", "lat0": 0.66, "lon0": 0.0}
        )
    with pytest.raises(ValidationError):
        _req("egsa87", "egsa87", [{"x": 0, "y": 0}], geoid_undulation=500.0)


def test_ten_thousand_points_in_reasonable_time():
    pts = [{"x": 400000.0 + i, "y": 4200000.0 + i} for i in range(10_000)]
    t0 = time.perf_counter()
    res = convert(_req("egsa87", "wgs84_geo", pts))
    assert time.perf_counter() - t0 < 5.0
    assert all(p.x is not None for p in res.points)


# ------------------------------------------------------------------------- point info


def test_point_info_egsa87():
    p = pyproj.Proj("EPSG:2100")
    info = point_info(
        PointInfoRequest.model_validate(
            {
                "system": "egsa87",
                "point": {"x": 300000.0, "y": 4300000.0, "z": 500.0},
                "geoid_undulation": 40.0,
            }
        )
    )
    lon, lat = p(300000.0, 4300000.0, inverse=True)
    f = p.get_factors(lon, lat)
    assert info.lat == pytest.approx(R(lat), abs=1e-12)
    assert info.scale_factor == pytest.approx(f.meridional_scale, abs=1e-10)
    assert math.degrees(info.convergence or 0) == pytest.approx(f.meridian_convergence, abs=1e-8)
    r = 6.38e6
    assert info.elevation_factor == pytest.approx(r / (r + 540.0), abs=2e-7)
    assert info.combined_factor == pytest.approx(
        (info.scale_factor or 0) * (info.elevation_factor or 0)
    )
    assert info.utm_zone == 34 and info.inside_zone and info.lon_athens is None
    # the legacy textbook formula of geodesy.py agrees to ~1e-7
    from atsurvey.core.geodesy import egsa87_point_scale

    assert info.scale_factor == pytest.approx(egsa87_point_scale(300000.0), abs=2e-7)


def test_point_info_geographic_and_hatt():
    geo = point_info(
        PointInfoRequest.model_validate(
            {"system": "greek_geo", "point": {"x": R(21.0), "y": R(38.0)}}
        )
    )
    assert geo.scale_factor is None and geo.convergence is None and geo.x is None
    assert geo.tm3_zone == "tm3_west"
    assert geo.lon_athens == pytest.approx(R(21.0 - ATHENS_MERIDIAN_DEG))
    hatt = point_info(
        PointInfoRequest.model_validate(
            {
                "system": "hatt",
                "point": {"x": 20000.0, "y": 0.0, "z": 10.0},
                "hatt": {"lat0": R(38.25), "lon0": R(0.25)},
            }
        )
    )
    assert hatt.scale_factor is None and hatt.combined_factor is None
    assert hatt.scale_min == pytest.approx(1.0, abs=1e-9)
    assert (hatt.scale_max or 0) > 1.0 and hatt.inside_zone
    assert "COORD_GEOID_ASSUMED_ZERO" in {i.code for i in hatt.issues}


def test_point_info_outside_zone():
    info = point_info(
        PointInfoRequest.model_validate(
            {"system": "utm34", "point": {"x": 900000.0, "y": 4000000.0}}
        )
    )
    assert not info.inside_zone


def test_every_system_round_trips_through_geographic():
    hatt = {"lat0": R(38.25), "lon0": R(0.25)}
    for sid, sd in SYSTEMS.items():
        if sd.kind == "geographic":
            continue
        start = {"x": 1234.5, "y": -2345.6} if sid == "hatt" else None
        if start is None:
            geo = convert(_req("wgs84_geo", sid, [_geo(*ATHENS)]))
            start = geo.points[0].model_dump(exclude={"name", "z"})
        kw = {"src_hatt": hatt, "dst_hatt": hatt} if sid == "hatt" else {}
        target = {"ggrs87": "ggrs87_geo", "wgs84": "wgs84_geo", "greek": "greek_geo"}[sd.datum]
        there = convert(_req(sid, target, [start], **kw))
        back = convert(_req(target, sid, [there.points[0].model_dump()], **kw))
        assert back.points[0].x == pytest.approx(start["x"], abs=1e-6), sid
        assert back.points[0].y == pytest.approx(start["y"], abs=1e-6), sid


def test_every_coord_code_has_a_greek_template():
    import re
    from pathlib import Path

    from atsurvey.core.messages import EL, localize

    src = Path(__file__).parents[1] / "src" / "atsurvey" / "core" / "coords"
    codes = set(re.findall(r'"(COORD_[A-Z_]+)"', "".join(p.read_text() for p in src.glob("*.py"))))
    assert codes and codes <= EL.keys()
    res = convert(_req("wgs84_geo", "egsa87", [{"name": "X", "x": 9.0, "y": 9.0}]))
    texts = [localize(i, "el") for i in res.issues]
    assert any("X" in t and "δεν μετατράπηκαν" in t for t in texts)


def test_user_entered_hatt_polynomial():
    coeffs = [400000.0, 1.0, 0.0, 0.0, 0.0, 0.0, 4200000.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    spec = {"lat0": R(38.25), "lon0": R(0.25), "coefficients": coeffs}
    res = convert(
        _req("hatt", "egsa87", [{"x": 10.0, "y": 20.0}], src_hatt=spec, datum_method="official")
    )
    assert (res.points[0].x, res.points[0].y) == pytest.approx((400010.0, 4200020.0))
    assert res.datum_shift == ["Πολυώνυμο Hatt → ΕΓΣΑ87 (συντελεστές χρήστη)"]
    assert not res.approximate
    # without "official" the same spec runs the approximate EPSG path through φ, λ
    approx = convert(_req("hatt", "egsa87", [{"x": 10.0, "y": 20.0}], src_hatt=spec))
    assert approx.approximate and approx.accuracy_m == 5.0
    with pytest.raises(ValidationError):
        _req("hatt", "egsa87", [{"x": 0, "y": 0}], src_hatt={**spec, "coefficients": [1.0] * 11})
    with pytest.raises(CoordsError) as exc:  # the polynomials only go Hatt → ΕΓΣΑ87
        convert(
            _req("egsa87", "hatt", [{"x": 4e5, "y": 4.2e6}], dst_hatt=spec, datum_method="official")
        )
    assert exc.value.code == "COORD_NO_OFFICIAL_SHIFT"
