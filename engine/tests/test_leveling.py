import itertools
import math

import pytest

from atsurvey.core.cogo_models import (
    Benchmark,
    LevelingReading,
    LevelingRequest,
    LevelingSetup,
)
from atsurvey.core.leveling import level


def setup(bs, bsr, fs, fsr, dist=None, inter=()):
    rs = [
        LevelingReading(point=bs, reading=bsr, kind="bs", distance=dist),
        *[LevelingReading(point=p, reading=r, kind="is", distance=dist) for p, r in inter],
        LevelingReading(point=fs, reading=fsr, kind="fs", distance=dist),
    ]
    return LevelingSetup(readings=rs)


def test_closed_on_second_benchmark_by_distance():
    # BM1 100.000 → TP1 → TP2 → BM2 101.000; raw rise 1.004 → misclosure −4 mm
    setups = [
        setup("BM1", 1.500, "TP1", 1.200, dist=50),  # +0.300
        setup("TP1", 1.400, "TP2", 1.000, dist=30),  # +0.400
        setup("TP2", 1.304, "BM2", 1.000, dist=20),  # +0.304
    ]
    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="BM1", h=100.0), Benchmark(name="BM2", h=101.0)],
            setups=setups,
        )
    )
    assert r.misclosure == pytest.approx(-0.004)
    assert r.length_km == pytest.approx(0.2)
    assert r.tolerance == pytest.approx(0.012 * math.sqrt(0.2))
    assert r.within_tolerance is True
    pts = {p.name: p for p in r.points}
    # corrections proportional to cumulative distance: 100/200, 160/200, 200/200 of −4 mm
    assert pts["TP1"].correction == pytest.approx(-0.002)
    assert pts["TP2"].correction == pytest.approx(-0.0032)
    assert pts["TP1"].h == pytest.approx(100.300 - 0.002)
    assert pts["BM2"].h == pytest.approx(101.0) and pts["BM2"].kind == "benchmark"
    assert pts["BM2"].h_unadjusted == pytest.approx(101.004)
    assert [row.dh for row in r.rows] == [pytest.approx(v) for v in (0.3, 0.4, 0.304)]


def test_misclosure_beyond_tolerance_is_flagged():
    setups = [setup("BM1", 1.5, "TP", 1.2, dist=50), setup("TP", 1.4, "BM2", 0.694, dist=50)]
    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="BM1", h=100.0), Benchmark(name="BM2", h=101.0)],
            setups=setups,
        )
    )
    # −6 mm over 0.2 km against 12 mm·√0.2 = 5.37 mm
    assert r.misclosure == pytest.approx(-0.006)
    assert r.within_tolerance is False


def test_loop_returns_to_start_by_setups():
    setups = [
        setup("BM", 1.000, "A", 2.000),  # −1.000
        setup("A", 1.500, "B", 0.500),  # +1.000
        setup("B", 1.200, "BM", 1.196),  # +0.004 → misclosure −4 mm
    ]
    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="BM", h=50.0)], setups=setups, distribute="setups"
        )
    )
    assert r.start == r.end == "BM"
    assert r.misclosure == pytest.approx(-0.004)
    pts = {p.name: p for p in r.points}
    assert pts["A"].correction == pytest.approx(-0.004 / 3)
    assert pts["B"].correction == pytest.approx(-0.008 / 3)
    assert pts["BM"].h == pytest.approx(50.0)
    assert r.tolerance is None and r.within_tolerance is None  # no distances
    assert r.message and "tolerance" in r.message


def test_distance_mode_falls_back_without_distances():
    setups = [setup("BM1", 1.0, "TP", 1.0), setup("TP", 1.0, "BM2", 0.99)]
    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="BM1", h=10.0), Benchmark(name="BM2", h=10.0)],
            setups=setups,
        )
    )
    assert r.misclosure == pytest.approx(-0.01)
    assert "equally per setup" in (r.message or "")
    assert {p.name: p for p in r.points}["TP"].correction == pytest.approx(-0.005)


