"""Levelling network adjustment: synthetic networks with known truth, statistics, loops, datum."""

import math

import numpy as np
import pytest
from pydantic import ValidationError

from atsurvey.core._lsq import chi2_ppf
from atsurvey.core.levelnet import (
    LevelNetBenchmark,
    LevelNetLine,
    LevelNetRequest,
    adjust_level_network,
)

TRUTH = {
    "RM1": 100.000,
    "RM2": 112.345,
    "A": 103.210,
    "B": 107.654,
    "C": 109.999,
    "D": 104.321,
    "E": 111.111,
    "F": 101.234,
}
# (from, to, km): a redundant network with several loops and a connection RM1 … RM2
TOPOLOGY = [
    ("RM1", "A", 0.8),
    ("A", "B", 1.1),
    ("B", "C", 0.6),
    ("C", "RM2", 0.9),
    ("RM1", "D", 0.7),
    ("D", "B", 1.3),
    ("D", "E", 1.6),
    ("E", "RM2", 0.5),
    ("C", "E", 0.7),
    ("A", "F", 0.4),
    ("F", "RM1", 0.5),
    ("F", "D", 0.9),
    ("A", "D", 0.6),
    ("B", "E", 1.2),
]
SIGMA_KM_MM = 1.5


def make_lines(rng=None, blunder=None, sigma=SIGMA_KM_MM):
    out = []
    for i, (a, b, km) in enumerate(TOPOLOGY):
        dh = TRUTH[b] - TRUTH[a]
        if rng is not None:
            dh += rng.normal(0.0, sigma * math.sqrt(km) / 1000.0)
        if blunder is not None and blunder[0] == i:
            dh += blunder[1]
        out.append(LevelNetLine(frm=a, to=b, dh=dh, length_km=km))
    return out


def bms(*names):
    return [LevelNetBenchmark(name=n, h=TRUTH[n]) for n in names]


def req(lines, benchmarks, **kw):
    return LevelNetRequest(
        benchmarks=benchmarks, lines=lines, sigma_mm_per_sqrt_km=SIGMA_KM_MM, **kw
    )


def test_chi2_quantiles_match_tables():
    assert chi2_ppf(0.975, 1) == pytest.approx(5.023886, abs=1e-5)
    assert chi2_ppf(0.025, 1) == pytest.approx(0.000982069, rel=1e-4)
    assert chi2_ppf(0.95, 10) == pytest.approx(18.307038, abs=1e-5)
    assert chi2_ppf(0.05, 100) == pytest.approx(77.929465, abs=1e-4)


def test_noise_free_network_recovers_truth_exactly():
    r = adjust_level_network(req(make_lines(), bms("RM1", "RM2")))
    for p in r.points:
        assert p.h == pytest.approx(TRUTH[p.name], abs=1e-9)
    assert all(abs(ln.residual) < 1e-9 for ln in r.lines)
    assert r.dof == len(TOPOLOGY) - 6
    assert len(r.loops) == r.dof  # one independent condition per degree of freedom
    assert all(abs(lp.misclosure) < 1e-9 for lp in r.loops)
    assert sum(lp.kind == "connection" for lp in r.loops) == 1
    assert r.suspect_line is None


def test_hand_computed_two_benchmark_line():
    # A=100, B=110, A→X +5.010 (1 km), X→B +5.000 (1 km): w = +10 mm, half to each line
    r = adjust_level_network(
        LevelNetRequest(
            benchmarks=[LevelNetBenchmark(name="A", h=100), LevelNetBenchmark(name="B", h=110)],
            lines=[
                LevelNetLine(frm="A", to="X", dh=5.010, length_km=1),
                LevelNetLine(frm="X", to="B", dh=5.000, length_km=1),
            ],
            sigma_mm_per_sqrt_km=2.0,
        )
    )
    x = next(p for p in r.points if p.name == "X")
    assert x.h == pytest.approx(105.005, abs=1e-12)
    assert r.lines[0].residual == pytest.approx(-0.005)
    assert r.lines[1].residual == pytest.approx(-0.005)
    (conn,) = r.loops
    assert conn.kind == "connection" and conn.misclosure == pytest.approx(0.010)
    assert conn.points == ["A", "X", "B"] or conn.points == ["B", "X", "A"]
    # vᵀPv = 2·25/4 = 12.5 ≫ χ²(0.975, 1): test fails → a priori σ for σH: √(4/2) mm
    assert r.global_test is not None and not r.global_test.passed
    assert r.variance_factor == 1.0
    assert x.sigma_h == pytest.approx(math.sqrt(2e-6))
    assert any(i.code == "LEVNET_GLOBAL_TEST" for i in r.issues)
    assert r.lines[0].redundancy == pytest.approx(0.5)


