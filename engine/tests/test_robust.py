"""Robust estimation (IRLS, Huber / Danish) in the least-squares adjustment.

Truth: a synthetic 5×5 network with Gaussian noise that matches the a priori model. The
clean solution is the plain adjustment of the noisy data without gross errors; the robust
solution of the same data plus injected gross errors must reproduce it within the noise.
"""

import copy
import json
import math
import random
from pathlib import Path

import pytest
from test_adjust import grid_setups, grid_truth, run_direct

from atsurvey.core.adjust import ROBUST_MIN_WEIGHT, robust_weight
from atsurvey.core.messages import EL
from atsurvey.core.models import AdjustmentSettings
from atsurvey.core.units import CC_TO_RAD

BASE = {
    "method": "least_squares",
    "sigma_direction_cc": 10,
    "sigma_distance_mm": 2,
    "sigma_distance_ppm": 0,
    "sigma_centering_mm": 0,
    "sigma_height_mm": 5,
}
FIXED = ["P0_0", "P4_4", "P0_4", "P4_0"]
GOLDEN = Path(__file__).parent / "fixtures" / "adjust_golden.json"


def settings(**kw) -> AdjustmentSettings:
    return AdjustmentSettings(**BASE, **kw)


@pytest.fixture(scope="module")
def network():
    truth = grid_truth(5, 5)
    setups = grid_setups(truth, 5, 5, rng=random.Random(42), noise=True, sig=settings())
    return truth, setups


def _obs(setups, station, target):
    s = next(s for s in setups if s.station == station)
    return next(o for o in s.observations if o.target == target)


def _with_blunders(setups, which):
    bad = copy.deepcopy(setups)
    if "direction" in which:
        _obs(bad, "P1_1", "P2_2").hz += 150 * CC_TO_RAD
    if "distance" in which:
        _obs(bad, "P3_2", "P3_3").sd += 0.06
    if "height" in which:
        _obs(bad, "P2_3", "P2_4").v += 0.0004  # ≈ 0.1 m at 250 m
    return bad


def _max_shift(known, ref):
    hz = max(math.hypot(known[n].x - ref[n].x, known[n].y - ref[n].y) for n in ref if ref[n].sx)
    vz = max(abs(known[n].z - ref[n].z) for n in ref if ref[n].sz)
    return hz, vz


# ------------------------------------------------------------------------- weight function


def test_weight_functions():
    assert robust_weight(2.0, "huber", 2.5) == 1.0
    assert robust_weight(-5.0, "huber", 2.5) == pytest.approx(0.5)
    assert robust_weight(10.0, "off", 2.5) == 1.0
    # Danish: continuous at c, decays exponentially, floored
    assert robust_weight(2.5 + 1e-9, "danish", 2.5) == pytest.approx(1.0)
    assert robust_weight(5.0, "danish", 2.5) == pytest.approx(math.exp(-3.0))
    assert robust_weight(100.0, "danish", 2.5) == ROBUST_MIN_WEIGHT


# -------------------------------------------------------------------- injected gross errors


@pytest.mark.parametrize("method", ["huber", "danish"])
@pytest.mark.parametrize(
    "which", [("direction",), ("direction", "distance"), ("direction", "distance", "height")]
)
def test_gross_errors_are_downweighted(network, method, which):
    truth, setups = network
    _, clean, _ = run_direct(truth, FIXED, setups, settings=settings())
    bad = _with_blunders(setups, which)
    _, plain, _ = run_direct(truth, FIXED, bad, settings=settings())
    res, rob, sink = run_direct(truth, FIXED, bad, settings=settings(robust=method))
    assert res is not None and res.robust is not None
    assert res.robust.converged and res.robust.method == method

    # every injected gross error carries (almost) no weight
    pairs = {
        "direction": ("P1_1", "P2_2"),
        "distance": ("P3_2", "P3_3"),
        "height": ("P2_3", "P2_4"),
    }
    for kind in which:
        st, tg = pairs[kind]
        o = next(o for o in res.observations if (o.kind, o.station, o.target) == (kind, st, tg))
        assert o.weight < 0.35, (kind, o.weight)
        assert o.flagged  # w (a priori σ) still names it
    assert any(i.code == "ROBUST_DOWNWEIGHTED" for i in sink.items)

    # the robust solution reproduces the clean one within the noise (≈ 1 mm here) …
    hz, vz = _max_shift(rob, clean)
    assert hz < 1.5e-3 and vz < 1.0e-3, (hz, vz)
    # … while the plain adjustment is visibly pulled away by the same errors
    hz_plain, _ = _max_shift(plain, clean)
    assert hz_plain > 3 * hz


