"""Coverage check of parts against an outline (Cadastre: no gaps, no overlaps, no slivers)."""

from __future__ import annotations

import random

import pytest

from atsurvey.core.parcels_coverage import check_coverage
from atsurvey.core.parcels_models import CoverageRequest, Parcel, ParcelVertex, SubdivideRequest
from atsurvey.core.parcels_subdivide import subdivide

E0, N0 = 476_123.457, 4_205_987.123


def parcel(pts, label: str = "") -> Parcel:
    return Parcel(label=label, vertices=[ParcelVertex(name=n, x=x, y=y) for n, x, y in pts])


def codes(issues) -> list[str]:
    return [i.code for i in issues]


OUTLINE = parcel(
    [
        ("A", E0, N0),
        ("B", E0 + 73.21, N0 + 4.07),
        ("C", E0 + 61.03, N0 + 55.49),
        ("D", E0 - 3.3, N0 + 40.1),
    ]
)


def parts_of(result) -> list[Parcel]:
    return [Parcel(label=p.geometry.label, vertices=p.geometry.vertices) for p in result.parts]


@pytest.mark.parametrize("method", ["parallel", "perpendicular", "pivot"])
def test_subdivision_covers_the_outline_exactly(method):
    req = SubdivideRequest(
        parcel=OUTLINE, method=method, side=1, pivot="B", mode="ratios", parts=[1, 2, 1.5]
    )
    sub = subdivide(req)
    assert not sub.issues
    # original vertices keep their exact input coordinates (no round-trip drift)
    originals = {v.name: (v.x, v.y) for v in OUTLINE.vertices}
    for part in sub.parts:
        for v in part.geometry.vertices:
            if v.name in originals:
                assert (v.x, v.y) == originals[v.name]
    r = check_coverage(CoverageRequest(outline=OUTLINE, parts=parts_of(sub)))
    assert r.ok, r.issues
    assert abs(r.difference) < 1e-6


def test_random_subdivisions_pass_with_exact_matching():
    rng = random.Random(5)
    for _ in range(30):
        req = SubdivideRequest(
            parcel=OUTLINE,
            method=rng.choice(["parallel", "perpendicular", "pivot"]),
            side=rng.randrange(4),
            pivot=rng.choice("ABCD"),
            from_end=rng.choice(["start", "end"]),
            mode="ratios",
            parts=[rng.uniform(0.2, 1) for _ in range(rng.randint(2, 4))],
        )
        r = check_coverage(CoverageRequest(outline=OUTLINE, parts=parts_of(subdivide(req))))
        assert r.ok, r.issues


SQ = parcel([("A", 0, 0), ("B", 20, 0), ("C", 20, 10), ("D", 0, 10)])


def test_sliver_gap_between_parts_is_detected():
    left = parcel([("A", 0, 0), ("M", 10, 0), ("N", 10, 10), ("D", 0, 10)])
    right = parcel([("M2", 10.002, 0), ("B", 20, 0), ("C", 20, 10), ("N2", 10.002, 10)])
    r = check_coverage(CoverageRequest(outline=SQ, parts=[left, right]))
    assert not r.ok
    assert "PARCEL_MERGE_NOT_ADJACENT" in codes(r.issues)
    assert "PARCEL_COVERAGE_AREA" in codes(r.issues)
    assert r.difference == pytest.approx(-0.02)


def test_overlap_is_detected():
    left = parcel([("A", 0, 0), ("M", 11, 0), ("N", 11, 10), ("D", 0, 10)])
    right = parcel([("M2", 10, 0), ("B", 20, 0), ("C", 20, 10), ("N2", 10, 10)])
    r = check_coverage(CoverageRequest(outline=SQ, parts=[left, right]))
    assert not r.ok and "PARCEL_COVERAGE_AREA" in codes(r.issues)


def test_part_outside_the_outline():
    left = parcel([("A", 0, 0), ("M", 10, 0), ("N", 10, 10), ("D", 0, 10)])
    right = parcel([("M", 10, 0), ("B", 20, 0), ("X", 21, 10), ("N", 10, 10)])
    r = check_coverage(CoverageRequest(outline=SQ, parts=[left, right]))
    assert codes(r.issues) == ["PARCEL_COVERAGE_OUTSIDE", "PARCEL_COVERAGE_AREA"]
    assert r.issues[0].params["points"] == ["X"]


def test_uncovered_corner():
    left = parcel([("A", 0, 0), ("M", 10, 0), ("N", 10, 10), ("D", 0, 10)])
    right = parcel([("M", 10, 0), ("B", 20, 0), ("Y", 20, 9), ("N", 10, 10)])
    r = check_coverage(CoverageRequest(outline=SQ, parts=[left, right]))
    assert codes(r.issues) == ["PARCEL_COVERAGE_GAP", "PARCEL_COVERAGE_AREA"]
    assert r.issues[0].params["points"] == ["C"]
    assert r.difference == pytest.approx(-5.0)


def test_single_part_equal_to_the_outline():
    r = check_coverage(CoverageRequest(outline=SQ, parts=[SQ]))
    assert r.ok and r.difference == 0.0


def test_invalid_outline():
    bow = parcel([("A", 0, 0), ("B", 10, 10), ("C", 10, 0), ("D", 0, 10)])
    r = check_coverage(CoverageRequest(outline=bow, parts=[SQ]))
    assert not r.ok and codes(r.issues) == ["PARCEL_SELF_INTERSECTION"]