def test_sigma0_is_about_one_over_many_noisy_networks():
    rng = np.random.default_rng(42)
    omegas, dofs, inside = [], [], 0
    for _ in range(300):
        r = adjust_level_network(req(make_lines(rng), bms("RM1", "RM2")))
        omegas.append(r.global_test.statistic)  # type: ignore[union-attr]
        dofs.append(r.dof)
        for p in r.points:
            if p.kind == "adjusted":
                inside += abs(p.h - TRUTH[p.name]) <= 3 * math.sqrt(
                    p.sigma_h**2 / r.variance_factor
                )
    # E[Ω] = f: the mean variance factor is 1 within sampling error (≈ ±0.07 for 300 runs)
    assert sum(omegas) / sum(dofs) == pytest.approx(1.0, abs=0.08)
    assert inside / (300 * 6) > 0.98  # 3σ coverage of the true heights


def test_blunder_is_caught_by_the_w_test():
    rng = np.random.default_rng(7)
    r = adjust_level_network(req(make_lines(rng, blunder=(6, 0.025)), bms("RM1", "RM2")))
    assert r.suspect_line == 6
    flagged = [ln for ln in r.lines if ln.flagged]
    assert [ln.index for ln in flagged] == [6]
    assert abs(flagged[0].w or 0) > r.w_critical
    assert r.global_test is not None and not r.global_test.passed
    codes = {i.code for i in r.issues}
    assert {"LEVNET_BLUNDER", "LEVNET_GLOBAL_TEST"} <= codes
    blunder_issue = next(i for i in r.issues if i.code == "LEVNET_BLUNDER")
    assert blunder_issue.params["line"] == 7 and blunder_issue.params["frm"] == "D"
    # the MDB of the line is smaller than the injected error
    assert flagged[0].mdb is not None and flagged[0].mdb < 0.025


def test_loop_misclosure_identity_with_residuals():
    rng = np.random.default_rng(3)
    lines = make_lines(rng)
    r = adjust_level_network(req(lines, bms("RM1", "RM2")))
    res = {ln.index: ln.residual for ln in r.lines}
    for lp in r.loops:
        # the adjusted Δh close every loop exactly: Σ ±(Δh + v) = known difference
        assert math.fsum(s * res[i] for i, s in zip(lp.lines, lp.signs, strict=True)) == (
            pytest.approx(-lp.misclosure, abs=1e-12)
        )
        raw = math.fsum(s * lines[i].dh for i, s in zip(lp.lines, lp.signs, strict=True))
        if lp.kind == "loop":
            assert lp.points[0] == lp.points[-1]
            assert raw == pytest.approx(lp.misclosure, abs=1e-12)
        else:
            known = TRUTH[lp.points[-1]] - TRUTH[lp.points[0]]
            assert raw - known == pytest.approx(lp.misclosure, abs=1e-12)
        assert lp.length_km == pytest.approx(sum(lines[i].length_km or 0 for i in lp.lines))
        assert lp.tolerance == pytest.approx(0.012 * math.sqrt(lp.length_km or 0))


