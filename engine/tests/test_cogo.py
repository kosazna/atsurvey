import math
import random

import pytest

from atsurvey.core.cogo import (
    area,
    intersection_angles,
    intersection_distances,
    intersection_lines,
    inverse,
    offset,
    polar,
    resection,
    transform,
)
from atsurvey.core.cogo_models import (
    XY,
    AreaRequest,
    CommonPoint,
    IntersectionAnglesRequest,
    IntersectionDistancesRequest,
    IntersectionLinesRequest,
    InverseRequest,
    OffsetRequest,
    PolarRequest,
    ResectionObservation,
    ResectionRequest,
    TransformRequest,
)
from atsurvey.core.geodesy import egsa87_point_scale, grid_azimuth
from atsurvey.core.models import ReductionSettings
from atsurvey.core.units import from_rad, to_rad

TWO_PI = 2 * math.pi


def gon(v):
    return from_rad(v, "gon")


# ----------------------------------------------------------------------------- inverse


def test_inverse_textbook():
    r = inverse(InverseRequest(a=XY(x=1000, y=1000, z=100), b=XY(x=1100, y=1100, z=105)))
    assert r.distance == pytest.approx(100 * math.sqrt(2))
    assert gon(r.azimuth) == pytest.approx(50.0)
    assert gon(r.azimuth_back) == pytest.approx(250.0)
    assert r.dz == pytest.approx(5.0)
    assert r.slope_distance == pytest.approx(math.hypot(100 * math.sqrt(2), 5))
    assert r.gradient_percent == pytest.approx(5 / (100 * math.sqrt(2)) * 100)
    assert r.distance_ground is None


@pytest.mark.parametrize(
    ("dx", "dy", "az"), [(0, 10, 0), (10, 0, 100), (0, -10, 200), (-10, 0, 300), (-3, 3, 350)]
)
def test_inverse_quadrants(dx, dy, az):
    r = inverse(InverseRequest(a=XY(x=0, y=0), b=XY(x=dx, y=dy)))
    assert gon(r.azimuth) == pytest.approx(az)


def test_inverse_ground_distance_inverts_the_reductions():
    a, b = XY(x=476120.0, y=4205333.0, z=200.0), XY(x=476500.0, y=4205600.0, z=210.0)
    rs = ReductionSettings()
    r = inverse(InverseRequest(a=a, b=b, reduction=rs))
    k = egsa87_point_scale((a.x + b.x) / 2)  # ≈ line factor for a short line
    ef = rs.earth_radius / (rs.earth_radius + 205.0)
    assert r.distance_ground == pytest.approx(r.distance / (k * ef), abs=1e-6)
    assert r.distance_ground is not None and r.distance_ground > r.distance  # k < 1


def test_inverse_coincident_points():
    with pytest.raises(ValueError, match="coincide"):
        inverse(InverseRequest(a=XY(x=1, y=1), b=XY(x=1, y=1)))


# ------------------------------------------------------------------------------- polar


def test_polar_by_azimuth_and_inverse_roundtrip():
    rng = random.Random(3)
    for _ in range(200):
        st = XY(x=rng.uniform(1e5, 9e5), y=rng.uniform(3.8e6, 4.6e6), z=rng.uniform(0, 1000))
        az, d = rng.uniform(0, TWO_PI), rng.uniform(0.5, 3000)
        p = polar(PolarRequest(station=st, azimuth=az, distance=d, dz=1.5)).point
        back = inverse(InverseRequest(a=st, b=p))
        assert back.distance == pytest.approx(d, abs=1e-8)
        assert abs(math.remainder(back.azimuth - az, TWO_PI)) < 1e-10
        assert st.z is not None and p.z == pytest.approx(st.z + 1.5)


def test_polar_from_backsight_angle():
    st, bs = XY(x=0, y=0), XY(x=0, y=100)  # backsight due north
    p = polar(PolarRequest(station=st, backsight=bs, angle=to_rad(100, "gon"), distance=50)).point
    assert p.x == pytest.approx(50) and p.y == pytest.approx(0, abs=1e-12)


def test_polar_needs_direction():
    with pytest.raises(ValueError, match="azimuth"):
        polar(PolarRequest(station=XY(x=0, y=0), distance=10))


# ------------------------------------------------------------------------ intersections


