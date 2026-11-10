"""Subdivision (κατάτμηση): hand-computed cuts, random convex polygons checked with an exact
(Fraction) shoelace, non-convex refusal, frontage and naming."""

from __future__ import annotations

import itertools
import math
import random
from fractions import Fraction

import pytest

from atsurvey.core.parcels_models import ArcSpec, Parcel, ParcelVertex, SubdivideRequest, XYPoint
from atsurvey.core.parcels_subdivide import subdivide

E0, N0 = 476_000.0, 4_205_000.0
AREA_TOL = 1e-6  # m², required accuracy of every part


def parcel(pts, label: str = "") -> Parcel:
    return Parcel(label=label, vertices=[ParcelVertex(name=n, x=x, y=y) for n, x, y in pts])


def exact_area(vertices) -> float:
    """Independent truth: shoelace in exact rational arithmetic on the returned coordinates."""
    n = len(vertices)
    s = Fraction(0)
    for i in range(n):
        a, b = vertices[i], vertices[(i + 1) % n]
        s += Fraction(a.x) * Fraction(b.y) - Fraction(b.x) * Fraction(a.y)
    return abs(float(s / 2))


def codes(issues) -> list[str]:
    return [i.code for i in issues]


def shift(pts, dx=E0, dy=N0):
    return [(n, x + dx, y + dy) for n, x, y in pts]


RECT = [("A", 0, 0), ("B", 100, 0), ("C", 100, 50), ("D", 0, 50)]
#: trapezoid: base 100, top 60, height 40 → width w(h) = 100 − h, A(h) = 100h − h²/2
TRAP = [("A", 0, 0), ("B", 100, 0), ("C", 80, 40), ("D", 20, 40)]


# -------------------------------------------------------------------------- hand-computed


def test_rectangle_parallel_cut_at_egsa87():
    req = SubdivideRequest(parcel=parcel(shift(RECT)), method="parallel", side=0, parts=[1234.5])
    r = subdivide(req)
    assert r.issues == []
    first, rest = r.parts
    assert first.geometry.area == pytest.approx(1234.5, abs=AREA_TOL)
    assert exact_area(first.geometry.vertices) == pytest.approx(1234.5, abs=AREA_TOL)
    assert rest.requested_area is None
    assert rest.geometry.area == pytest.approx(5000 - 1234.5, abs=AREA_TOL)
    depth = 1234.5 / 100
    assert {(round(p.x - E0, 9), round(p.y - N0, 9)) for p in r.new_points} == {
        (100.0, depth),
        (0.0, depth),
    }
    assert [p.name for p in r.new_points] == ["Ν1", "Ν2"]
    assert r.cut_lines[0].length == pytest.approx(100.0)
    # part 1 starts at the first original vertex and keeps the input orientation
    assert [v.name for v in first.geometry.vertices][:2] == ["A", "B"]
    assert first.geometry.orientation == "counterclockwise"


def test_trapezoid_parallel_cut_solves_the_quadratic():
    r = subdivide(SubdivideRequest(parcel=parcel(TRAP), method="parallel", side=0, parts=[1000]))
    h = 100 - math.sqrt(8000)  # 100h − h²/2 = 1000
    ys = sorted(p.y for p in r.new_points)
    assert ys == pytest.approx([h, h], abs=1e-12)
    assert r.parts[0].geometry.area == pytest.approx(1000, abs=1e-9)
    assert abs(r.parts[0].area_error) < 1e-9


def test_trapezoid_parallel_to_the_top_side():
    # cut 600 m² off the top (side C→D): A(d) = 60d + d²/2 → d = −60 + √(3600 + 1200)
    r = subdivide(SubdivideRequest(parcel=parcel(TRAP), method="parallel", side=2, parts=[600]))
    d = -60 + math.sqrt(4800)
    assert [p.y for p in r.new_points] == pytest.approx([40 - d, 40 - d], abs=1e-12)
    assert r.parts[0].geometry.area == pytest.approx(600, abs=1e-9)
    assert {"C", "D"} <= {v.name for v in r.parts[0].geometry.vertices}


