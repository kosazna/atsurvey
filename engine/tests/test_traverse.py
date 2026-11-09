import itertools
import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from atsurvey import ControlPoint, ProjectInput, TraverseSpec, compute_project
from atsurvey.core.geodesy import grid_azimuth
from atsurvey.core.models import ComputeSettings, ReductionSettings
from atsurvey.core.units import CC_TO_RAD, GON_TO_RAD, rad_to_cc

from synth import CONTROL, TRUTH, observe, traverse_setups

TOL = 1e-4  # 0.1 mm


def control(names=CONTROL, truth=TRUTH):
    return [ControlPoint(name=n, x=truth[n][0], y=truth[n][1], z=truth[n][2]) for n in names]


def pts(result):
    return {p.name: p for p in result.points}


def assert_truth(result, names, truth=TRUTH, tol=TOL, ztol=TOL):
    p = pts(result)
    for n in names:
        assert n in p, f"{n} not computed; issues: {[i.message for i in result.issues]}"
        assert p[n].x == pytest.approx(truth[n][0], abs=tol), n
        assert p[n].y == pytest.approx(truth[n][1], abs=tol), n
        if ztol is not None:
            assert p[n].z == pytest.approx(truth[n][2], abs=ztol), n


LINK = ["T1", "T2", "S1", "S2", "S3", "T3", "T4"]


def test_link_traverse_perfect_data_closes():
    inp = ProjectInput(
        control_points=control(),
        setups=traverse_setups(TRUTH, LINK),
        traverses=[TraverseSpec(route=LINK)],
    )
    r = compute_project(inp)
    t = r.traverses[0]
    assert t.kind == "link" and t.end_orientation
    assert t.status == "ok" and t.within_tolerance
    assert abs(rad_to_cc(t.angular_misclosure)) < 0.01
    assert t.linear_misclosure < TOL
    assert abs(t.wz) < TOL
    assert t.new_points == ["S1", "S2", "S3"]
    assert_truth(r, ["S1", "S2", "S3"])
    assert not [i for i in r.issues if i.severity != "info"]


def test_open_traverse_regression_last_point_not_overwritten():
    # legacy bug: the last new point was overwritten with the start station
    route = ["T1", "T2", "S1", "S2"]
    inp = ProjectInput(
        control_points=control(["T1", "T2"]),
        setups=traverse_setups(TRUTH, route),
        traverses=[TraverseSpec(route=route)],
    )
    r = compute_project(inp)
    t = r.traverses[0]
    assert t.kind == "open"
    assert t.within_tolerance is None
    assert_truth(r, ["S1", "S2"])


def test_closed_traverse_with_orientation():
    route = ["T1", "T2", "S1", "S2", "D3", "T2", "T1"]
    inp = ProjectInput(
        control_points=control(["T1", "T2"]),
        setups=traverse_setups(TRUTH, route),
        traverses=[TraverseSpec(route=route)],
    )
    r = compute_project(inp)
    t = r.traverses[0]
    assert t.kind == "closed" and t.end_orientation
    assert t.n_angles == 5
    assert abs(rad_to_cc(t.angular_misclosure)) < 0.01
    assert t.linear_misclosure < TOL
    assert_truth(r, ["S1", "S2", "D3"])


def test_closed_traverse_detects_angular_error():
    # legacy bug: closed traverses reported zero angular misclosure
    route = ["T1", "T2", "S1", "S2", "D3", "T2", "T1"]
    setups = traverse_setups(TRUTH, route)
    # spoil the angle at S2 by +100 cc
    s2 = setups[2]
    s2.observations[1].hz += 100 * CC_TO_RAD
    r = compute_project(
        ProjectInput(
            control_points=control(["T1", "T2"]),
            setups=setups,
            traverses=[TraverseSpec(route=route)],
        )
    )
    t = r.traverses[0]
    assert rad_to_cc(t.angular_misclosure) == pytest.approx(-100, abs=0.05)
    assert t.stations[0].angle_correction == pytest.approx(-100 / 5 * CC_TO_RAD, abs=1e-9)


def test_link_traverse_position_only():
    route = ["T1", "T2", "S1", "S2", "S3", "T3"]
    inp = ProjectInput(
        control_points=control(),
        setups=traverse_setups(TRUTH, route),
        traverses=[TraverseSpec(route=route, end_orientation=False)],
    )
    r = compute_project(inp)
    t = r.traverses[0]
    assert t.kind == "link" and not t.end_orientation
    assert t.angular_misclosure is None
    assert t.linear_misclosure < TOL
    assert_truth(r, ["S1", "S2", "S3"])