def angles_for(a: XY, b: XY, p: XY) -> tuple[float, float]:
    """Clockwise angle at A from B to P and at B from A to P, from true coordinates."""
    ang_a = (grid_azimuth(a.x, a.y, p.x, p.y) - grid_azimuth(a.x, a.y, b.x, b.y)) % TWO_PI
    ang_b = (grid_azimuth(b.x, b.y, p.x, p.y) - grid_azimuth(b.x, b.y, a.x, a.y)) % TWO_PI
    return ang_a, ang_b


def test_forward_intersection_textbook():
    # A(0,0), B(100,0); P(50,50): at A 350g clockwise from B, at B 50g clockwise from A
    a, b = XY(x=0, y=0), XY(x=100, y=0)
    r = intersection_angles(
        IntersectionAnglesRequest(a=a, b=b, angle_a=to_rad(350, "gon"), angle_b=to_rad(50, "gon"))
    )
    assert len(r.solutions) == 1
    assert r.solutions[0].x == pytest.approx(50) and r.solutions[0].y == pytest.approx(50)


def test_forward_intersection_random_geometry():
    rng = random.Random(5)
    for _ in range(100):
        a = XY(x=rng.uniform(4e5, 5e5), y=rng.uniform(4.1e6, 4.2e6))
        b = XY(x=a.x + rng.uniform(-500, 500), y=a.y + rng.uniform(-500, 500))
        p = XY(x=a.x + rng.uniform(-800, 800), y=a.y + rng.uniform(-800, 800))
        ang_a, ang_b = angles_for(a, b, p)
        r = intersection_angles(IntersectionAnglesRequest(a=a, b=b, angle_a=ang_a, angle_b=ang_b))
        if r.solutions:
            assert r.solutions[0].x == pytest.approx(p.x, abs=1e-6)
            assert r.solutions[0].y == pytest.approx(p.y, abs=1e-6)


def test_forward_intersection_parallel_and_wrong_side():
    a, b = XY(x=0, y=0), XY(x=100, y=0)
    par = intersection_angles(
        IntersectionAnglesRequest(a=a, b=b, angle_a=to_rad(300, "gon"), angle_b=to_rad(100, "gon"))
    )
    assert par.solutions == [] and "parallel" in (par.message or "")
    # rays diverging: from A to the north-west, from B to the north-east
    away = intersection_angles(
        IntersectionAnglesRequest(a=a, b=b, angle_a=to_rad(250, "gon"), angle_b=to_rad(150, "gon"))
    )
    assert away.solutions == [] and away.message


def test_circle_intersection_textbook_order():
    # 3-4-5 triangle: A(0,0) r=5, B(8,0) r=5 → (4, ±3); first solution right of A→B (south)
    r = intersection_distances(
        IntersectionDistancesRequest(a=XY(x=0, y=0), r_a=5, b=XY(x=8, y=0), r_b=5)
    )
    assert [(round(s.x, 9), round(s.y, 9)) for s in r.solutions] == [(4, -3), (4, 3)]


def test_circle_intersection_tangent_and_none():
    t = intersection_distances(
        IntersectionDistancesRequest(a=XY(x=0, y=0), r_a=3, b=XY(x=5, y=0), r_b=2)
    )
    assert len(t.solutions) == 1 and t.solutions[0].x == pytest.approx(3)
    far = intersection_distances(
        IntersectionDistancesRequest(a=XY(x=0, y=0), r_a=1, b=XY(x=5, y=0), r_b=1)
    )
    assert far.solutions == [] and far.message
    inside = intersection_distances(
        IntersectionDistancesRequest(a=XY(x=0, y=0), r_a=10, b=XY(x=1, y=0), r_b=1)
    )
    assert inside.solutions == []


def test_line_intersection():
    r = intersection_lines(
        IntersectionLinesRequest(
            p1=XY(x=0, y=0), p2=XY(x=10, y=10), p3=XY(x=0, y=10), p4=XY(x=10, y=0)
        )
    )
    assert r.solutions[0].x == pytest.approx(5) and r.solutions[0].y == pytest.approx(5)
    par = intersection_lines(
        IntersectionLinesRequest(p1=XY(x=0, y=0), p2=XY(x=1, y=1), p3=XY(x=0, y=1), p4=XY(x=1, y=2))
    )
    assert par.solutions == []
    with pytest.raises(ValueError):
        intersection_lines(
            IntersectionLinesRequest(
                p1=XY(x=0, y=0), p2=XY(x=0, y=0), p3=XY(x=0, y=1), p4=XY(x=1, y=2)
            )
        )


