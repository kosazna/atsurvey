"""Batch setting out and the as-staked check (core/setout.py)."""

import math

import pytest

from atsurvey.core.cogo import polar
from atsurvey.core.cogo_models import XY, PolarRequest
from atsurvey.core.geodesy import egsa87_line_scale, height_difference
from atsurvey.core.models import ReductionSettings
from atsurvey.core.setout import (
    CheckRequest,
    ReferenceLine,
    SetoutRequest,
    SPoint,
    check_staked,
    setout_points,
)
from atsurvey.core.units import from_rad, to_rad


def gon(rad):
    return from_rad(rad, "gon")


ST = SPoint(name="S1", x=1000.0, y=1000.0, z=100.0)
BS_NORTH = SPoint(name="S2", x=1000.0, y=1100.0, z=101.0)


# --------------------------------------------------------------------------- setting out


def test_hand_computed_polar_values():
    req = SetoutRequest(
        station=ST,
        backsight=BS_NORTH,
        instrument_height=1.5,
        target_height=1.8,
        points=[
            SPoint(name="P1", x=1100.0, y=1100.0, z=102.0),  # NE, 50 gon
            SPoint(name="P2", x=900.0, y=1000.0),  # W, 300 gon
            SPoint(name="P3", x=1030.0, y=960.0, z=99.0),  # 3-4-5 triangle, 50 m
        ],
    )
    r = setout_points(req)
    assert gon(r.zero_azimuth) == pytest.approx(0.0, abs=1e-12)
    assert r.backsight_distance == pytest.approx(100.0)
    p1, p2, p3 = r.rows
    assert gon(p1.direction) == pytest.approx(50.0, abs=1e-10)
    assert p1.distance == pytest.approx(100 * math.sqrt(2), abs=1e-12)
    assert (p1.de, p1.dn, p1.dz) == pytest.approx((100.0, 100.0, 2.0))
    # V = ΔZ − hi + ht = 2 − 1.5 + 1.8 = 2.3
    assert p1.zenith == pytest.approx(math.atan2(100 * math.sqrt(2), 2.3), abs=1e-15)
    assert p1.slope_distance == pytest.approx(math.hypot(100 * math.sqrt(2), 2.3))
    assert gon(p2.direction) == pytest.approx(300.0, abs=1e-10)
    assert p2.dz is None and p2.zenith is None
    assert p3.distance == pytest.approx(50.0, abs=1e-12)
    # azimuth of (30, −40) = 200 − atan(30/40) in gon
    assert gon(p3.direction) == pytest.approx(200.0 - gon(math.atan2(30, 40)), abs=1e-10)
    assert r.field_order == [0, 2, 1]  # 50, 159.03, 300 gon


def test_known_zero_azimuth_instead_of_backsight():
    r = setout_points(
        SetoutRequest(
            station=ST,
            backsight_azimuth=to_rad(100.0, "gon"),
            points=[SPoint(name="N", x=1000.0, y=1050.0)],
        )
    )
    assert gon(r.rows[0].direction) == pytest.approx(300.0, abs=1e-10)
    assert r.backsight_distance is None


def test_setting_out_reproduces_the_design_point_with_polar():
    pts = [
        SPoint(name=f"P{i}", x=1000 + 37.3 * math.cos(i), y=1000 + 81.1 * math.sin(i))
        for i in range(40)
    ]
    r = setout_points(SetoutRequest(station=ST, backsight=BS_NORTH, points=pts))
    for p, row in zip(pts, r.rows, strict=True):
        back = polar(
            PolarRequest(
                station=XY(x=ST.x, y=ST.y),
                backsight=XY(x=BS_NORTH.x, y=BS_NORTH.y),
                angle=row.direction,
                distance=row.distance_grid,
            )
        ).point
        assert math.hypot(back.x - p.x, back.y - p.y) < 1e-9


