"""Least-squares network adjustment."""

import math
import random
import time

import pytest

from atsurvey import ComputeSettings, ControlPoint, ProjectInput, TraverseSpec, compute_project
from atsurvey.core.adjust import _chi2_ppf, _ellipse, adjust_network
from atsurvey.core.issues import IssueSink
from atsurvey.core.models import AdjustmentSettings, ReductionSettings, Setup, Tolerances
from atsurvey.core.reduce import ObservationIndex, reduce_setups
from atsurvey.core.traverse import KnownPoint
from atsurvey.core.units import CC_TO_RAD

from synth import TRUTH, observe, traverse_setups
from test_traverse import LINK, control

LSA = AdjustmentSettings(method="least_squares")


def lsa_settings(**kw) -> ComputeSettings:
    return ComputeSettings(adjustment=AdjustmentSettings(method="least_squares", **kw))


def pts(result):
    return {p.name: p for p in result.points}


# ---------------------------------------------------------------------- network helpers


def grid_truth(nx: int, ny: int, spacing: float = 250.0, seed: int = 3):
    rng = random.Random(seed)
    truth = {}
    for i in range(nx):
        for j in range(ny):
            truth[f"P{i}_{j}"] = (
                450_000 + i * spacing + rng.uniform(-30, 30),
                4_200_000 + j * spacing + rng.uniform(-30, 30),
                100 + rng.uniform(-20, 20),
            )
    return truth


def grid_setups(
    truth, nx, ny, *, diagonals=True, rng=None, noise=False, sig: AdjustmentSettings = LSA
):
    """Every point is occupied and observes its 4 (or 8) neighbours."""
    rng = rng or random.Random(11)
    setups = []
    for i in range(nx):
        for j in range(ny):
            nb = []
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if (di, dj) == (0, 0) or (not diagonals and di and dj):
                        continue
                    if 0 <= i + di < nx and 0 <= j + dj < ny:
                        nb.append(f"P{i + di}_{j + dj}")
            st = observe(truth, f"P{i}_{j}", nb, rng=rng)
            if noise:
                add_noise(st, truth, rng, sig)
            setups.append(st)
    return setups


def add_noise(setup: Setup, truth, rng, sig: AdjustmentSettings):
    """Gaussian noise matching the a priori model (centering = 0, ppm = 0)."""
    xs, ys, _ = truth[setup.station]
    for o in setup.observations:
        xt, yt, _ = truth[o.target]
        d = math.hypot(xt - xs, yt - ys)
        o.hz += rng.gauss(0, sig.sigma_direction_cc) * CC_TO_RAD
        o.sd += rng.gauss(0, sig.sigma_distance_mm / 1000)
        s_h = max(sig.sigma_height_mm * math.sqrt(d / 1000), 1.0) / 1000
        o.v += rng.gauss(0, s_h / d)


def run_direct(truth, fixed_names, setups, settings=LSA, approx_noise=0.05, seed=1, rs=None):
    rs = rs or ReductionSettings()
    sink = IssueSink()
    reduced = reduce_setups(setups, rs, Tolerances(), sink)
    index = ObservationIndex(reduced)
    rng = random.Random(seed)
    known = {}
    for n, (x, y, z) in truth.items():
        if n in fixed_names:
            known[n] = KnownPoint(n, x, y, z, "control")
        elif n in index.by_station:
            known[n] = KnownPoint(
                n,
                x + rng.uniform(-approx_noise, approx_noise),
                y + rng.uniform(-approx_noise, approx_noise),
                z + rng.uniform(-approx_noise, approx_noise),
                "traverse",
            )
    res = adjust_network(reduced, index, known, set(fixed_names), rs, settings, sink)
    return res, known, sink


# -------------------------------------------------------------------------------- tests


def test_a_perfect_link_traverse_recovers_truth():
    setups = traverse_setups(TRUTH, LINK)
    r = compute_project(
        ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=LINK)],
            settings=lsa_settings(),
        )
    )
    a = r.adjustment
    assert a is not None and a.converged and a.dof > 0
    assert a.sigma0 < 1e-6
    assert max(abs(o.residual) for o in a.observations if o.kind != "direction") < 1e-6
    assert max(abs(o.residual) for o in a.observations if o.kind == "direction") < 1e-9
    p = pts(r)
    for n in ("S1", "S2", "S3"):
        assert p[n].x == pytest.approx(TRUTH[n][0], abs=1e-4)
        assert p[n].y == pytest.approx(TRUTH[n][1], abs=1e-4)
        assert p[n].z == pytest.approx(TRUTH[n][2], abs=1e-4)
        assert p[n].ellipse is not None and p[n].sz is not None
    # control points are fixed and carry no precision
    assert p["T1"].x == TRUTH["T1"][0] and p["T1"].ellipse is None