# ---------------------------------------------------------------------------- resection

STATION = (476611.203, 4205290.118)
KNOWN = [
    XY(x=476120.412, y=4205333.187, name="T1"),
    XY(x=476402.955, y=4205718.664, name="T2"),
    XY(x=477322.018, y=4205551.773, name="T3"),
    XY(x=477083.640, y=4204822.091, name="T4"),
    XY(x=476300.000, y=4204900.000, name="T5"),
]


def resection_obs(points, omega=1.234, distances=False, noise_cc=0.0, rng=None):
    out = []
    for p in points:
        d = grid_azimuth(*STATION, p.x, p.y) - omega
        if noise_cc:
            d += (rng or random.Random(1)).gauss(0, noise_cc) * 1e-4 * math.pi / 200
        out.append(
            ResectionObservation(
                point=p,
                direction=d % TWO_PI,
                distance=math.hypot(p.x - STATION[0], p.y - STATION[1]) if distances else None,
            )
        )
    return out


@pytest.mark.parametrize("n", [3, 4, 5])
def test_resection_recovers_station(n):
    r = resection(ResectionRequest(station_name="S", observations=resection_obs(KNOWN[:n])))
    assert r.station.x == pytest.approx(STATION[0], abs=1e-4)
    assert r.station.y == pytest.approx(STATION[1], abs=1e-4)
    assert r.orientation == pytest.approx(1.234, abs=1e-9)
    assert r.station.name == "S"
    assert not r.danger_circle
    assert all(abs(v.direction_residual) < 1e-9 for v in r.residuals)
    if n == 3:
        assert r.method == "three-point closed form" and r.sigma0 is None
    else:
        assert r.sigma0 is not None and r.sx is not None


def test_resection_with_two_directions_and_distances():
    r = resection(ResectionRequest(observations=resection_obs(KNOWN[:2], distances=True)))
    assert r.station.x == pytest.approx(STATION[0], abs=1e-4)
    assert r.station.y == pytest.approx(STATION[1], abs=1e-4)
    assert all(abs(v.distance_residual or 0) < 1e-6 for v in r.residuals)


def test_resection_redundant_noisy_statistics():
    rng = random.Random(11)
    obs = resection_obs(KNOWN, noise_cc=10, rng=rng)
    r = resection(ResectionRequest(observations=obs))
    assert math.hypot(r.station.x - STATION[0], r.station.y - STATION[1]) < 0.02
    assert 0.2 < (r.sigma0 or 0) < 3.0  # a priori σ = 10 cc matches the simulated noise
    assert r.sx and r.sx < 0.05


def test_resection_danger_circle():
    c, rad = (1000.0, 2000.0), 500.0
    pts = [
        XY(x=c[0] + rad * math.sin(a), y=c[1] + rad * math.cos(a), name=n)
        for a, n in [(0.3, "A"), (2.0, "B"), (4.0, "C")]
    ]

    def obs_from(s):
        return [
            ResectionObservation(point=p, direction=grid_azimuth(s[0], s[1], p.x, p.y) % TWO_PI)
            for p in pts
        ]

    near = (c[0] + 1.01 * rad * math.sin(5.2), c[1] + 1.01 * rad * math.cos(5.2))
    r = resection(ResectionRequest(observations=obs_from(near)))
    assert r.danger_circle
    assert r.station.x == pytest.approx(near[0], abs=1e-3)
    on = (c[0] + rad * math.sin(5.2), c[1] + rad * math.cos(5.2))
    with pytest.raises(ValueError, match="danger circle"):
        resection(ResectionRequest(observations=obs_from(on)))


def test_resection_not_enough_observations():
    with pytest.raises(ValueError, match="needs"):
        resection(ResectionRequest(observations=resection_obs(KNOWN[:2])))


# --------------------------------------------------------------------------------- area


def test_area_square():
    sq = [XY(x=0, y=0), XY(x=10, y=0), XY(x=10, y=10), XY(x=0, y=10)]
    r = area(AreaRequest(points=sq))
    assert r.area == pytest.approx(100)
    assert r.perimeter == pytest.approx(40)
    assert r.orientation == "counterclockwise"
    assert (r.centroid.x, r.centroid.y) == (pytest.approx(5), pytest.approx(5))
    r2 = area(AreaRequest(points=[*reversed(sq), sq[-1]]))  # closed, clockwise
    assert r2.orientation == "clockwise" and r2.area == pytest.approx(100)