def test_reversed_route_is_handled():
    route = list(reversed(LINK))
    inp = ProjectInput(
        control_points=control(),
        setups=traverse_setups(TRUTH, LINK),
        traverses=[TraverseSpec(route=route)],
    )
    r = compute_project(inp)
    # both ends are known, so the route is computed in the given direction
    assert r.traverses[0].route == route
    assert r.traverses[0].linear_misclosure < TOL
    assert_truth(r, ["S1", "S2", "S3"])


def test_route_written_from_the_unknown_end_is_reversed():
    setups = traverse_setups(TRUTH, ["T1", "T2", "S1", "S2", "S3"])
    r = compute_project(
        ProjectInput(
            control_points=control(["T1", "T2"]),
            setups=setups,
            traverses=[TraverseSpec(route=["S3", "S2", "S1", "T2", "T1"])],
        )
    )
    assert r.traverses[0].route == ["T1", "T2", "S1", "S2", "S3"]
    assert_truth(r, ["S1", "S2", "S3"])


def test_angular_misclosure_sign_and_distribution():
    setups = traverse_setups(TRUTH, LINK)
    setups[1].observations[1].hz += 30 * CC_TO_RAD  # angle at S1 too big by 30 cc
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    t = r.traverses[0]
    assert rad_to_cc(t.angular_misclosure) == pytest.approx(-30, abs=0.05)
    n = t.n_angles
    assert n == 5
    for s in t.stations:
        assert rad_to_cc(s.angle_correction) == pytest.approx(-30 / n, abs=0.01)
    # after correction the closing azimuth is exact
    last = t.stations[-1]
    az_known = grid_azimuth(*TRUTH["T3"][:2], *TRUTH["T4"][:2])
    assert last.azimuth == pytest.approx(az_known, abs=1e-9)


def test_linear_misclosure_bowditch_distribution():
    setups = traverse_setups(TRUTH, LINK)
    # lengthen the S1→S2 distance by 3 cm (both directions)
    for s in setups:
        for o in s.observations:
            if {s.station, o.target} == {"S1", "S2"}:
                o.sd += 0.03
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    t = r.traverses[0]
    assert t.linear_misclosure == pytest.approx(0.03, abs=0.002)
    total = sum(leg.distance_grid for leg in t.legs)
    for leg in t.legs:
        assert leg.corr_x == pytest.approx(t.wx * leg.distance_grid / total, abs=1e-12)
    # corrections sum to the misclosure
    assert sum(leg.corr_x for leg in t.legs) == pytest.approx(t.wx, abs=1e-12)
    assert sum(leg.corr_y for leg in t.legs) == pytest.approx(t.wy, abs=1e-12)


def test_tolerance_flags():
    setups = traverse_setups(TRUTH, LINK)
    setups[2].observations[1].hz += 500 * CC_TO_RAD
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    t = r.traverses[0]
    assert t.status == "warning" and t.within_tolerance is False
    assert "TRAVERSE_ANGULAR_TOLERANCE" in {i.code for i in r.issues}


def test_face_two_and_rounds_reduce_to_same_result():
    a = compute_project(
        ProjectInput(
            control_points=control(),
            setups=traverse_setups(TRUTH, LINK),
            traverses=[TraverseSpec(route=LINK)],
        )
    )
    b = compute_project(
        ProjectInput(
            control_points=control(),
            setups=traverse_setups(TRUTH, LINK, face2=True),
            traverses=[TraverseSpec(route=LINK)],
        )
    )
    pa, pb = pts(a), pts(b)
    for n in ["S1", "S2", "S3"]:
        assert pa[n].x == pytest.approx(pb[n].x, abs=1e-6)
        assert pa[n].z == pytest.approx(pb[n].z, abs=1e-6)


def test_missing_angle_is_reported():
    setups = traverse_setups(TRUTH, LINK)
    setups[2].observations = setups[2].observations[:1]  # S2 sees S1 only
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    assert r.traverses[0].status == "failed"
    errs = [i for i in r.issues if i.code == "TRAVERSE_MISSING_ANGLE"]
    assert errs and errs[0].params["angle"] == "S1-S2-S3"


def test_dependency_order_resolution():
    # traverse 2 starts from S1/S2, which only exist after traverse 1 — listed first anyway
    second = ["S1", "S2", "D3"]
    setups = [*traverse_setups(TRUTH, LINK), observe(TRUTH, "S2", ["S1", "D3"])]
    r = compute_project(
        ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=second, kind="open"), TraverseSpec(route=LINK)],
        )
    )
    assert [t.name for t in r.traverses] == ["S1-S2-D3", "-".join(LINK)]
    assert_truth(r, ["S1", "S2", "S3", "D3"])


def test_unresolved_traverse():
    r = compute_project(
        ProjectInput(
            control_points=control(["T1"]),
            setups=traverse_setups(TRUTH, LINK),
            traverses=[TraverseSpec(route=LINK)],
        )
    )
    assert "TRAVERSE_UNRESOLVED" in {i.code for i in r.issues}