def test_open_line_and_intermediate_sights():
    setups = [
        setup("BM", 1.500, "TP", 0.500, dist=40, inter=[("X1", 1.000), ("X2", 2.000)]),
        setup("TP", 1.000, "END", 1.500, dist=40),
    ]
    r = level(LevelingRequest(benchmarks=[Benchmark(name="BM", h=20.0)], setups=setups))
    assert r.misclosure is None and r.within_tolerance is None
    assert r.message and "Open line" in r.message
    pts = {p.name: p for p in r.points}
    assert pts["X1"].h == pytest.approx(20.5) and pts["X1"].kind == "intermediate"
    assert pts["X2"].h == pytest.approx(19.5)
    assert pts["END"].h == pytest.approx(20.5)


def test_intermediate_sight_gets_interpolated_correction():
    setups = [
        setup("BM1", 1.0, "TP", 1.0, dist=50, inter=[("X", 1.2)]),
        setup("TP", 1.0, "BM2", 1.0, dist=50),
    ]
    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="BM1", h=10.0), Benchmark(name="BM2", h=10.01)],
            setups=setups,
        )
    )
    pts = {p.name: p for p in r.points}
    # setup 1 gets half of +10 mm; its instrument height half of that (equal sights)
    assert pts["TP"].correction == pytest.approx(0.005)
    assert pts["X"].correction == pytest.approx(0.0025)
    assert pts["X"].h == pytest.approx(10.0 + 1.0 - 1.2 + 0.0025)


def test_validation_errors():
    with pytest.raises(ValueError, match="benchmark"):
        level(
            LevelingRequest(benchmarks=[Benchmark(name="Z", h=0)], setups=[setup("A", 1, "B", 1)])
        )
    with pytest.raises(ValueError, match="foresight point"):
        level(
            LevelingRequest(
                benchmarks=[Benchmark(name="A", h=0)],
                setups=[setup("A", 1, "B", 1), setup("C", 1, "D", 1)],
            )
        )
    bad = LevelingSetup(
        readings=[
            LevelingReading(point="A", reading=1, kind="bs"),
            LevelingReading(point="B", reading=1, kind="bs"),
        ]
    )
    with pytest.raises(ValueError, match="exactly one"):
        level(LevelingRequest(benchmarks=[Benchmark(name="A", h=0)], setups=[bad]))


# --------------------------------------------------------------- double-run (μετάβαση–επιστροφή)


def _chain(points: list[tuple[str, float | None, float | None]]):
    """[(point, foresight reading, backsight reading)] → LevelingSetup list."""
    from atsurvey.core.cogo_models import LevelingReading, LevelingSetup

    setups = []
    for (p0, _fs0, bs0), (p1, fs1, _bs1) in itertools.pairwise(points):
        assert bs0 is not None and fs1 is not None
        setups.append(
            LevelingSetup(
                readings=[
                    LevelingReading(point=p0, reading=bs0, kind="bs"),
                    LevelingReading(point=p1, reading=fs1, kind="fs"),
                ]
            )
        )
    return setups


# The user's reference workbook (ΧΩΡΟΣΤΑΘΜΙΣΗ): forward Rn → Σ27 and return Σ27 → Rn.
FORWARD = [
    ("Rn", None, 0.794),
    ("Κ1", 1.298, 1.717),
    ("Κ2", 0.501, 2.567),
    ("Σ22", 0.072, 2.877),
    ("Κ3", 0.305, 2.779),
    ("Σ23", 0.159, 1.849),
    ("Κ4", 1.561, 1.591),
    ("Σ24", 1.164, 1.95),
    ("Κ5", 1.02, 1.912),
    ("Σ25", 0.857, 0.828),
    ("Κ6", 2.843, 0.065),
    ("Σ26", 1.89, 0.5),
    ("Σ27", 2.864, None),
]
RETURN = [
    ("Σ27", None, 2.864),
    ("Σ26", 0.498, 1.91),
    ("Κ6", 0.085, 2.544),
    ("Σ25", 0.832, 0.871),
    ("Κ5", 1.946, 1.009),
    ("Σ24", 1.937, 1.166),
    ("Κ4", 1.593, 1.588),
    ("Σ23", 1.875, 0.168),
    ("Κ3", 2.787, 0.32),
    ("Σ22", 2.891, 0.065),
    ("Κ2", 2.561, 0.497),
    ("Κ1", 1.713, 1.315),
    ("Rn", 0.811, None),
]
SECTIONS = ["Rn", "Σ22", "Σ23", "Σ24", "Σ25", "Σ26", "Σ27"]


