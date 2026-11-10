"""Network pre-analysis: precision and reliability of a planned network.

Independent truths: (1) the real least-squares adjustment of perfect synthetic observations of
the same geometry (σ0 = 1 cofactor results must agree); (2) closed-form small networks;
(3) a dense design matrix built by numerical differentiation in the test itself.
"""

import math
import random
from statistics import NormalDist

import numpy as np
import pytest
from test_adjust import grid_truth, run_direct

from atsurvey.core.messages import EL
from atsurvey.core.models import AdjustmentSettings, ReductionSettings
from atsurvey.core.preanalysis import K95, observation_sigma, preanalyse, reliability_constants
from atsurvey.core.preanalysis_models import (
    InstrumentSpec,
    PlannedObservation,
    PlannedPoint,
    PreanalysisRequest,
)
from atsurvey.core.units import CC_TO_RAD

from synth import observe

NO_CENTRING = InstrumentSpec(
    sigma_direction_cc=10,
    sigma_distance_mm=2,
    sigma_distance_ppm=0,
    sigma_centering_instrument_mm=0,
    sigma_centering_target_mm=0,
    sigma_height_mm=5,
)


def pt(name, x, y, fixed=False):
    return PlannedPoint(name=name, x=x, y=y, fixed=fixed)


def ob(kind, st, tg, setup=None):
    return PlannedObservation(kind=kind, station=st, target=tg, setup=setup)


def by_name(res):
    return {p.name: p for p in res.points}


# ------------------------------------------------------------------- constants (Baarda)


def test_baarda_constants():
    d0, l0 = reliability_constants(0.001, 0.80)
    assert d0 == pytest.approx(4.13, abs=0.005)
    assert l0 == pytest.approx(17.07, abs=0.02)
    assert abs(K95 - 2.4477) < 1e-4
    # χ²₂ quantile: pt(χ²₂ ≤ k²) = 1 − exp(−k²/2) = 0.95
    assert 1 - math.exp(-(K95**2) / 2) == pytest.approx(0.95, abs=1e-12)


def test_observation_sigmas():
    spec = InstrumentSpec(
        sigma_direction_cc=5,
        sigma_distance_mm=1,
        sigma_distance_ppm=1.5,
        sigma_centering_instrument_mm=0.8,
        sigma_centering_target_mm=0.6,
        sigma_height_mm=4,
    )
    d = 400.0
    c2 = 0.0008**2 + 0.0006**2
    assert observation_sigma("direction", d, spec) == pytest.approx(
        math.sqrt((5 * CC_TO_RAD) ** 2 + c2 / d**2)
    )
    assert observation_sigma("distance", d, spec) == pytest.approx(
        math.sqrt((0.001 + 1.5e-6 * d) ** 2 + c2)
    )
    assert observation_sigma("height", d, spec) == pytest.approx(0.004 * math.sqrt(0.4))
    assert observation_sigma("height", 10.0, spec) == pytest.approx(0.001)  # 1 mm floor


# ---------------------------------------------------------- identical to the adjustment


def _grid_case(nx=4, ny=4):
    truth = grid_truth(nx, ny)
    rs = ReductionSettings(scale_mode="none", elevation_reduction=False)
    rng = random.Random(4)
    setups = []
    for i in range(nx):
        for j in range(ny):
            nb = [
                f"P{i + di}_{j + dj}"
                for di in (-1, 0, 1)
                for dj in (-1, 0, 1)
                if (di, dj) != (0, 0) and 0 <= i + di < nx and 0 <= j + dj < ny
            ]
            setups.append(observe(truth, f"P{i}_{j}", nb, rs=rs, rng=rng))
    return truth, setups, rs