def test_known_point_in_middle_is_kept_and_flagged():
    shifted = (TRUTH["S2"][0] + 0.05, TRUTH["S2"][1], TRUTH["S2"][2])
    inp = ProjectInput(
        control_points=[*control(), ControlPoint(name="S2", x=shifted[0], y=shifted[1])],
        setups=traverse_setups(TRUTH, LINK),
        traverses=[TraverseSpec(route=LINK)],
    )
    r = compute_project(inp)
    issue = next(i for i in r.issues if i.code == "TRAVERSE_KNOWN_POINT_MID")
    assert issue.params["point"] == "S2" and issue.params["diff_mm"] == pytest.approx(50, abs=1)
    s2 = pts(r)["S2"]
    assert s2.kind == "control" and s2.x == shifted[0]
    assert "S2" not in r.traverses[0].new_points


def test_missing_distance_is_reported():
    setups = traverse_setups(TRUTH, LINK)
    for s in setups:
        for o in s.observations:
            if {s.station, o.target} == {"S2", "S3"}:
                o.sd = None
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)])
    )
    assert r.traverses[0].status == "failed"
    assert any(
        i.code == "TRAVERSE_MISSING_DISTANCE" and i.params["leg"] == "S2-S3" for i in r.issues
    )


def test_input_hash_is_stable_and_sensitive():
    a = ProjectInput(control_points=control())
    b = ProjectInput(control_points=control())
    c = ProjectInput(control_points=control(["T1"]))
    ra, rb, rc = compute_project(a), compute_project(b), compute_project(c)
    assert ra.input_hash == rb.input_hash != rc.input_hash


def test_legacy_compatible_mode_plane_geometry():
    """Without reductions the computation is plain plane trigonometry."""
    rs = ReductionSettings(scale_mode="none", elevation_reduction=False, curvature_refraction=False)
    setups = traverse_setups(TRUTH, LINK, rs=rs)
    r = compute_project(
        ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=LINK)],
            settings=ComputeSettings(reduction=rs),
        )
    )
    assert_truth(r, ["S1", "S2", "S3"])
    leg = r.traverses[0].legs[0]
    assert leg.reduction_scale == 1.0 and leg.elevation_factor == 1.0


def test_reductions_matter_at_the_cm_level():
    """Ignoring the EGSA87 scale factor on real data must visibly break closure."""
    setups = traverse_setups(TRUTH, LINK)
    rs = ReductionSettings(scale_mode="none", elevation_reduction=False)
    r = compute_project(
        ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=LINK)],
            settings=ComputeSettings(reduction=rs),
        )
    )
    assert r.traverses[0].linear_misclosure > 0.05


def test_traverse_mean_mode_close_to_leg_mode():
    setups = traverse_setups(TRUTH, LINK)
    rs = ReductionSettings(scale_mode="traverse_mean", elevation_mode="traverse")
    r = compute_project(
        ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=LINK)],
            settings=ComputeSettings(reduction=rs),
        )
    )
    # a single factor for the whole traverse leaves a sub-cm misclosure that Bowditch absorbs
    assert r.traverses[0].linear_misclosure < 0.01
    assert_truth(r, ["S1", "S2", "S3"], tol=0.005, ztol=None)


@settings(max_examples=60, deadline=None)
@given(
    n_new=st.integers(min_value=1, max_value=8),
    seed=st.integers(min_value=0, max_value=10_000),
    face2=st.booleans(),
)
def test_property_random_link_traverses_close(n_new, seed, face2):
    rng = random.Random(seed)
    x0, y0 = rng.uniform(150_000, 850_000), rng.uniform(3_850_000, 4_600_000)
    truth = {"A": (x0, y0, rng.uniform(0, 1500))}
    heading = rng.uniform(0, 2 * math.pi)
    names = ["A", "B"] + [f"P{i}" for i in range(n_new)] + ["E", "F"]
    for prev, name in itertools.pairwise(names):
        heading += rng.uniform(-0.9, 0.9)
        d = rng.uniform(80, 600)
        px, py, pz = truth[prev]
        truth[name] = (
            px + d * math.sin(heading),
            py + d * math.cos(heading),
            pz + rng.uniform(-20, 20),
        )
    known = ["A", "B", "E", "F"]
    r = compute_project(
        ProjectInput(
            control_points=control(known, truth),
            setups=traverse_setups(truth, names, face2=face2, rng=rng),
            traverses=[TraverseSpec(route=names)],
        )
    )
    t = r.traverses[0]
    assert abs(t.angular_misclosure) < 1e-9
    assert t.linear_misclosure < 2e-4
    assert_truth(r, names[2:-2], truth=truth, tol=2e-4, ztol=2e-4)


def test_gon_constant():
    assert pytest.approx(2 * math.pi) == 400 * GON_TO_RAD