def test_loop_tolerance_issue():
    lines = make_lines(blunder=(1, 0.05))
    r = adjust_level_network(req(lines, bms("RM1", "RM2")))
    assert any(lp.within_tolerance is False for lp in r.loops)
    assert any(i.code == "LEVNET_LOOP_TOLERANCE" for i in r.issues)


def test_single_benchmark_equals_free_network_on_that_benchmark():
    rng = np.random.default_rng(11)
    lines = make_lines(rng)
    fixed = adjust_level_network(req(lines, bms("RM1")))
    free = adjust_level_network(req(lines, bms("RM1"), datum="free", free_points=["RM1"]))
    hf = {p.name: p for p in fixed.points}
    for p in free.points:
        assert p.h == pytest.approx(hf[p.name].h, abs=1e-9)
        assert p.sigma_h == pytest.approx(hf[p.name].sigma_h, abs=1e-9)
    assert fixed.dof == free.dof == len(TOPOLOGY) - 7
    assert fixed.sigma0 == pytest.approx(free.sigma0)


def test_free_network_keeps_the_mean_and_checks_benchmarks():
    rng = np.random.default_rng(5)
    lines = make_lines(rng)
    free = adjust_level_network(req(lines, bms("RM1", "RM2"), datum="free"))
    known = {p.name: p for p in free.points if p.known_h is not None}
    # default datum points: the benchmarks; their mean height is preserved
    assert math.fsum(p.h for p in known.values()) == pytest.approx(TRUTH["RM1"] + TRUTH["RM2"])
    assert math.fsum(p.known_diff or 0 for p in known.values()) == pytest.approx(0, abs=1e-12)
    assert all(p.kind == "adjusted" and p.sigma_h > 0 for p in free.points)
    # residuals do not depend on the datum (minimal constraint)
    one = adjust_level_network(req(lines, bms("RM1")))
    for a, b in zip(free.lines, one.lines, strict=True):
        assert a.residual == pytest.approx(b.residual, abs=1e-12)
    # all points as datum: mean of the adjusted heights = mean of the carried heights
    allp = adjust_level_network(req(lines, [], datum="free", free_points=list(TRUTH)))
    assert len(allp.points) == len(TRUTH)
    assert any(i.code == "LEVNET_NO_REDUNDANCY" for i in allp.issues) is False


def test_part_without_benchmark_is_reported_and_excluded():
    lines = [*make_lines(), LevelNetLine(frm="X1", to="X2", dh=1.0, length_km=0.3)]
    r = adjust_level_network(req(lines, bms("RM1", "RM2")))
    assert set(r.excluded_points) == {"X1", "X2"}
    assert {p.name for p in r.points} == set(TRUTH)
    issue = next(i for i in r.issues if i.code == "LEVNET_NO_DATUM")
    assert issue.severity == "error" and set(issue.params["points"]) == {"X1", "X2"}


def test_no_benchmark_at_all():
    r = adjust_level_network(req(make_lines(), [LevelNetBenchmark(name="ZZ", h=1)]))
    assert r.points == [] and r.dof == 0
    codes = {i.code for i in r.issues}
    assert {"LEVNET_NO_DATUM", "LEVNET_UNUSED_BENCHMARK"} <= codes


def test_free_network_must_be_connected():
    lines = [*make_lines(), LevelNetLine(frm="X1", to="X2", dh=1.0, length_km=0.3)]
    r = adjust_level_network(req(lines, [], datum="free"))
    assert any(i.code == "LEVNET_DISCONNECTED" for i in r.issues)
    assert set(r.excluded_points) == {"X1", "X2"}


def test_two_parts_each_with_a_benchmark():
    lines = [*make_lines(), LevelNetLine(frm="X1", to="X2", dh=1.0, length_km=0.3)]
    r = adjust_level_network(req(lines, [*bms("RM1", "RM2"), LevelNetBenchmark(name="X1", h=50.0)]))
    assert next(p.h for p in r.points if p.name == "X2") == pytest.approx(51.0)
    assert any(i.code == "LEVNET_PARTS" for i in r.issues)
    x2 = next(ln for ln in r.lines if ln.frm == "X1")
    assert x2.redundancy == pytest.approx(0.0) and x2.w is None


