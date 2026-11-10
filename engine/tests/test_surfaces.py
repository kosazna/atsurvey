"""Surfaces: TIN, heights, contours (checked against closed-form geometry)."""

import itertools
import math

import numpy as np
import pytest

from atsurvey.core.surfaces import contour_lines, heights, surface
from atsurvey.core.surfaces.cdt import constrain
from atsurvey.core.surfaces.contours import level_range
from atsurvey.core.surfaces.geom import incircle, orient
from atsurvey.core.surfaces.models import (
    Breakline,
    ContoursRequest,
    HeightsRequest,
    NamedXY,
    PlanXY,
    SurfacePoint,
    SurfaceRequest,
    SurfaceSpec,
)
from atsurvey.core.surfaces.tin import build_surface, delaunay, edges_of

E0, N0 = 476_000.0, 4_205_000.0  # ΕΓΣΑ87 magnitudes


def plane(x, y):
    return 10.0 + 0.1 * (x - E0) + 0.05 * (y - N0)


def square_points(n=400, seed=1, size=100.0, f=plane):
    rng = np.random.default_rng(seed)
    xs = np.concatenate([[0, size, size, 0], rng.uniform(0, size, n)]) + E0
    ys = np.concatenate([[0, 0, size, size], rng.uniform(0, size, n)]) + N0
    return [
        SurfacePoint(name=f"P{i}", x=x, y=y, z=f(x, y))
        for i, (x, y) in enumerate(zip(xs, ys, strict=True))
    ]


def spec(points, **kw):
    return SurfaceSpec(points=points, **kw)