def test_area_large_coordinates_and_reduction():
    # a 30 m x 20 m parcel in EGSA87 — the local origin keeps full precision
    x0, y0 = 476611.203, 4205290.118
    pts = [XY(x=x0, y=y0), XY(x=x0 + 30, y=y0), XY(x=x0 + 30, y=y0 + 20), XY(x=x0, y=y0 + 20)]
    r = area(AreaRequest(points=pts, reduction=ReductionSettings()))
    assert r.area == pytest.approx(600.0, abs=1e-9)
    k = egsa87_point_scale(x0 + 15)
    assert r.scale_factor_mean == pytest.approx(k, rel=1e-9)
    assert r.area_ellipsoid == pytest.approx(600.0 / k**2, rel=1e-9)


def test_area_degenerate():
    with pytest.raises(ValueError):
        area(AreaRequest(points=[XY(x=0, y=0), XY(x=1, y=1), XY(x=2, y=2)]))


# ------------------------------------------------------------------------ transformation


def helmert_apply(x, y, tx, ty, s, rot):
    a, b = s * math.cos(rot), s * math.sin(rot)
    return tx + a * x - b * y, ty + b * x + a * y


def test_helmert_recovers_known_parameters():
    rng = random.Random(2)
    tx, ty, s, rot = 476000.0, 4205000.0, 1.000321, 0.0123
    common = []
    for i in range(6):
        x, y = rng.uniform(-500, 500), rng.uniform(-500, 500)
        X, Y = helmert_apply(x, y, tx, ty, s, rot)
        common.append(CommonPoint(name=f"P{i}", src=XY(x=x, y=y), dst=XY(x=X, y=Y)))
    r = transform(
        TransformRequest(method="helmert", common=common, points=[XY(x=10, y=20, name="N")])
    )
    assert r.params["tx"] == pytest.approx(tx, abs=1e-6)
    assert r.params["ty"] == pytest.approx(ty, abs=1e-6)
    assert r.params["scale"] == pytest.approx(s, abs=1e-12)
    assert r.params["rotation"] == pytest.approx(rot, abs=1e-12)
    assert r.rms == pytest.approx(0, abs=1e-6)
    X, Y = helmert_apply(10, 20, tx, ty, s, rot)
    assert r.points[0].x == pytest.approx(X, abs=1e-6) and r.points[0].name == "N"


def test_helmert_two_points_exact_and_unused_residual():
    common = [
        CommonPoint(name="A", src=XY(x=0, y=0), dst=XY(x=100, y=100)),
        CommonPoint(name="B", src=XY(x=10, y=0), dst=XY(x=100, y=90)),  # rotated -100g
        CommonPoint(name="C", src=XY(x=0, y=10), dst=XY(x=110.05, y=100), use=False),
    ]
    r = transform(TransformRequest(method="helmert", common=common))
    assert r.rms is None  # no redundancy
    assert r.params["scale"] == pytest.approx(1.0)
    c = next(v for v in r.residuals if v.name == "C")
    assert not c.used and c.v == pytest.approx(0.05, abs=1e-9)


def test_affine_recovers_parameters_and_noise_rms():
    rng = random.Random(4)
    a = (1000.0, 1.001, 0.002, 2000.0, -0.003, 0.999)
    common = []
    for i in range(8):
        x, y = rng.uniform(-300, 300), rng.uniform(-300, 300)
        X = a[0] + a[1] * x + a[2] * y + rng.gauss(0, 0.01)
        Y = a[3] + a[4] * x + a[5] * y + rng.gauss(0, 0.01)
        common.append(CommonPoint(name=f"P{i}", src=XY(x=x, y=y), dst=XY(x=X, y=Y)))
    r = transform(TransformRequest(method="affine", common=common))
    assert r.params["a1"] == pytest.approx(1.001, abs=1e-4)
    assert r.params["b2"] == pytest.approx(0.999, abs=1e-4)
    assert 0.003 < (r.rms or 0) < 0.03