def test_equals_the_adjustment_cofactors():
    """Pre-analysis σ and r = the real adjustment of perfect data of the same geometry, whose
    σ0 ≈ 0 fails the global test low, so it reports a priori (σ0 = 1) precision."""
    truth, setups, rs = _grid_case()
    fixed = ["P0_0", "P3_3", "P0_3"]
    settings = AdjustmentSettings(
        method="least_squares",
        sigma_direction_cc=10,
        sigma_distance_mm=2,
        sigma_distance_ppm=0,
        sigma_centering_mm=0,
        sigma_height_mm=5,
    )
    adj, known, _ = run_direct(truth, fixed, setups, settings=settings, rs=rs, approx_noise=0.02)
    assert adj is not None and adj.global_test is not None and not adj.global_test.passed

    req = PreanalysisRequest(
        points=[pt(n, x, y, n in fixed) for n, (x, y, _) in truth.items()],
        observations=[
            ob(kind, s.station, o.target)
            for s in setups
            for o in s.observations
            for kind in ("direction", "distance", "height")
        ],
        instrument=NO_CENTRING,
    )
    res = preanalyse(req)
    assert not [i for i in res.issues if i.severity == "error"]
    assert (res.n_observations, res.n_unknowns, res.dof) == (
        adj.n_observations,
        adj.n_unknowns,
        adj.dof,
    )
    pts = by_name(res)
    for name, kp in known.items():
        if kp.sx is None:
            continue
        p = pts[name]
        assert p.sx == pytest.approx(kp.sx, rel=1e-6)
        assert p.sy == pytest.approx(kp.sy, rel=1e-6)
        assert p.sz == pytest.approx(kp.sz, rel=1e-6)
        assert p.ellipse is not None and kp.ellipse is not None
        assert p.ellipse.a == pytest.approx(kp.ellipse.a, rel=1e-6)
        assert p.ellipse.b == pytest.approx(kp.ellipse.b, rel=1e-6)
        assert p.ellipse.theta == pytest.approx(kp.ellipse.theta, abs=1e-6)
    adj_r = {(o.kind, o.station, o.target): o.redundancy for o in adj.observations}
    for o in res.observations:
        assert o.redundancy == pytest.approx(adj_r[(o.kind, o.station, o.target)], abs=1e-7)
    assert math.fsum(o.redundancy for o in res.observations) == pytest.approx(res.dof)


# ----------------------------------------------------------------------- closed form


def test_closed_form_distances():
    """P at the origin; distances from A (east), C (west) and B (north), σ = 2 mm.
    x is fixed by two distances (σx = σ/√2, r = ½ each), y by one (σy = σ, r = 0)."""
    req = PreanalysisRequest(
        points=[
            pt("P", 0, 0),
            pt("A", 100, 0, True),
            pt("C", -100, 0, True),
            pt("B", 0, 100, True),
        ],
        observations=[ob("distance", "P", "A"), ob("distance", "P", "C"), ob("distance", "P", "B")],
        instrument=NO_CENTRING,
    )
    res = preanalyse(req)
    s = 0.002
    p = by_name(res)["P"]
    assert p.sx == pytest.approx(s / math.sqrt(2))
    assert p.sy == pytest.approx(s)
    assert p.spos == pytest.approx(math.hypot(s / math.sqrt(2), s))
    assert p.a95 == pytest.approx(K95 * s)
    assert p.b95 == pytest.approx(K95 * s / math.sqrt(2))
    a, c, b = res.observations
    d0, _ = reliability_constants(0.001, 0.8)
    assert a.redundancy == pytest.approx(0.5) and c.redundancy == pytest.approx(0.5)
    assert a.mdb == pytest.approx(d0 * s / math.sqrt(0.5))
    assert a.external == pytest.approx(d0)  # δ0·√((1 − ½)/½)
    # a bias ∇ in P–A moves P by ∇/2 along x
    assert a.mdb is not None
    assert a.max_shift == pytest.approx(a.mdb / 2) and a.max_shift_point == "P"
    assert a.status == "ok"
    assert b.redundancy == pytest.approx(0.0, abs=1e-12) and b.status == "uncontrolled"
    assert b.mdb is None
    assert any(i.code == "PREANALYSIS_UNCONTROLLED" for i in res.issues)


def test_closed_form_heights():
    """Height of P from two fixed points at equal distance: σz = σ/√2, r = ½."""
    req = PreanalysisRequest(
        points=[pt("P", 0, 0), pt("A", 1000, 0, True), pt("B", -1000, 0, True)],
        observations=[ob("height", "A", "P"), ob("height", "P", "B")],
        instrument=NO_CENTRING,
    )
    res = preanalyse(req)
    p = by_name(res)["P"]
    assert p.sz == pytest.approx(0.005 / math.sqrt(2))
    assert p.sx is None  # height-only point
    assert [o.redundancy for o in res.observations] == pytest.approx([0.5, 0.5])
    first = res.observations[0]
    assert first.mdb is not None and first.max_shift == pytest.approx(first.mdb / 2)


# --------------------------------------------- independent dense model (finite differences)