def test_b_lsa_agrees_with_bowditch_on_a_single_noisy_traverse():
    rng = random.Random(5)
    setups = traverse_setups(TRUTH, LINK, rng=rng, angle_noise_cc=8, dist_noise_m=0.002)

    def inp(settings: ComputeSettings) -> ProjectInput:
        return ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=LINK)],
            settings=settings,
        )

    bow = pts(compute_project(inp(ComputeSettings())))
    lsa = pts(compute_project(inp(lsa_settings())))
    for n in ("S1", "S2", "S3"):
        assert math.hypot(bow[n].x - lsa[n].x, bow[n].y - lsa[n].y) < 0.005
        assert math.hypot(lsa[n].x - TRUTH[n][0], lsa[n].y - TRUTH[n][1]) < 0.01


def test_c_network_with_junction_and_cross_ties():
    truth = dict(TRUTH)
    truth.update(
        {
            "J": (476840.0, 4205600.0, 205.0),
            "Q1": (476520.0, 4205700.0, 199.0),
            "T5": (476200.0, 4205900.0, 190.0),
            "T6": (476350.0, 4205820.0, 193.0),
        }
    )
    r1 = ["T1", "T2", "S1", "J", "S3", "T3", "T4"]
    r2 = ["T5", "T6", "Q1", "J"]
    rng = random.Random(9)
    setups = traverse_setups(truth, r1, rng=rng, angle_noise_cc=6, dist_noise_m=0.0015)
    for st, targets in (
        ("T6", ["T5", "Q1"]),
        ("Q1", ["T6", "J", "S1"]),  # cross-tie to S1
        ("J", ["Q1", "S1"]),
        ("S1", ["Q1", "J"]),
    ):
        setups.append(observe(truth, st, targets, rng=rng, angle_noise_cc=6, dist_noise_m=0.0015))
    cps = control(["T1", "T2", "T3", "T4", "T5", "T6"], truth)
    r = compute_project(
        ProjectInput(
            control_points=cps,
            setups=setups,
            traverses=[TraverseSpec(route=r1), TraverseSpec(route=r2)],
            settings=lsa_settings(
                sigma_direction_cc=6, sigma_distance_mm=1.5, sigma_distance_ppm=0
            ),
        )
    )
    a = r.adjustment
    assert a is not None and a.dof > 5 and a.converged
    p = pts(r)
    for n in ("S1", "J", "S3", "Q1"):
        assert math.hypot(p[n].x - truth[n][0], p[n].y - truth[n][1]) < 0.01, n
    # the junction is determined once, by all observations together
    assert not [i for i in r.issues if i.code == "POINT_CONFLICT"]


def test_d_sigma0_close_to_one_with_matching_noise():
    truth = grid_truth(4, 4)
    sig = AdjustmentSettings(
        method="least_squares",
        sigma_direction_cc=10,
        sigma_distance_mm=2,
        sigma_distance_ppm=0,
        sigma_centering_mm=0,
        sigma_height_mm=5,
    )
    fixed = ["P0_0", "P3_3", "P0_3"]
    s0, passed = [], 0
    n_runs = 30
    for seed in range(n_runs):
        rng = random.Random(1000 + seed)
        setups = grid_setups(truth, 4, 4, rng=rng, noise=True, sig=sig)
        res, _, _ = run_direct(truth, fixed, setups, settings=sig, seed=seed)
        assert res is not None
        s0.append(res.sigma0)
        passed += bool(res.global_test and res.global_test.passed)
    mean = sum(s0) / len(s0)
    assert 0.85 < mean < 1.15, mean
    assert passed >= 0.8 * n_runs


