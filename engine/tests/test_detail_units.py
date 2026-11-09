import math

import pytest
from atsurvey import ProjectInput, TraverseSpec, compute_project
from atsurvey.core.geodesy import egsa87_line_scale, egsa87_point_scale, grid_azimuth
from atsurvey.core.units import (
    circular_mean,
    deg_to_dms,
    dms_to_deg,
    from_rad,
    to_rad,
    wrap_2pi,
    wrap_pi,
)
from synth import TRUTH, observe, traverse_setups
from test_traverse import LINK, assert_truth, control, pts


def test_detail_points_from_traverse_stations():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "S2", "D1", "D2"], codes={"D1": "KR", "D2": "TO"}))
    setups.append(observe(TRUTH, "S2", ["S1", "D3"]))
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    assert_truth(r, ["D1", "D2", "D3"])
    p = pts(r)
    assert p["D1"].kind == "detail" and p["D1"].code == "KR"
    # traverse stations are not overwritten by the radiation shots
    assert p["S2"].kind == "traverse"
    checks = [s for s in r.detail if s.check and s.residual is not None]
    assert checks and max(s.residual for s in checks) < 1e-4
    o = [o for o in r.orientations if o.station == "S1" and len(o.references) >= 2]
    assert o and o[0].spread < 1e-9


def test_radiated_station_and_its_setup():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "D1"]))
    setups.append(observe(TRUTH, "D1", ["S1", "D3"]))  # D1 is a radiated station
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    assert_truth(r, ["D1", "D3"])
    assert "STATION_BY_RADIATION" in {i.code for i in r.issues}


def test_duplicate_detail_averaged_and_flagged():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "D3"]))
    bad = observe(TRUTH, "S2", ["S1", "D3"])
    bad.observations[1].sd += 0.2
    setups.append(bad)
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    assert pts(r)["D3"].n == 2
    assert "DETAIL_DUPLICATE" in {i.code for i in r.issues}


def test_setup_without_orientation_and_unknown_station():
    setups = [observe(TRUTH, "S1", ["D1", "D2"]), observe(TRUTH, "T2", ["D1"])]
    r = compute_project(ProjectInput(control_points=control(), setups=setups))
    codes = {i.code for i in r.issues}
    assert "SETUP_STATION_UNKNOWN" in codes
    assert "SETUP_NO_ORIENTATION" in codes


def test_control_duplicate():
    cps = control() + control(["T1"])
    r = compute_project(ProjectInput(control_points=cps))
    assert "CONTROL_DUPLICATE" in {i.code for i in r.issues}
    assert r.summary.n_control == 4


@pytest.mark.parametrize(
    ("dx", "dy", "expected_gon"),
    [(0, 10, 0), (10, 0, 100), (0, -10, 200), (-10, 0, 300), (10, 10, 50), (-10, 10, 350)],
)
def test_azimuth_quadrants_including_axes(dx, dy, expected_gon):
    # legacy bug: azimuth crashed when Δx or Δy was exactly zero
    assert from_rad(grid_azimuth(0, 0, dx, dy), "gon") == pytest.approx(expected_gon)


def test_angle_units_roundtrip():
    for v in [0.0, 12.3456, 199.9999, 399.99999]:
        assert from_rad(to_rad(v, "gon"), "gon") == pytest.approx(v)
    assert dms_to_deg(123.4530) == pytest.approx(123 + 45 / 60 + 30 / 3600)
    assert deg_to_dms(dms_to_deg(45.0001)) == pytest.approx(45.0001, abs=1e-9)
    assert from_rad(to_rad(359.5959, "dms"), "dms") == pytest.approx(359.5959, abs=1e-8)


def test_wrapping_and_circular_mean():
    assert wrap_2pi(-0.1) == pytest.approx(2 * math.pi - 0.1)
    assert wrap_pi(3 * math.pi / 2) == pytest.approx(-math.pi / 2)
    m = circular_mean([2 * math.pi - 0.001, 0.001])
    assert min(m, 2 * math.pi - m) == pytest.approx(0, abs=1e-12)


def test_egsa87_scale_factor_values():
    assert egsa87_point_scale(500000) == pytest.approx(0.9996)
    # classic textbook value at 200 km from the central meridian
    assert egsa87_point_scale(300000) == pytest.approx(0.9996 + 0.012311 * 0.04)
    assert egsa87_line_scale(400000, 400000) == pytest.approx(egsa87_point_scale(400000))