def test_rectangle_perpendicular_cut_from_start_and_end():
    for end, x in (("start", 30.0), ("end", 70.0)):
        req = SubdivideRequest(
            parcel=parcel(RECT), method="perpendicular", side=0, from_end=end, parts=[1500]
        )
        r = subdivide(req)
        assert [p.x for p in r.new_points] == pytest.approx([x, x], abs=1e-12)
        names = {v.name for v in r.parts[0].geometry.vertices}
        assert ("A" in names) is (end == "start")
        assert r.parts[0].geometry.area == pytest.approx(1500, abs=1e-9)


def test_triangle_pivot_at_vertex_splits_the_opposite_side_proportionally():
    tri = [("A", 0, 0), ("B", 60, 0), ("C", 0, 40)]  # area 1200
    r = subdivide(SubdivideRequest(parcel=parcel(tri), method="pivot", pivot="C", parts=[300]))
    # part 1 runs from C towards A (next vertex), i.e. triangle C, A, X with X on A–B at 1/4
    (x,) = r.new_points
    assert (x.x, x.y) == pytest.approx((15.0, 0.0), abs=1e-12)
    assert r.parts[0].geometry.area == pytest.approx(300, abs=1e-12)
    r2 = subdivide(
        SubdivideRequest(parcel=parcel(tri), method="pivot", pivot="C", towards="B", parts=[300])
    )
    (x2,) = r2.new_points
    assert (x2.x, x2.y) == pytest.approx((45.0, 0.0), abs=1e-12)
    assert "B" in {v.name for v in r2.parts[0].geometry.vertices}


def test_pivot_fan_crosses_several_sides():
    r = subdivide(
        SubdivideRequest(parcel=parcel(RECT), method="pivot", pivot="A", parts=[1000, 1000, 1000])
    )
    pts = [(p.name, p.x, p.y) for p in r.new_points]
    assert pts == [
        ("Ν1", pytest.approx(100.0), pytest.approx(20.0)),
        ("Ν2", pytest.approx(100.0), pytest.approx(40.0)),
        ("Ν3", pytest.approx(80.0), pytest.approx(50.0)),
    ]
    assert [p.geometry.area for p in r.parts] == pytest.approx([1000, 1000, 1000, 2000], abs=1e-9)
    assert all("A" in {v.name for v in p.geometry.vertices} for p in r.parts)


def test_pivot_given_by_coordinates_on_a_side_is_inserted():
    req = SubdivideRequest(
        parcel=parcel(shift(RECT)),
        method="pivot",
        pivot_point=XYPoint(x=E0 + 40.0, y=N0 + 0.0004),
        towards="B",
        parts=[1500],
    )
    r = subdivide(req)
    assert r.issues == []
    # the pivot is projected onto side A–B; triangle Ν1, B, C has 60·50/2 = 1500 m², so the
    # cut lands exactly on vertex C and no second new point is created
    (piv,) = r.new_points
    assert piv.name == "Ν1" and (piv.x - E0, piv.y - N0) == pytest.approx((40.0, 0.0))
    assert [v.name for v in r.parts[0].geometry.vertices] == ["B", "C", "Ν1"]
    assert r.parts[0].geometry.area == pytest.approx(1500, abs=AREA_TOL)


def test_pivot_not_on_the_boundary():
    req = SubdivideRequest(
        parcel=parcel(RECT), method="pivot", pivot_point=XYPoint(x=50, y=25), parts=[100]
    )
    assert codes(subdivide(req).issues) == ["PARCEL_PIVOT_NOT_ON_BOUNDARY"]


def test_pivot_unknown_and_towards_not_adjacent():
    base = {"parcel": parcel(RECT), "method": "pivot", "parts": [100]}
    assert codes(subdivide(SubdivideRequest(**base, pivot="Z")).issues) == ["PARCEL_PIVOT_UNKNOWN"]
    r = subdivide(SubdivideRequest(**base, pivot="A", towards="C"))
    assert codes(r.issues) == ["PARCEL_TOWARDS_NOT_ADJACENT"]