def _numeric_q(points, fixed, obs, sig):
    """Dense A by central differences of the observation functions; Q = (AᵀPA)⁻¹."""
    free = sorted(n for n in points if n not in fixed)
    stations = sorted({s for k, s, _ in obs if k == "direction"})
    cols = {n: 2 * i for i, n in enumerate(free)}
    ocol = {s: 2 * len(free) + j for j, s in enumerate(stations)}
    n = 2 * len(free) + len(stations)

    def f(vec, k, s, t):
        def xy(name):
            return (vec[cols[name]], vec[cols[name] + 1]) if name in cols else points[name]

        (xs, ys), (xt, yt) = xy(s), xy(t)
        if k == "distance":
            return math.hypot(xt - xs, yt - ys)
        return math.atan2(xt - xs, yt - ys) - vec[ocol[s]]

    x0 = np.zeros(n)
    for name, c in cols.items():
        x0[c], x0[c + 1] = points[name]
    a = np.zeros((len(obs), n))
    h = 1e-4
    for r, (k, s, t) in enumerate(obs):
        for j in range(n):
            e = np.zeros(n)
            e[j] = h
            a[r, j] = (f(x0 + e, k, s, t) - f(x0 - e, k, s, t)) / (2 * h)
    p = np.diag([1 / sig(k, s, t) ** 2 for k, s, t in obs])
    return np.linalg.inv(a.T @ p @ a), cols


def test_matches_dense_numerical_model_and_relative_ellipse():
    points = {
        "A": (1000.0, 1000.0),
        "B": (1600.0, 1100.0),
        "N1": (1200.0, 1350.0),
        "N2": (1450.0, 1500.0),
        "C": (1800.0, 1600.0),
    }
    fixed = {"A", "B", "C"}
    obs = []
    for s, ts in {"N1": ["A", "N2", "B"], "N2": ["N1", "C", "B"], "A": ["N1", "B"]}.items():
        for t in ts:
            obs += [("direction", s, t), ("distance", s, t)]
    spec = InstrumentSpec(
        sigma_direction_cc=6,
        sigma_distance_mm=1.5,
        sigma_distance_ppm=2,
        sigma_centering_instrument_mm=0.7,
        sigma_centering_target_mm=1.0,
    )

    def sig(k, s, t):
        (xs, ys), (xt, yt) = points[s], points[t]
        return observation_sigma(k, math.hypot(xt - xs, yt - ys), spec)

    q, cols = _numeric_q(points, fixed, obs, sig)
    res = preanalyse(
        PreanalysisRequest(
            points=[pt(n, x, y, n in fixed) for n, (x, y) in points.items()],
            observations=[ob(k, s, t) for k, s, t in obs],
            instrument=spec,
            relative_pairs=[("N1", "N2"), ("N2", "C"), ("N1", "N2")],
        )
    )
    pts = by_name(res)
    for name, c in cols.items():
        assert pts[name].sx == pytest.approx(math.sqrt(q[c, c]), rel=1e-6)
        assert pts[name].sy == pytest.approx(math.sqrt(q[c + 1, c + 1]), rel=1e-6)
    # relative N1–N2 by direct propagation of Δ = X2 − X1
    j = np.zeros((2, q.shape[0]))
    j[0, cols["N2"]], j[0, cols["N1"]] = 1, -1
    j[1, cols["N2"] + 1], j[1, cols["N1"] + 1] = 1, -1
    qd = j @ q @ j.T
    dx = points["N2"][0] - points["N1"][0]
    dy = points["N2"][1] - points["N1"][1]
    d = math.hypot(dx, dy)
    g = np.array([dx / d, dy / d])
    rel = {(r.frm, r.to): r for r in res.relative}
    assert len(res.relative) == 2  # duplicate pair dropped
    r12 = rel[("N1", "N2")]
    assert r12.s_distance == pytest.approx(math.sqrt(g @ qd @ g), rel=1e-6)
    lam = np.linalg.eigvalsh(qd)
    assert r12.ellipse.a == pytest.approx(math.sqrt(lam[1]), rel=1e-6)
    assert r12.ellipse.b == pytest.approx(math.sqrt(lam[0]), rel=1e-6)
    assert r12.s_transverse == pytest.approx(r12.distance * r12.s_azimuth)
    # one fixed endpoint: relative = absolute
    abs_n2 = pts["N2"].ellipse
    assert abs_n2 is not None
    assert rel[("N2", "C")].ellipse.a == pytest.approx(abs_n2.a, rel=1e-9)


# --------------------------------------------------------------------- datum and defects


def test_datum_defect_one_control_point():
    res = preanalyse(
        PreanalysisRequest(
            points=[pt("A", 0, 0, True), pt("N", 100, 0), pt("M", 50, 80)],
            observations=[
                ob(k, s, t)
                for s, t in (("A", "N"), ("N", "M"), ("M", "A"))
                for k in ("direction", "distance")
            ],
        )
    )
    assert [i.code for i in res.issues if i.severity == "error"] == ["PREANALYSIS_DATUM"]
    assert res.points == [] and all(o.status == "excluded" for o in res.observations)