def test_field_order_is_a_clockwise_sweep_from_the_backsight():
    pts = [
        SPoint(
            name=str(g),
            x=1000 + 10 * math.sin(to_rad(g, "gon")),
            y=1000 + 10 * math.cos(to_rad(g, "gon")),
        )
        for g in (350, 10, 200, 120, 10.0001)
    ]
    r = setout_points(SetoutRequest(station=ST, backsight=BS_NORTH, points=pts))
    dirs = [r.rows[k].direction for k in r.field_order]
    assert dirs == sorted(dirs)
    assert [r.rows[k].name for k in r.field_order] == ["10", "10.0001", "120", "200", "350"]


def test_egsa87_reduction_matches_the_independent_chain():
    rs = ReductionSettings(
        scale_mode="leg_simpson", elevation_reduction=True, curvature_refraction=False
    )
    st = SPoint(name="S", x=300_000.0, y=4_200_000.0, z=800.0)
    p = SPoint(name="P", x=300_300.0, y=4_200_400.0, z=820.0)
    r = setout_points(SetoutRequest(station=st, backsight_azimuth=0.0, points=[p], reduction=rs))
    row = r.rows[0]
    k = egsa87_line_scale(st.x, p.x)
    elev = rs.earth_radius / (rs.earth_radius + 810.0)
    assert row.distance_grid == pytest.approx(500.0, abs=1e-12)
    assert row.distance == pytest.approx(500.0 / (k * elev), abs=1e-9)
    assert row.scale == pytest.approx(k * elev, abs=1e-15)
    # ground is longer than grid west of the central meridian at 800 m height
    assert row.distance > row.distance_grid


def test_curvature_refraction_zenith_inverts_the_height_reduction():
    rs = ReductionSettings(scale_mode="none", elevation_reduction=False, curvature_refraction=True)
    st = SPoint(name="S", x=0.0, y=0.0, z=100.0)
    p = SPoint(name="P", x=0.0, y=800.0, z=112.345)
    r = setout_points(
        SetoutRequest(
            station=st,
            backsight_azimuth=0.0,
            points=[p],
            reduction=rs,
            instrument_height=1.6,
            target_height=2.0,
        )
    )
    row = r.rows[0]
    assert row.zenith is not None and row.slope_distance is not None
    dh = height_difference(rs, row.slope_distance, row.zenith, 1.6, 2.0)
    assert dh == pytest.approx(12.345, abs=1e-9)
    # without the correction the zenith would differ by (1 − κ)·HD²/2R ≈ 43.7 mm at 800 m
    plain = math.atan2(800.0, 12.345 - 1.6 + 2.0)
    assert abs(row.zenith - plain) > 1e-5


def test_setout_validation_and_issues():
    with pytest.raises(ValueError, match="Backsight coincides"):
        setout_points(SetoutRequest(station=ST, backsight=ST, points=[BS_NORTH]))
    with pytest.raises(ValueError, match="coincides with the station"):
        setout_points(SetoutRequest(station=ST, backsight=BS_NORTH, points=[ST]))
    with pytest.raises(ValueError, match="backsight"):
        setout_points(SetoutRequest(station=ST, points=[BS_NORTH]))
    no_z = SPoint(name="S", x=0.0, y=0.0)
    r = setout_points(
        SetoutRequest(
            station=no_z,
            backsight_azimuth=0.0,
            points=[SPoint(name="A", x=1, y=1, z=5), SPoint(name="A", x=2, y=1)],
        )
    )
    codes = {i.code for i in r.issues}
    assert codes == {"SETOUT_DUPLICATE_NAME", "SETOUT_NO_STATION_HEIGHT"}


def test_request_bounds_reject_non_finite_values():
    with pytest.raises(ValueError):
        SPoint(x=math.inf, y=0.0)
    with pytest.raises(ValueError):
        SetoutRequest(station=ST, backsight=BS_NORTH, points=[])


# ------------------------------------------------------------------------- as-staked check