def test_transform_degenerate():
    with pytest.raises(ValueError, match="at least 3"):
        transform(
            TransformRequest(
                method="affine",
                common=[
                    CommonPoint(name="A", src=XY(x=0, y=0), dst=XY(x=0, y=0)),
                    CommonPoint(name="B", src=XY(x=1, y=0), dst=XY(x=1, y=0)),
                ],
            )
        )
    collinear = [CommonPoint(name=str(i), src=XY(x=i, y=i), dst=XY(x=i, y=i)) for i in range(4)]
    with pytest.raises(ValueError, match="collinear"):
        transform(TransformRequest(method="affine", common=collinear))


# ------------------------------------------------------------------------------- offset


def test_offset_signs_and_foot():
    r = offset(
        OffsetRequest(
            a=XY(x=0, y=0),
            b=XY(x=0, y=100),
            points=[XY(x=5, y=30, name="R"), XY(x=-5, y=30, name="L"), XY(x=0, y=-10)],
        )
    )
    assert r.line_length == pytest.approx(100) and gon(r.azimuth) == pytest.approx(0)
    right, left, behind = r.rows
    assert right.offset == pytest.approx(5) and right.chainage == pytest.approx(30)
    assert left.offset == pytest.approx(-5)
    assert behind.chainage == pytest.approx(-10)
    assert (right.foot.x, right.foot.y) == (pytest.approx(0), pytest.approx(30))


# ------------------------------------------------------------------------------ stakeout


def test_stakeout_inverts_polar():
    from atsurvey.core.cogo import polar, stakeout
    from atsurvey.core.cogo_models import XY, PolarRequest, StakeoutRequest

    st = XY(x=476_500.0, y=4_205_300.0, z=150.0, name="S1")
    bs = XY(x=476_350.0, y=4_205_420.0, name="T2")
    design = [
        XY(x=476_510.25, y=4_205_312.5, z=150.8, name="Δ1"),
        XY(x=476_430.0, y=4_205_250.0, z=149.1, name="Δ2"),
        XY(x=476_500.0, y=4_205_200.0, z=None, name="Δ3"),  # due south, no height
    ]
    res = stakeout(StakeoutRequest(station=st, backsight=bs, points=design))
    for row, p in zip(res.rows, design, strict=True):
        back = polar(PolarRequest(station=st, backsight=bs, angle=row.angle, distance=row.distance))
        assert back.point.x == pytest.approx(p.x, abs=1e-9)
        assert back.point.y == pytest.approx(p.y, abs=1e-9)
    assert res.rows[2].dz is None and res.rows[2].zenith is None
    assert res.rows[0].dz == pytest.approx(0.8)


def test_stakeout_ground_distance_and_zenith():
    from atsurvey.core.cogo import stakeout
    from atsurvey.core.cogo_models import XY, StakeoutRequest
    from atsurvey.core.geodesy import egsa87_line_scale, elevation_factor
    from atsurvey.core.models import ReductionSettings

    rs = ReductionSettings()
    st = XY(x=476_500.0, y=4_205_300.0, z=400.0)
    p = XY(x=476_800.0, y=4_205_700.0, z=420.0, name="Δ")
    res = stakeout(
        StakeoutRequest(
            station=st,
            backsight_azimuth=0.0,
            points=[p],
            reduction=rs,
            instrument_height=1.5,
            target_height=1.8,
        )
    )
    row = res.rows[0]
    k = egsa87_line_scale(st.x, p.x)
    assert row.distance_ground * k * elevation_factor(rs, 410.0) == pytest.approx(row.distance)
    # zenith/slope distance consistent with the ground distance and the heights
    vert = 20.0 - 1.5 + 1.8
    assert row.slope_distance == pytest.approx(math.hypot(row.distance_ground, vert))
    assert math.cos(row.zenith) * row.slope_distance == pytest.approx(vert)
    assert row.angle == pytest.approx(row.azimuth)  # zero direction = north


def test_stakeout_validation():
    from atsurvey.core.cogo import stakeout
    from atsurvey.core.cogo_models import XY, StakeoutRequest

    st = XY(x=0, y=0)
    with pytest.raises(ValueError):
        stakeout(StakeoutRequest(station=st, points=[XY(x=1, y=1)]))
    with pytest.raises(ValueError):
        stakeout(StakeoutRequest(station=st, backsight=XY(x=0, y=0), points=[XY(x=1, y=1)]))
    with pytest.raises(ValueError):
        stakeout(StakeoutRequest(station=st, backsight_azimuth=0, points=[XY(x=0, y=0)]))