def ring_area(pts):
    x = np.array([p[0] for p in pts]) - pts[0][0]
    y = np.array([p[1] for p in pts]) - pts[0][1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


# ----------------------------------------------------------------------------------- TIN


def test_tin_of_square_covers_it_exactly():
    r = surface(SurfaceRequest(surface=spec(square_points())))
    assert r.stats.area_2d == pytest.approx(10_000.0, abs=1e-6)
    # sloped area of a plane = plan area · √(1 + a² + b²)
    assert r.stats.area_3d == pytest.approx(10_000.0 * math.sqrt(1 + 0.1**2 + 0.05**2), rel=1e-12)
    assert r.stats.triangles == 2 * r.stats.vertices - 2 - 4  # Euler: 2n − 2 − hull vertices
    assert len(r.outline) == 1 and abs(ring_area(r.outline[0])) == pytest.approx(10_000.0)


def test_points_without_height_and_duplicates_are_reported():
    pts = square_points(50)
    pts.append(SurfacePoint(name="NOZ", x=E0 + 5, y=N0 + 5))
    pts.append(SurfacePoint(name="DUP", x=pts[10].x + 0.0004, y=pts[10].y, z=pts[10].z))
    pts.append(SurfacePoint(name="DUPZ", x=pts[11].x, y=pts[11].y + 0.0005, z=pts[11].z + 0.30))
    r = surface(SurfaceRequest(surface=spec(pts)))
    codes = [i.code for i in r.issues]
    assert codes.count("SURF_NO_Z") == 1
    assert "SURF_DUPLICATE" in codes
    dz = [i for i in r.issues if i.code == "SURF_DUPLICATE_Z"]
    assert len(dz) == 1 and dz[0].params["kept"] == "P11" and dz[0].params["dz"] == 0.3
    assert r.stats.duplicates_merged == 2 and r.stats.points_without_z == 1
    assert r.stats.vertices == 54


@pytest.mark.parametrize(
    "pts",
    [
        [SurfacePoint(x=E0 + i, y=N0 + 2 * i, z=1.0) for i in range(10)],  # collinear
        [
            SurfacePoint(x=E0, y=N0, z=1.0),
            SurfacePoint(x=E0 + 1, y=N0, z=1.0),
            SurfacePoint(x=E0, y=N0 + 1),
        ],
        [SurfacePoint(x=E0, y=N0, z=1.0)] * 5,  # all coincident
    ],
)
def test_degenerate_inputs_raise(pts):
    with pytest.raises(ValueError):
        build_surface(spec(pts))


def test_regular_grid_is_triangulated_without_gaps():
    # co-circular points everywhere: Qhull must still give a full triangulation
    g = [SurfacePoint(x=E0 + i, y=N0 + j, z=float(i + j)) for i in range(21) for j in range(21)]
    t = build_surface(spec(g))
    assert t.stats.triangles == 2 * 20 * 20
    assert t.stats.area_2d == pytest.approx(400.0, abs=1e-9)


# ------------------------------------------------------------------------------- heights


def test_heights_reproduce_the_plane_and_flag_outside_points():
    rng = np.random.default_rng(7)
    q = [
        NamedXY(name=f"Q{i}", x=E0 + x, y=N0 + y)
        for i, (x, y) in enumerate(rng.uniform(0, 100, (300, 2)))
    ]
    q += [NamedXY(name="OUT", x=E0 - 1, y=N0 + 50), NamedXY(name="EDGE", x=E0, y=N0 + 37.5)]
    r = heights(HeightsRequest(surface=spec(square_points()), points=q))
    for row in r.rows[:-2]:
        assert row.inside and row.z == pytest.approx(plane(row.x, row.y), abs=1e-9)
    assert r.rows[-2].z is None and not r.rows[-2].inside
    assert r.rows[-1].inside and r.rows[-1].z == pytest.approx(plane(E0, N0 + 37.5), abs=1e-9)
    assert [i.code for i in r.issues] == ["SURF_OUTSIDE"]
    assert r.issues[0].params["points"] == ["OUT"]


def test_height_on_a_shared_vertex_is_the_vertex_height():
    pts = square_points(30)
    r = heights(HeightsRequest(surface=spec(pts), points=[NamedXY(x=p.x, y=p.y) for p in pts]))
    assert [row.z for row in r.rows] == pytest.approx([p.z for p in pts], abs=1e-9)


# ------------------------------------------------------------------------------ contours


def test_contours_of_a_plane_are_straight_and_exact():
    res = contour_lines(
        ContoursRequest(surface=spec(square_points()), interval=1.0, base=0.0, index_every=5)
    )
    # z = 25 only at the corner: a level of a single point gives no line
    assert res.levels == [float(k) for k in range(11, 26)]
    assert [line.z for line in res.lines] == [float(k) for k in range(11, 25)]
    for line in res.lines:
        assert not line.closed
        assert line.index == (round(line.z) % 5 == 0)
        xy = np.array(line.points)
        assert np.abs(plane(xy[:, 0], xy[:, 1]) - line.z).max() < 1e-9
        # straight: every vertex on the chord between the end points
        a, b = xy[0], xy[-1]
        u = (b - a) / np.linalg.norm(b - a)
        off = (xy[:, 0] - a[0]) * u[1] - (xy[:, 1] - a[1]) * u[0]
        assert np.abs(off).max() < 1e-7
        # ends on the border of the square
        for p in (a, b):
            d = min(p[0] - E0, E0 + 100 - p[0], p[1] - N0, N0 + 100 - p[1])
            assert abs(d) < 1e-7
        # higher ground on the left of the direction of travel (gradient (0.1, 0.05))
        assert u[0] * 0.05 - u[1] * 0.1 > 0  # cross(u, grad) > 0 ⇔ grad points left


def hill(x, y):
    return 100.0 - ((x - E0 - 50) ** 2 + (y - N0 - 50) ** 2) / 50.0


def test_contours_on_a_hill_close_into_counter_clockwise_loops():
    g = [
        SurfacePoint(x=E0 + i * 2.0, y=N0 + j * 2.0, z=hill(E0 + i * 2.0, N0 + j * 2.0))
        for i in range(51)
        for j in range(51)
    ]
    res = contour_lines(ContoursRequest(surface=spec(g), interval=5.0, base=0.0, index_every=4))
    for lev in (60.0, 75.0, 90.0, 95.0):
        ls = [line for line in res.lines if line.z == lev]
        assert len(ls) == 1 and ls[0].closed
        r2 = (100.0 - lev) * 50.0  # circle radius² of the paraboloid level
        area = ring_area(ls[0].points)
        assert area > 0  # counter-clockwise
        assert area == pytest.approx(math.pi * r2, rel=0.02)
        assert ls[0].index == (lev % 20 == 0)
    # levels that reach the border of the grid are open
    assert [line.closed for line in res.lines if line.z == 40.0] == [False] * 4  # r = 54.8 m


def test_vertices_exactly_on_a_level_do_not_break_or_branch_lines():
    # integer heights on a pyramid-like grid: many vertices lie exactly on integer levels
    g = [
        SurfacePoint(x=E0 + i, y=N0 + j, z=float(10 - max(abs(i - 10), abs(j - 10))))
        for i in range(21)
        for j in range(21)
    ]
    res = contour_lines(ContoursRequest(surface=spec(g), interval=1.0, base=0.0))
    for lev in range(1, 10):
        ls = [line for line in res.lines if line.z == lev]
        assert len(ls) == 1, lev
        assert ls[0].closed
        pts = ls[0].points
        assert all(p != q for p, q in zip(pts, pts[1:] + pts[:1], strict=True))
    # the top vertex (z = 10) is a flat point: classified "above", so no line at 10
    assert not [line for line in res.lines if line.z == 10.0]


def test_level_range_is_exact_at_the_bounds():
    assert level_range(10.0, 20.0, 0.0, 5.0) == (3, 4)  # 15, 20 (10 excluded: z > L required)
    assert level_range(0.25, 0.875, 0.125, 0.125) == (2, 6)
    k0, k1 = level_range(-3.2, 7.9, 0.5, 2.0)
    assert 0.5 + k0 * 2.0 > -3.2 and 0.5 + (k0 - 1) * 2.0 <= -3.2
    assert 0.5 + k1 * 2.0 <= 7.9 < 0.5 + (k1 + 1) * 2.0


def test_too_many_contour_levels_is_refused():
    with pytest.raises(ValueError, match="Too many contour levels"):
        contour_lines(ContoursRequest(surface=spec(square_points(20)), interval=0.001))


def test_no_contour_in_range_is_an_info_issue():
    pts = square_points(20, f=lambda x, y: 10.2 + 0 * x)
    res = contour_lines(ContoursRequest(surface=spec(pts), interval=1.0))
    assert res.lines == [] and [i.code for i in res.issues] == ["SURF_CONTOURS_NONE"]


# ---------------------------------------------------------------------- trim and clip


def test_max_edge_trims_the_concave_side_only():
    # a "C": two arms and a back, the convex hull spans the 60 m mouth
    pts = []
    for i in range(41):
        for j in range(41):
            x, y = i * 2.5, j * 2.5
            if x > 20 and 20 < y < 80:
                continue  # the mouth of the C
            pts.append(SurfacePoint(x=E0 + x, y=N0 + y, z=1.0))
    full = build_surface(spec(pts))
    trimmed = build_surface(spec(pts, max_edge=3.0))  # grid 2.5 m, diagonals 3.54 m
    assert full.stats.area_2d == pytest.approx(10_000.0)
    assert trimmed.stats.area_2d == pytest.approx(10_000.0 - 80.0 * 60.0, rel=1e-9)
    # with 5 m the two inner-corner diagonals (< 5 m) stay: 2 half cells more
    loose = build_surface(spec(pts, max_edge=5.0))
    assert loose.stats.area_2d == pytest.approx(10_000.0 - 80.0 * 60.0 + 2.5 * 2.5, rel=1e-9)
    assert trimmed.stats.trimmed_triangles > 0
    assert len(trimmed.outline) == 1  # no interior holes


def test_boundary_clips_exactly():
    pts = square_points()
    ring = [(10, 10), (90, 10), (50, 50), (90, 90), (10, 90)]  # concave
    boundary = [PlanXY(x=E0 + x, y=N0 + y) for x, y in ring]
    t = build_surface(spec(pts, boundary=boundary))
    assert t.stats.area_2d == pytest.approx(80 * 80 - 0.5 * 80 * 40, abs=1e-6)
    res = contour_lines(ContoursRequest(surface=spec(pts, boundary=boundary), interval=1.0))
    for line in res.lines:
        xy = np.array(line.points)
        assert np.abs(plane(xy[:, 0], xy[:, 1]) - line.z).max() < 1e-9
    r = heights(
        HeightsRequest(
            surface=spec(pts, boundary=boundary),
            points=[NamedXY(x=E0 + 85, y=N0 + 50), NamedXY(x=E0 + 30, y=N0 + 50)],
        )
    )
    assert r.rows[0].z is None and r.rows[1].z == pytest.approx(plane(E0 + 30, N0 + 50))


def test_boundary_larger_than_the_surface_is_reported():
    boundary = [
        PlanXY(x=E0 + x, y=N0 + y) for x, y in [(-10, -10), (110, -10), (110, 110), (-10, 110)]
    ]
    t = build_surface(spec(square_points(), boundary=boundary))
    assert t.stats.area_2d == pytest.approx(10_000.0, abs=1e-6)
    issue = next(i for i in t.issues if i.code == "SURF_BOUNDARY_PARTIAL")
    assert issue.params["uncovered_area"] == pytest.approx(120 * 120 - 10_000, abs=0.01)


def test_self_intersecting_boundary_is_refused():
    bow = [PlanXY(x=E0 + x, y=N0 + y) for x, y in [(10, 10), (90, 90), (90, 10), (10, 60)]]
    with pytest.raises(ValueError, match="intersects itself"):
        build_surface(spec(square_points(), boundary=bow))


# ---------------------------------------------------------------------------- breaklines


def test_breakline_forces_the_ridge():
    pts = [
        SurfacePoint(name="A", x=E0, y=N0, z=10.0),
        SurfacePoint(name="B", x=E0 + 10, y=N0, z=10.0),
        SurfacePoint(name="C", x=E0 + 5, y=N0 + 1, z=0.0),
        SurfacePoint(name="D", x=E0 + 5, y=N0 - 1, z=0.0),
    ]
    q = [NamedXY(x=E0 + 5, y=N0)]
    plain = heights(HeightsRequest(surface=spec(pts), points=q))
    ridge = heights(
        HeightsRequest(surface=spec(pts, breaklines=[Breakline(points=["A", "B"])]), points=q)
    )
    assert plain.rows[0].z == pytest.approx(0.0)  # Delaunay takes the short diagonal C–D
    assert ridge.rows[0].z == pytest.approx(10.0)
    assert ridge.surface.stats.breakline_segments == 1


def _edge_set(tri):
    uniq, _ = edges_of(tri)
    return {tuple(e) for e in uniq.tolist()}


def _is_constrained_delaunay(xy, tri, fixed):
    """Every edge that is not constrained is locally Delaunay (exact predicate)."""
    where = {}
    for t, (a, b, c) in enumerate(tri.tolist()):
        for u, v in ((a, b), (b, c), (c, a)):
            where[(u, v)] = (t, (c if (u, v) == (a, b) else a if (u, v) == (b, c) else b))
    for (u, v), (_, w) in where.items():
        if (v, u) not in where or (min(u, v), max(u, v)) in fixed:
            continue
        opp = where[(v, u)][1]
        a, b, c = (u, v, w)
        if incircle(*xy[a], *xy[b], *xy[c], *xy[opp]) > 0:
            return False
    return True


def test_random_breaklines_become_edges_and_the_rest_stays_delaunay():
    rng = np.random.default_rng(3)
    xy = rng.uniform(0, 100, (600, 2))
    # a zig-zag polyline through some of the points, sorted by x (non-crossing)
    chain_idx = np.argsort(xy[:, 0])[::12].tolist()
    tri, _ = delaunay(xy)
    segs = list(itertools.pairwise(chain_idx))
    out, done, rejected = constrain(xy, tri, segs)
    assert not rejected and len(done) == len(segs)
    edges = _edge_set(out)
    for a, b in segs:
        assert (min(a, b), max(a, b)) in edges
    # still a triangulation of the same hull: same area, all counter-clockwise
    p = xy[out]
    area = 0.5 * (
        (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
        - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0])
    )
    p0 = xy[tri]
    area0 = 0.5 * (
        (p0[:, 1, 0] - p0[:, 0, 0]) * (p0[:, 2, 1] - p0[:, 0, 1])
        - (p0[:, 1, 1] - p0[:, 0, 1]) * (p0[:, 2, 0] - p0[:, 0, 0])
    )
    assert (area > 0).all() and area.sum() == pytest.approx(area0.sum(), rel=1e-12)
    assert len(out) == len(tri)
    fixed = {(min(a, b), max(a, b)) for a, b in segs}
    assert _is_constrained_delaunay(xy, out, fixed)


