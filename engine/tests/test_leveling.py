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