def test_clean_data_robust_changes_little(network):
    truth, setups = network
    _, clean, _ = run_direct(truth, FIXED, setups, settings=settings())
    res, rob, _ = run_direct(truth, FIXED, setups, settings=settings(robust="huber"))
    assert res is not None and res.robust is not None
    # with matching noise only the tails (|w| > 2.5, a few %) lose some weight
    assert res.robust.downweighted < 0.06 * res.n_observations
    hz, vz = _max_shift(rob, clean)
    assert hz < 1e-3 and vz < 1e-3


def test_robust_statistics_are_consistent(network):
    """σ0 and the global test are those of the final re-weighted least-squares solution."""
    truth, setups = network
    bad = _with_blunders(setups, ("direction", "distance", "height"))
    res, _, _ = run_direct(truth, FIXED, bad, settings=settings(robust="danish"))
    assert res is not None and res.global_test is not None
    vtpv = math.fsum(o.weight * (o.residual / o.sigma) ** 2 for o in res.observations)
    assert res.global_test.statistic == pytest.approx(vtpv, rel=1e-9)
    assert res.sigma0 == pytest.approx(math.sqrt(vtpv / res.dof), rel=1e-9)
    assert res.global_test.passed  # gross errors no longer inflate σ0
    for o in res.observations:  # w uses the a priori σ and the final redundancy numbers
        if o.w is not None:
            assert o.w == pytest.approx(o.residual / (o.sigma * math.sqrt(o.redundancy)))


def test_not_converged_is_reported(network):
    truth, setups = network
    bad = _with_blunders(setups, ("direction", "distance"))
    res, _, sink = run_direct(
        truth, FIXED, bad, settings=settings(robust="danish", robust_max_iterations=1)
    )
    assert res is not None and res.robust is not None and not res.robust.converged
    assert any(i.code == "ROBUST_NOT_CONVERGED" for i in sink.items)


def test_messages_exist():
    assert "ROBUST_DOWNWEIGHTED" in EL and "ROBUST_NOT_CONVERGED" in EL


# ------------------------------------------------------------------ off = unchanged results


def _golden_case():
    """The case whose plain least-squares output is stored in fixtures/adjust_golden.json."""
    truth = grid_truth(4, 4)
    sig = AdjustmentSettings(method="least_squares", sigma_centering_mm=1.0, sigma_distance_ppm=2.0)
    setups = grid_setups(truth, 4, 4, rng=random.Random(77), noise=True, sig=sig)
    _obs(setups, "P1_1", "P2_2").hz += 40 * CC_TO_RAD
    return truth, setups, sig


def test_off_reproduces_the_results_from_before_robust_estimation():
    """Results captured with the code before this feature (09bd164); locally they were
    bit-identical, here 1e-9 relative is allowed for LAPACK differences between machines."""
    g = json.loads(GOLDEN.read_text())
    truth, setups, sig = _golden_case()
    res, known, sink = run_direct(truth, ["P0_0", "P3_3", "P0_3"], setups, settings=sig)
    assert res is not None and res.robust is None
    assert res.sigma0 == pytest.approx(g["sigma0"], rel=1e-9)
    assert res.global_test is not None
    assert res.global_test.statistic == pytest.approx(g["global"], rel=1e-9)
    assert (res.dof, res.iterations) == (g["dof"], g["iterations"])
    assert [i.code for i in sink.items] == g["issues"]
    assert len(res.observations) == len(g["observations"])
    for o, (kind, st, tg, adj, v, r, w) in zip(res.observations, g["observations"], strict=True):
        assert (o.kind, o.station, o.target) == (kind, st, tg)
        assert o.weight == 1.0
        assert o.adjusted == pytest.approx(adj, rel=1e-12, abs=1e-12)
        assert o.residual == pytest.approx(v, rel=1e-7, abs=1e-11)
        assert o.redundancy == pytest.approx(r, rel=1e-9, abs=1e-12)
        assert (o.w is None) == (w is None)
        if w is not None:
            assert o.w == pytest.approx(w, rel=1e-7, abs=1e-9)
    for name, (x, y, z, sx, sy, sz, ell) in g["known"].items():
        k = known[name]
        assert (k.x, k.y) == pytest.approx((x, y), abs=1e-9)
        assert k.z == pytest.approx(z, abs=1e-9)
        if sx is not None:
            assert (k.sx, k.sy) == pytest.approx((sx, sy), rel=1e-9)
            assert k.ellipse is not None
            assert (k.ellipse.a, k.ellipse.b) == pytest.approx(tuple(ell[:2]), rel=1e-9)
        if sz is not None:
            assert k.sz == pytest.approx(sz, rel=1e-9)


def test_off_equals_default_settings(network):
    truth, setups = network
    a, ka, _ = run_direct(truth, FIXED, setups, settings=settings())
    b, kb, _ = run_direct(truth, FIXED, setups, settings=settings(robust="off"))
    assert a is not None and b is not None
    assert a.model_dump() == b.model_dump()
    assert all((ka[n].x, ka[n].y, ka[n].sx) == (kb[n].x, kb[n].y, kb[n].sx) for n in ka)