def test_breakline_through_a_vertex_is_split_there():
    xy = np.array([[0, 0], [5, 0], [10, 0], [5, 3], [5, -3], [2, 1], [8, -1]], dtype=float)
    tri, _ = delaunay(xy)
    out, _done, rejected = constrain(xy, tri, [(0, 2)])
    edges = _edge_set(out)
    assert (0, 1) in edges and (1, 2) in edges and not rejected


def test_crossing_breaklines_are_rejected_and_reported():
    pts = [
        SurfacePoint(name=n, x=E0 + x, y=N0 + y, z=1.0)
        for n, x, y in [
            ("A", 0, 0),
            ("B", 10, 10),
            ("C", 0, 10),
            ("D", 10, 0),
            ("E", 5, 2),
            ("F", 3, 5),
        ]
    ]
    t = build_surface(
        spec(pts, breaklines=[Breakline(points=["A", "B"]), Breakline(points=["C", "D"])])
    )
    assert t.stats.breakline_segments == 1
    assert any(i.code == "SURF_BREAKLINE_CROSSING" for i in t.issues)


def test_unknown_breakline_points_are_reported():
    t = build_surface(spec(square_points(20), breaklines=[Breakline(points=["P1", "NOPE", "P2"])]))
    issue = next(i for i in t.issues if i.code == "SURF_BREAKLINE_POINT")
    assert issue.params["points"] == ["NOPE"]


def test_orient_is_exact_for_nearly_collinear_points():
    # classic float failure: points almost on a line at large magnitudes
    assert orient(0.5, 0.5, 12.0, 12.0, 24.0, 24.0) == 0
    assert orient(E0, N0, E0 + 1, N0 + 1, E0 + 2, N0 + 2 + 2**-20) == 1