def test_equal_ratios_for_heirs_and_clockwise_input():
    cw = [("A", 0, 0), ("D", 0, 50), ("C", 100, 50), ("B", 100, 0)]
    r = subdivide(
        SubdivideRequest(
            parcel=parcel(cw), method="parallel", side=3, mode="ratios", parts=[1, 1, 1]
        )
    )
    assert r.issues == []
    assert [p.geometry.area for p in r.parts] == pytest.approx([5000 / 3] * 3, abs=1e-9)
    assert all(p.geometry.orientation == "clockwise" for p in r.parts)
    assert len(r.cut_lines) == 2 and len(r.new_points) == 4
    # the cut lines are parallel to side B→A (horizontal)
    assert all(abs(c.a.y - c.b.y) < 1e-12 for c in r.cut_lines)


def test_areas_summing_to_the_parcel_use_the_remainder_for_the_last_part():
    r = subdivide(
        SubdivideRequest(parcel=parcel(RECT), method="parallel", side=0, parts=[2000, 2999.995])
    )
    assert r.issues == []
    assert len(r.parts) == 2
    assert r.parts[1].area_error == pytest.approx(0.005, abs=1e-9)


def test_parts_exceeding_the_parcel():
    r = subdivide(SubdivideRequest(parcel=parcel(RECT), method="parallel", side=0, parts=[6000]))
    assert codes(r.issues) == ["PARCEL_PARTS_EXCEED_AREA"] and r.parts == []


def test_frontage_check():
    req = SubdivideRequest(
        parcel=parcel(RECT),
        method="perpendicular",
        side=0,
        mode="ratios",
        parts=[1, 1, 3],
        frontage_side=0,
        min_frontage=25.0,
    )
    r = subdivide(req)
    assert [p.frontage for p in r.parts] == pytest.approx([20.0, 20.0, 60.0])
    assert codes(r.issues) == ["PARCEL_FRONTAGE_SHORT", "PARCEL_FRONTAGE_SHORT"]


def test_custom_prefix_start_and_labels_and_name_clash():
    pts = [("A", 0, 0), ("B", 100, 0), ("K2", 100, 50), ("D", 0, 50)]
    req = SubdivideRequest(
        parcel=parcel(pts),
        method="parallel",
        side=0,
        parts=[1000, 4000],
        new_point_prefix="K",
        new_point_start=2,
        part_labels=["Κληρονόμος Α", "Κληρονόμος Β"],
    )
    r = subdivide(req)
    assert [p.name for p in r.new_points] == ["K3", "K4"]
    assert [p.geometry.label for p in r.parts] == ["Κληρονόμος Α", "Κληρονόμος Β"]


def test_side_index_out_of_range_raises():
    with pytest.raises(ValueError):
        subdivide(SubdivideRequest(parcel=parcel(RECT), method="parallel", side=9, parts=[10]))
    with pytest.raises(ValueError):
        subdivide(SubdivideRequest(parcel=parcel(RECT), method="parallel", parts=[10]))


# --------------------------------------------------------------------------- refusals


U_SHAPE = [
    ("A", 0, 0),
    ("B", 30, 0),
    ("C", 30, 30),
    ("D", 20, 30),
    ("E", 20, 10),
    ("F", 10, 10),
    ("G", 10, 30),
    ("H", 0, 30),
]  # area 700


def test_non_convex_parallel_cut_through_both_arms_is_refused():
    r = subdivide(SubdivideRequest(parcel=parcel(U_SHAPE), method="parallel", side=0, parts=[400]))
    assert codes(r.issues) == ["PARCEL_CUT_MULTIPLE_CROSSINGS"]
    assert r.issues[0].params == {"crossings": 4, "part": 1}
    assert r.parts == []


def test_non_convex_cut_below_the_notch_is_fine():
    r = subdivide(SubdivideRequest(parcel=parcel(U_SHAPE), method="parallel", side=0, parts=[200]))
    assert r.issues == []
    assert r.parts[0].geometry.area == pytest.approx(200, abs=1e-9)
    assert r.parts[1].geometry.area == pytest.approx(500, abs=1e-9)