@pytest.mark.parametrize("kind", ["direction", "distance"])
def test_e_blunder_is_the_suspect(kind):
    truth = grid_truth(4, 4)
    setups = grid_setups(truth, 4, 4)
    st = next(s for s in setups if s.station == "P1_1")
    o = next(o for o in st.observations if o.target == "P2_2")
    if kind == "direction":
        o.hz += 50 * CC_TO_RAD
    else:
        o.sd += 0.05
    res, _, sink = run_direct(truth, ["P0_0", "P3_3", "P0_3"], setups)
    assert res is not None and res.suspect is not None
    assert (res.suspect.kind, res.suspect.station, res.suspect.target) == (kind, "P1_1", "P2_2")
    assert res.suspect.flagged and abs(res.suspect.w or 0.0) > res.w_critical
    assert any(i.code == "ADJUSTMENT_BLUNDER" for i in sink.items)


def test_f_error_ellipses_grow_away_from_control():
    truth = grid_truth(6, 3)
    setups = grid_setups(truth, 6, 3, diagonals=False)
    res, known, _ = run_direct(truth, ["P0_0", "P0_1"], setups)
    assert res is not None
    near, far = known["P1_1"].ellipse, known["P5_1"].ellipse
    assert near is not None and far is not None
    assert far.a > 2 * near.a
    for kp in known.values():
        if kp.ellipse is not None:
            assert 0 <= kp.ellipse.theta < math.pi
            assert kp.ellipse.a >= kp.ellipse.b >= 0
            assert kp.sx is not None and kp.sy is not None


def test_ellipse_orientation():
    e = _ellipse(4.0, 1.0, 0.0, 1.0)  # long in X (east)
    assert e.a == pytest.approx(2.0) and e.b == pytest.approx(1.0)
    assert e.theta == pytest.approx(math.pi / 2)
    e = _ellipse(1.0, 4.0, 0.0, 1.0)  # long in Y (north)
    assert e.theta == pytest.approx(0.0)
    e = _ellipse(2.0, 2.0, 1.0, 1.0)  # long towards north-east
    assert e.theta == pytest.approx(math.pi / 4)


def test_g_datum_failure_with_one_control_point():
    truth = grid_truth(3, 3)
    setups = grid_setups(truth, 3, 3)
    res, known, sink = run_direct(truth, ["P0_0"], setups)
    assert res is None
    assert any(i.code == "ADJUSTMENT_DATUM" and i.severity == "error" for i in sink.items)
    # coordinates untouched
    assert known["P1_1"].ellipse is None


def test_h_heights_are_adjusted():
    truth = grid_truth(3, 3)
    setups = grid_setups(truth, 3, 3)
    res, known, _ = run_direct(truth, ["P0_0", "P2_2"], setups, approx_noise=0.2)
    assert res is not None
    assert any(o.kind == "height" for o in res.observations)
    for n in ("P1_1", "P2_0", "P0_2"):
        kp = known[n]
        assert kp.z == pytest.approx(truth[n][2], abs=1e-4)
        assert kp.sz is not None


def test_heights_need_a_fixed_height():
    truth = grid_truth(3, 3)
    setups = grid_setups(truth, 3, 3)
    sink = IssueSink()
    rs = ReductionSettings()
    reduced = reduce_setups(setups, rs, Tolerances(), sink)
    index = ObservationIndex(reduced)
    known = {
        n: KnownPoint(
            n,
            x,
            y,
            None if n in ("P0_0", "P2_2") else z,
            "control" if n in ("P0_0", "P2_2") else "traverse",
        )
        for n, (x, y, z) in truth.items()
    }
    res = adjust_network(reduced, index, known, {"P0_0", "P2_2"}, rs, LSA, sink)
    assert res is not None
    assert any(
        i.code == "ADJUSTMENT_DATUM" and i.params["dimension"] == "height" for i in sink.items
    )
    assert all(o.kind != "height" for o in res.observations)


def test_i_performance_300_stations():
    truth = grid_truth(15, 20)
    setups = grid_setups(truth, 15, 20, diagonals=False)
    t0 = time.perf_counter()
    res, known, _ = run_direct(truth, ["P0_0", "P14_19", "P0_19", "P14_0"], setups)
    elapsed = time.perf_counter() - t0
    assert res is not None and res.converged
    assert elapsed < 3.0, elapsed
    assert (
        math.hypot(known["P7_10"].x - truth["P7_10"][0], known["P7_10"].y - truth["P7_10"][1])
        < 1e-4
    )


