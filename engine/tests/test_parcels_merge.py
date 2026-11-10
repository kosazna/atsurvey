"""Merge (συνένωση) of adjacent parcels."""

from __future__ import annotations

import pytest

from atsurvey.core.parcels_merge import merge_parcels
from atsurvey.core.parcels_models import (
    ArcSpec,
    MergeRequest,
    Parcel,
    ParcelVertex,
    SubdivideRequest,
)
from atsurvey.core.parcels_subdivide import subdivide

E0, N0 = 476_000.0, 4_205_000.0


def parcel(pts, label: str = "") -> Parcel:
    return Parcel(label=label, vertices=[ParcelVertex(name=n, x=x, y=y) for n, x, y in pts])


def rect(names: str, x0: float, y0: float, x1: float, y1: float, label: str = "") -> Parcel:
    a, b, c, d = names
    return parcel([(a, x0, y0), (b, x1, y0), (c, x1, y1), (d, x0, y1)], label)


def codes(issues) -> list[str]:
    return [i.code for i in issues]


def test_two_rectangles_sharing_a_side():
    left = rect("ABCD", E0, N0, E0 + 10, N0 + 10, "1")
    right = rect("BEFC", E0 + 10, N0, E0 + 20, N0 + 10, "2")
    r = merge_parcels(MergeRequest(parcels=[left, right]))
    assert r.issues == []
    g = r.merged
    assert g is not None and g.valid
    assert g.area == pytest.approx(200.0, abs=1e-9)
    assert g.perimeter == pytest.approx(60.0, abs=1e-9)
    assert [v.name for v in g.vertices] == ["A", "B", "E", "F", "C", "D"]
    assert g.label == "1 + 2"
    assert r.area_sum == pytest.approx(200.0)


def test_mixed_orientation_and_snapping_within_tolerance():
    left = rect("ABCD", 0, 0, 10, 10)
    # clockwise neighbour whose shared corners are 0.4 mm off
    right = parcel([("B'", 10.0004, 0), ("C'", 10, 10.0003), ("F", 20, 10), ("E", 20, 0)])
    r = merge_parcels(MergeRequest(parcels=[left, right], label="Ενιαίο"))
    assert codes(r.issues) == ["PARCEL_MERGE_SNAPPED"]
    assert r.issues[0].params["count"] == 2
    assert r.max_snap == pytest.approx(0.0004)
    assert r.merged is not None and r.merged.label == "Ενιαίο"
    assert {v.name for v in r.merged.vertices} == {"A", "B", "E", "F", "C", "D"}
    assert r.merged.orientation == "counterclockwise"  # of the first parcel


def test_t_junction_neighbour_already_subdivided():
    big = rect("ABCD", 0, 0, 10, 20)
    # two small parcels on the right of side B–C; their common corner G lies on B–C
    low = parcel([("B", 10, 0), ("E", 20, 0), ("H", 20, 10), ("G", 10, 10)])
    high = parcel([("G", 10, 10), ("H", 20, 10), ("F", 20, 20), ("C", 10, 20)])
    r = merge_parcels(MergeRequest(parcels=[big, low, high]))
    assert r.issues == []
    assert r.inserted == ["G"]
    assert r.merged is not None and r.merged.area == pytest.approx(400.0)
    assert {v.name for v in r.merged.vertices} == {"A", "B", "E", "H", "F", "C", "D"}


def test_partially_overlapping_collinear_sides():
    a = rect("ABCD", 0, 0, 10, 10)
    b = rect("PQRS", 10, 5, 20, 15)  # shares B–C only from y = 5 to 10
    r = merge_parcels(MergeRequest(parcels=[a, b]))
    assert r.issues == []
    assert sorted(r.inserted) == ["C", "P"]
    assert r.merged is not None and r.merged.area == pytest.approx(200.0)


def test_not_adjacent():
    r = merge_parcels(
        MergeRequest(parcels=[rect("ABCD", 0, 0, 10, 10), rect("EFGH", 11, 0, 20, 10)])
    )
    assert codes(r.issues) == ["PARCEL_MERGE_NOT_ADJACENT"] and r.merged is None


def test_point_contact_only():
    r = merge_parcels(
        MergeRequest(parcels=[rect("ABCD", 0, 0, 10, 10), rect("CEFG", 10, 10, 20, 20)])
    )
    assert codes(r.issues) == ["PARCEL_MERGE_POINT_CONTACT"]
    assert r.issues[0].params == {"point": "C"}


def test_ring_of_parcels_leaves_a_hole():
    # 3 × 3 grid without the centre cell
    cells = [(i, j) for i in range(3) for j in range(3) if (i, j) != (1, 1)]
    parcels = []
    for i, j in cells:
        names = [f"{i + di}{j + dj}" for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1))]
        parcels.append(
            parcel([(n, float(n[0]) * 10, float(n[1]) * 10) for n in names], label=f"{i}{j}")
        )
    r = merge_parcels(MergeRequest(parcels=parcels))
    assert codes(r.issues) == ["PARCEL_MERGE_HOLES"]
    assert r.issues[0].params == {"count": 1}


def test_overlapping_parcels():
    r = merge_parcels(
        MergeRequest(parcels=[rect("ABCD", 0, 0, 10, 10), rect("ABCD", 0, 0, 10, 10)])
    )
    assert codes(r.issues) == ["PARCEL_MERGE_OVERLAP"]


def test_invalid_input_and_arcs():
    bow = parcel([("A", 0, 0), ("B", 10, 10), ("C", 10, 0), ("D", 0, 10)])
    r = merge_parcels(MergeRequest(parcels=[bow, rect("EFGH", 0, 0, 1, 1)]))
    assert codes(r.issues) == ["PARCEL_SELF_INTERSECTION"]
    arc = Parcel(
        vertices=[
            ParcelVertex(name="A", x=0, y=0, arc=ArcSpec(radius=10, side="right")),
            ParcelVertex(name="B", x=10, y=0),
            ParcelVertex(name="C", x=10, y=10),
        ]
    )
    r = merge_parcels(MergeRequest(parcels=[arc, rect("BEFC", 10, 0, 20, 10)]))
    assert codes(r.issues) == ["PARCEL_ARCS_NOT_SUPPORTED"]


def test_subdivide_then_merge_restores_the_parcel():
    pts = [
        ("A", E0, N0),
        ("B", E0 + 73.2, N0 + 4.1),
        ("C", E0 + 61.0, N0 + 55.5),
        ("D", E0 - 3, N0 + 40),
    ]
    original = parcel(pts)
    sub = subdivide(
        SubdivideRequest(parcel=original, method="parallel", side=0, mode="ratios", parts=[1, 2, 1])
    )
    parts = [Parcel(label=p.geometry.label, vertices=p.geometry.vertices) for p in sub.parts]
    r = merge_parcels(MergeRequest(parcels=parts))
    assert r.merged is not None, r.issues
    assert r.merged.area == pytest.approx(sub.original.area, abs=1e-6)
    # the new points on the outer boundary stay as (collinear) vertices
    assert {v.name for v in r.merged.vertices} >= {"A", "B", "C", "D"}