def test_setup_weights_and_parallel_lines():
    # the same section measured twice (parallel lines form a loop of two)
    lines = [
        LevelNetLine(frm="A", to="P", dh=1.002, setups=4),
        LevelNetLine(frm="A", to="P", dh=0.998, setups=4),
        LevelNetLine(frm="P", to="B", dh=2.0, setups=16),
    ]
    r = adjust_level_network(
        LevelNetRequest(
            benchmarks=[LevelNetBenchmark(name="A", h=10.0), LevelNetBenchmark(name="B", h=13.0)],
            lines=lines,
            weighting="setups",
            sigma_mm_per_setup=0.5,
            tolerance_mm_per_sqrt_setup=2.0,
        )
    )
    assert r.dof == 2 and len(r.loops) == 2
    loop = next(lp for lp in r.loops if lp.kind == "loop")
    assert abs(loop.misclosure) == pytest.approx(0.004)
    assert loop.setups == 8 and loop.tolerance == pytest.approx(0.002 * math.sqrt(8))
    p = next(p for p in r.points if p.name == "P")
    # weights 1/4, 1/4, 1/16 → normal equation solution
    expected = (11.002 / 4 + 10.998 / 4 + 11.0 / 16) / (1 / 4 + 1 / 4 + 1 / 16)
    assert p.h == pytest.approx(expected)


@pytest.mark.parametrize(
    ("lines", "kw", "msg"),
    [
        ([LevelNetLine(frm="A", to="B", dh=1)], {}, "needs a length"),
        ([LevelNetLine(frm="A", to="B", dh=1, length_km=1)], {"weighting": "setups"}, "setups"),
        ([LevelNetLine(frm="A", to="A", dh=1, length_km=1)], {}, "same point"),
    ],
)
def test_invalid_requests(lines, kw, msg):
    with pytest.raises(ValidationError, match=msg):
        LevelNetRequest(benchmarks=[LevelNetBenchmark(name="A", h=0)], lines=lines, **kw)


def test_duplicate_benchmarks_and_non_finite_values_are_rejected():
    line = LevelNetLine(frm="A", to="B", dh=1, length_km=1)
    with pytest.raises(ValidationError, match="unique"):
        LevelNetRequest(benchmarks=bms("RM1", "RM1"), lines=[line])
    with pytest.raises(ValidationError):
        LevelNetLine(frm="A", to="B", dh=float("nan"), length_km=1)


def test_unknown_free_datum_point():
    with pytest.raises(ValueError, match="not in the network"):
        adjust_level_network(req(make_lines(), [], datum="free", free_points=["NOPE"]))


def test_loop_basis_prefers_elementary_meshes():
    # a ladder of 3 square meshes: T0-T1-T2-T3 over B0-B1-B2-B3 with rungs Ti-Bi
    lines = [LevelNetLine(frm=f"T{i}", to=f"T{i + 1}", dh=0.1, length_km=1) for i in range(3)]
    lines += [LevelNetLine(frm=f"B{i}", to=f"B{i + 1}", dh=0.1, length_km=1) for i in range(3)]
    lines += [LevelNetLine(frm=f"T{i}", to=f"B{i}", dh=-1.0, length_km=1) for i in range(4)]
    r = adjust_level_network(
        LevelNetRequest(
            benchmarks=[LevelNetBenchmark(name="T0", h=10), LevelNetBenchmark(name="T3", h=10.3)],
            lines=lines,
        )
    )
    loops = [lp for lp in r.loops if lp.kind == "loop"]
    conns = [lp for lp in r.loops if lp.kind == "connection"]
    assert len(loops) == 3 and all(len(lp.lines) == 4 for lp in loops)
    assert all(abs(lp.misclosure) < 1e-12 for lp in r.loops)
    assert len(conns) == 1 and conns[0].points == ["T0", "T1", "T2", "T3"]
    assert len(r.loops) == r.dof