def test_as_staked_differences_and_statistics():
    design = [
        SPoint(name="A", x=100.0, y=200.0, z=10.0),
        SPoint(name="B", x=110.0, y=200.0, z=10.0),
        SPoint(name="C", x=120.0, y=200.0),
        SPoint(name="D", x=130.0, y=200.0),
    ]
    measured = [
        SPoint(name="A", x=100.003, y=200.004, z=10.005),  # radial 5 mm
        SPoint(name="B", x=110.0, y=199.988, z=9.97),  # 12 mm, dz −30 mm
        SPoint(name="C", x=120.030, y=200.040),  # 50 mm
        SPoint(name="X", x=0.0, y=0.0),
    ]
    r = check_staked(
        CheckRequest(design=design, measured=measured, tolerance_xy=0.02, tolerance_z=0.02)
    )
    a, b, c = r.rows
    assert (a.dx, a.dy, a.dz) == pytest.approx((0.003, 0.004, 0.005), abs=1e-9)
    assert a.radial == pytest.approx(0.005, abs=1e-9) and a.ok
    assert b.ok_xy and b.ok_z is False and not b.ok
    assert not c.ok_xy and c.ok_z is None
    s = r.summary
    assert s is not None
    assert s.matched == 3 and s.out_of_tolerance == 2 and s.out_xy == 1 and s.out_z == 1
    assert s.max_radial == pytest.approx(0.05, abs=1e-9)
    assert s.rms_radial == pytest.approx(math.sqrt((0.005**2 + 0.012**2 + 0.05**2) / 3), abs=1e-9)
    assert s.mean_dx == pytest.approx(0.011, abs=1e-9)
    assert s.max_abs_dz == pytest.approx(0.03, abs=1e-9)
    assert s.rms_dz == pytest.approx(math.sqrt((0.005**2 + 0.03**2) / 2), abs=1e-9)
    assert r.unmatched_design == ["D"] and r.unmatched_measured == ["X"]


def test_along_and_across_a_reference_line():
    line = ReferenceLine(a=SPoint(x=0, y=0), b=SPoint(x=30, y=40))  # direction (0.6, 0.8)
    r = check_staked(
        CheckRequest(
            design=[SPoint(name="P", x=10, y=10)],
            measured=[
                SPoint(name="P", x=10.006 + 0.008, y=10.008 - 0.006)
            ],  # 10 mm along, 10 mm right
            reference_line=line,
        )
    )
    row = r.rows[0]
    assert row.along == pytest.approx(0.010, abs=1e-12)
    assert row.across == pytest.approx(0.010, abs=1e-12)
    assert row.along is not None and row.across is not None
    assert math.hypot(row.along, row.across) == pytest.approx(row.radial, abs=1e-12)
    with pytest.raises(ValueError, match="coincide"):
        check_staked(
            CheckRequest(
                design=[SPoint(name="P", x=1, y=1)],
                measured=[SPoint(name="P", x=1, y=1)],
                reference_line=ReferenceLine(a=SPoint(x=0, y=0), b=SPoint(x=0, y=0)),
            )
        )


def test_restaked_points_unnamed_points_and_no_match():
    r = check_staked(
        CheckRequest(
            design=[SPoint(name="P", x=0, y=0), SPoint(name="P", x=5, y=5), SPoint(x=1, y=1)],
            measured=[SPoint(name="P", x=1, y=0), SPoint(name="P", x=0.001, y=0)],
        )
    )
    assert r.rows[0].dx == pytest.approx(0.001)  # the last measurement wins
    assert {i.code for i in r.issues} == {
        "SETOUT_DUPLICATE_NAME",
        "SETOUT_RESTAKED",
        "SETOUT_UNNAMED",
    }
    none = check_staked(
        CheckRequest(design=[SPoint(name="A", x=0, y=0)], measured=[SPoint(name="B", x=0, y=0)])
    )
    assert none.summary is None and none.rows == []
    assert none.unmatched_design == ["A"] and none.unmatched_measured == ["B"]