def test_non_convex_pivot_cut_leaving_the_parcel_is_refused():
    # from A the fan towards B sweeps across the notch: the cut A–X would cross side E–F
    r = subdivide(SubdivideRequest(parcel=parcel(U_SHAPE), method="pivot", pivot="A", parts=[500]))
    assert codes(r.issues) == ["PARCEL_CUT_MULTIPLE_CROSSINGS"]


def test_arcs_are_refused():
    p = Parcel(
        vertices=[
            ParcelVertex(name="A", x=0, y=0, arc=ArcSpec(radius=80, side="right")),
            ParcelVertex(name="B", x=100, y=0),
            ParcelVertex(name="C", x=100, y=50),
        ]
    )
    r = subdivide(SubdivideRequest(parcel=p, method="parallel", side=1, parts=[10]))
    assert codes(r.issues) == ["PARCEL_ARCS_NOT_SUPPORTED"]


def test_invalid_parcel_returns_its_errors():
    bow = [("A", 0, 0), ("B", 10, 10), ("C", 10, 0), ("D", 0, 10)]
    r = subdivide(SubdivideRequest(parcel=parcel(bow), method="parallel", side=0, parts=[1]))
    assert codes(r.issues) == ["PARCEL_SELF_INTERSECTION"]


# ----------------------------------------------------------------- random convex polygons


def random_convex(rng: random.Random, n: int, radius: float) -> list[tuple[str, float, float]]:
    angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
    radii = [radius * rng.uniform(0.999, 1.0) for _ in range(n)]
    pts = [
        (f"P{i + 1}", E0 + r * math.cos(a), N0 + r * math.sin(a))
        for i, (a, r) in enumerate(zip(angles, radii, strict=True))
    ]
    if rng.random() < 0.5:
        pts.reverse()
    return pts


def on_boundary(p, ring, tol=1e-6) -> bool:
    for i in range(len(ring)):
        (_, ax, ay), (_, bx, by) = ring[i], ring[(i + 1) % len(ring)]
        dx, dy = bx - ax, by - ay
        t = ((p.x - ax) * dx + (p.y - ay) * dy) / (dx * dx + dy * dy)
        if -1e-12 <= t <= 1 + 1e-12 and math.hypot(p.x - ax - t * dx, p.y - ay - t * dy) < tol:
            return True
    return False


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("method", ["parallel", "perpendicular", "pivot"])
def test_random_convex_polygons(seed, method):
    rng = random.Random(seed * 7919 + len(method))
    pts = random_convex(rng, rng.randint(3, 12), rng.uniform(5, 800))
    area0 = exact_area([ParcelVertex(name=n, x=x, y=y) for n, x, y in pts])
    fractions = sorted(rng.uniform(0.05, 0.9) for _ in range(rng.randint(1, 3)))
    shares = [fractions[0], *(b - a for a, b in itertools.pairwise(fractions))]
    targets = [area0 * f for f in shares if f > 1e-3]
    side = rng.randrange(len(pts))
    req = SubdivideRequest(
        parcel=parcel(pts),
        method=method,
        side=side,
        from_end=rng.choice(["start", "end"]),
        pivot=pts[side][0] if method == "pivot" else None,
        parts=targets,
    )
    r = subdivide(req)
    assert not [i for i in r.issues if i.severity != "info"], r.issues
    assert len(r.parts) == len(targets) + 1
    for part, target in zip(r.parts, targets, strict=False):
        assert exact_area(part.geometry.vertices) == pytest.approx(target, abs=AREA_TOL)
    total = math.fsum(exact_area(p.geometry.vertices) for p in r.parts)
    assert total == pytest.approx(area0, abs=AREA_TOL * len(r.parts))
    assert all(on_boundary(p, pts) for p in r.new_points)
    if method != "pivot":
        (_, ax, ay), (_, bx, by) = pts[side], pts[(side + 1) % len(pts)]
        ux, uy = bx - ax, by - ay
        for c in r.cut_lines:
            vx, vy = c.b.x - c.a.x, c.b.y - c.a.y
            rel = (ux * vy - uy * vx) if method == "parallel" else (ux * vx + uy * vy)
            assert abs(rel) / math.hypot(ux, uy) / math.hypot(vx, vy) < 1e-9