def test_singular_collinear_intersection():
    """N fixed only by distances along one line: the transverse direction is undetermined."""
    res = preanalyse(
        PreanalysisRequest(
            points=[pt("A", 0, 0, True), pt("N", 100, 0), pt("B", 200, 0, True)],
            observations=[ob("distance", "A", "N"), ob("distance", "N", "B")],
        )
    )
    assert any(i.code == "PREANALYSIS_SINGULAR" for i in res.issues)
    assert res.points == []


def test_undetermined_point_is_reported_and_excluded():
    res = preanalyse(
        PreanalysisRequest(
            points=[
                pt("A", 0, 0, True),
                pt("B", 300, 0, True),
                pt("N", 150, 120),
                pt("H", 150, 300),
            ],
            observations=[
                ob("direction", "N", "A"),
                ob("direction", "N", "B"),
                ob("distance", "N", "A"),
                ob("distance", "N", "B"),
                ob("direction", "N", "H"),  # H gets one observation only
            ],
        )
    )
    assert res.excluded_points == ["H"]
    assert res.observations[-1].status == "excluded"
    assert any(i.code == "PREANALYSIS_UNDETERMINED" for i in res.issues)
    assert "N" in by_name(res)


def test_weak_observations_flagged():
    """Free station with four symmetric directions only: dof = 1 shared equally, r = ¼."""
    res = preanalyse(
        PreanalysisRequest(
            points=[
                pt("N", 0, 0),
                pt("A", 0, 300, True),
                pt("B", 300, 0, True),
                pt("C", 0, -300, True),
                pt("D", -300, 0, True),
            ],
            observations=[ob("direction", "N", t) for t in "ABCD"],
        )
    )
    assert res.dof == 1
    assert [o.redundancy for o in res.observations] == pytest.approx([0.25] * 4)
    assert all(o.status == "weak" for o in res.observations)
    assert any(i.code == "PREANALYSIS_WEAK" for i in res.issues)


@pytest.mark.parametrize(
    ("obs", "msg"),
    [
        ([ob("distance", "A", "X")], "unknown point"),
        ([ob("distance", "A", "A")], "same point"),
        ([ob("distance", "A", "Z")], "coincide"),
    ],
)
def test_validation_errors(obs, msg):
    with pytest.raises(ValueError, match=msg):
        preanalyse(
            PreanalysisRequest(
                points=[pt("A", 0, 0, True), pt("B", 1, 1), pt("Z", 0, 0.0001)], observations=obs
            )
        )


def test_duplicate_points_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        preanalyse(
            PreanalysisRequest(
                points=[pt("A", 0, 0), pt("A", 1, 1)], observations=[ob("distance", "A", "A")]
            )
        )


def test_messages_exist():
    for code in (
        "PREANALYSIS_DATUM",
        "PREANALYSIS_SINGULAR",
        "PREANALYSIS_UNDETERMINED",
        "PREANALYSIS_UNCONTROLLED",
        "PREANALYSIS_WEAK",
    ):
        assert code in EL


def test_reliability_against_w_test_power():
    """An error of size ∇ = MDB is found by the w-test with probability β0 (Baarda): its
    expected w equals δ0, so pt(|w| > N⁻¹(1 − α0/2)) ≈ β0."""
    d0, _ = reliability_constants(0.001, 0.8)
    k = NormalDist().inv_cdf(1 - 0.001 / 2)
    assert 1 - NormalDist(mu=d0).cdf(k) == pytest.approx(0.8, abs=1e-3)


def test_large_network_is_fast():
    import time

    nx, ny = 20, 25  # 500 points, 4 neighbours each → ≈ 3800 observations
    pts = [
        pt(f"P{i}_{j}", 1000 + 200 * i + 7 * (j % 3), 2000 + 200 * j, (i, j) in {(0, 0), (19, 24)})
        for i in range(nx)
        for j in range(ny)
    ]
    obs = []
    for i in range(nx):
        for j in range(ny):
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= i + di < nx and 0 <= j + dj < ny:
                    obs.append(ob("direction", f"P{i}_{j}", f"P{i + di}_{j + dj}"))
                    if di > 0 or dj > 0:
                        obs.append(ob("distance", f"P{i}_{j}", f"P{i + di}_{j + dj}"))
    assert len(obs) <= 5000
    t0 = time.perf_counter()
    res = preanalyse(PreanalysisRequest(points=pts, observations=obs))
    assert time.perf_counter() - t0 < 15
    assert len(res.points) == 498