def test_double_run_reference_workbook_finds_the_blunder():
    from atsurvey.core.cogo_models import Benchmark, LevelingRequest
    from atsurvey.core.leveling import level

    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="Rn", h=192.419)],
            setups=_chain(FORWARD),
            return_setups=_chain(RETURN),
            section_points=SECTIONS,
        )
    )
    disc = {f"{s.frm}-{s.to}": round(s.discrepancy * 1000, 1) for s in r.sections}
    # forward and return agree within a few mm except Σ24–Σ25 (18 mm) and Σ25–Σ26 (303 mm):
    # the staff reading on Κ6 is 2.843 forward but 2.544 on the return run (a 0.3 m misread)
    assert disc == {
        "Rn-Σ22": -1.0,
        "Σ22-Σ23": 2.0,
        "Σ23-Σ24": 1.0,
        "Σ24-Σ25": -18.0,
        "Σ25-Σ26": -303.0,
        "Σ26-Σ27": 2.0,
    }
    mean = {f"{s.frm}-{s.to}": s.dh_mean for s in r.sections}
    assert mean["Rn-Σ22"] == pytest.approx(3.2075)
    assert r.misclosure is None  # Σ27 is not a benchmark
    assert [p.name for p in r.points] == SECTIONS


def test_double_run_perfect_data_and_closure_distribution():
    from atsurvey.core.cogo_models import Benchmark, LevelingReading, LevelingRequest, LevelingSetup
    from atsurvey.core.leveling import level

    def s(bs_p, bs, fs_p, fs, d=50.0):
        return LevelingSetup(
            readings=[
                LevelingReading(point=bs_p, reading=bs, kind="bs", distance=d),
                LevelingReading(point=fs_p, reading=fs, kind="fs", distance=d),
            ]
        )

    fwd = [s("A", 1.5, "T1", 1.0), s("T1", 1.2, "P", 1.6), s("P", 1.4, "B", 1.0)]
    ret = [s("B", 1.0, "T9", 1.3), s("T9", 1.6, "P", 1.7), s("P", 1.1, "A", 1.2)]
    r = level(
        LevelingRequest(
            benchmarks=[Benchmark(name="A", h=100.0), Benchmark(name="B", h=100.505)],
            setups=fwd,
            return_setups=ret,
        )
    )
    secs = {f"{x.frm}-{x.to}": x for x in r.sections}
    assert set(secs) == {"A-P", "P-B"}  # turning points T1/T9 are not common to both runs
    assert secs["A-P"].discrepancy == pytest.approx(0.0, abs=1e-12)
    assert secs["P-B"].discrepancy == pytest.approx(0.0, abs=1e-12)
    # mean ΔH A→B = 0.5, benchmark says 0.505 → 5 mm distributed by section length (equal)
    assert r.misclosure == pytest.approx(0.005)
    h = {p.name: p for p in r.points}
    assert h["P"].h == pytest.approx(100.1 + 0.0025)
    assert h["B"].h == 100.505 and r.within_tolerance is True


def test_double_run_validation():
    from atsurvey.core.cogo_models import Benchmark, LevelingRequest
    from atsurvey.core.leveling import level

    with pytest.raises(ValueError, match="return run must go"):
        level(
            LevelingRequest(
                benchmarks=[Benchmark(name="Rn", h=0.0)],
                setups=_chain(FORWARD),
                return_setups=_chain(FORWARD),
            )
        )