def test_j_end_to_end_detail_from_adjusted_stations():
    rng = random.Random(21)
    setups = traverse_setups(TRUTH, LINK, rng=rng, angle_noise_cc=10, dist_noise_m=0.003)
    setups.append(observe(TRUTH, "S1", ["T2", "D1", "D2"]))
    r = compute_project(
        ProjectInput(
            control_points=control(),
            setups=setups,
            traverses=[TraverseSpec(route=LINK)],
            settings=lsa_settings(),
        )
    )
    assert r.adjustment is not None
    p = pts(r)
    assert p["S2"].ellipse is not None and p["S2"].sx is not None
    shot = next(s for s in r.detail if s.station == "S1" and s.target == "D1")
    s1, d1 = p["S1"], p["D1"]
    # the detail point was radiated from the *adjusted* S1
    dg = shot.distance_grid
    assert dg is not None
    assert d1.x - s1.x == pytest.approx(dg * math.sin(shot.azimuth), abs=1e-9)
    assert d1.y - s1.y == pytest.approx(dg * math.cos(shot.azimuth), abs=1e-9)
    assert p["D1"].ellipse is None


def test_excluded_point_without_coordinates_and_no_free_points():
    setups = traverse_setups(TRUTH, LINK)
    r = compute_project(
        ProjectInput(control_points=control(), setups=setups, settings=lsa_settings())
    )
    codes = {i.code for i in r.issues}
    assert "ADJUSTMENT_EXCLUDED_POINT" in codes or "ADJUSTMENT_NO_REDUNDANCY" in codes
    assert r.adjustment is None


def test_too_large(monkeypatch):
    import atsurvey.core.adjust as adj

    monkeypatch.setattr(adj, "MAX_UNKNOWNS", 5)
    truth = grid_truth(3, 3)
    res, _, sink = run_direct(truth, ["P0_0", "P2_2"], grid_setups(truth, 3, 3))
    assert res is None
    assert any(i.code == "ADJUSTMENT_TOO_LARGE" for i in sink.items)


def test_chi2_quantiles():
    # reference values from tables
    assert _chi2_ppf(0.975, 10) == pytest.approx(20.483, rel=0.01)
    assert _chi2_ppf(0.025, 10) == pytest.approx(3.247, rel=0.03)
    assert _chi2_ppf(0.95, 50) == pytest.approx(67.505, rel=0.005)


def test_greek_messages_exist():
    from atsurvey.core.messages import EL

    for code in (
        "ADJUSTMENT_DATUM",
        "ADJUSTMENT_TOO_LARGE",
        "ADJUSTMENT_NOT_CONVERGED",
        "ADJUSTMENT_GLOBAL_TEST",
        "ADJUSTMENT_SIGMA0_LOW",
        "ADJUSTMENT_BLUNDER",
        "ADJUSTMENT_NO_REDUNDANCY",
        "ADJUSTMENT_EXCLUDED_POINT",
    ):
        assert code in EL


def test_control_point_input_untouched():
    cps = control()
    before = [c.model_dump() for c in cps]
    compute_project(
        ProjectInput(
            control_points=cps,
            setups=traverse_setups(TRUTH, LINK),
            traverses=[TraverseSpec(route=LINK)],
            settings=lsa_settings(),
        )
    )
    assert [c.model_dump() for c in cps] == before
    assert isinstance(cps[0], ControlPoint)


def test_low_sigma0_is_informational_not_a_warning():
    """Perfect data fits better than the a-priori σ: that is a note, not a quality problem."""
    from atsurvey import ControlPoint, ProjectInput, TraverseSpec, compute_project
    from atsurvey.core.models import AdjustmentSettings, ComputeSettings

    from synth import CONTROL, TRUTH, traverse_setups

    route = ["T1", "T2", "S1", "S2", "S3", "T3", "T4"]
    r = compute_project(
        ProjectInput(
            control_points=[
                ControlPoint(name=n, x=TRUTH[n][0], y=TRUTH[n][1], z=TRUTH[n][2]) for n in CONTROL
            ],
            setups=traverse_setups(TRUTH, route),
            traverses=[TraverseSpec(route=route)],
            settings=ComputeSettings(adjustment=AdjustmentSettings(method="least_squares")),
        )
    )
    codes = {(i.code, i.severity) for i in r.issues}
    assert ("ADJUSTMENT_SIGMA0_LOW", "info") in codes
    assert not any(c == "ADJUSTMENT_GLOBAL_TEST" for c, _ in codes)
