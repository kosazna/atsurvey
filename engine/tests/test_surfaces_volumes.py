"""Surfaces: cut/fill volumes and profiles against analytic shapes."""

import itertools
import math

import numpy as np
import pytest

from atsurvey.core.surfaces import profile, volume_level, volume_surfaces
from atsurvey.core.surfaces.models import (
    LevelVolumeRequest,
    PlanXY,
    ProfileRequest,
    SurfacePoint,
    SurfaceSpec,
    SurfaceVolumeRequest,
)
from atsurvey.core.surfaces.tin import build_surface, edges_of

E0, N0 = 476_000.0, 4_205_000.0


def square(f, n=300, seed=1, size=100.0):
    rng = np.random.default_rng(seed)
    xs = np.concatenate([[0, size, size, 0], rng.uniform(0, size, n)])
    ys = np.concatenate([[0, 0, size, size], rng.uniform(0, size, n)])
    return SurfaceSpec(
        points=[SurfacePoint(x=E0 + x, y=N0 + y, z=f(x, y)) for x, y in zip(xs, ys, strict=True)]
    )


def ramp(x, y):
    return 10.0 + 0.1 * x  # local x in [0, 100]


def tilted(x, y):
    return 10.0 + 0.1 * x + 0.05 * y


# ------------------------------------------------------------------------- vs level


def test_ramp_against_a_level_is_exact():
    # ∫ max(0.1x − 5, 0) over [0,100]² = 100·∫₅₀¹⁰⁰(0.1x − 5)dx = 12 500 (fill the same)
    v = volume_level(LevelVolumeRequest(surface=square(ramp), level=15.0))
    assert v.cut == pytest.approx(12_500.0, rel=1e-12)
    assert v.fill == pytest.approx(12_500.0, rel=1e-12)
    assert v.net == pytest.approx(0.0, abs=1e-8)
    assert v.cut_area == pytest.approx(5_000.0, rel=1e-12)
    assert v.fill_area == pytest.approx(5_000.0, rel=1e-12)
    assert v.area == pytest.approx(10_000.0, rel=1e-12)
    assert v.method.startswith("TIN prism")


def test_level_below_everything_is_the_mean_height_prism():
    v = volume_level(LevelVolumeRequest(surface=square(tilted), level=0.0))
    # mean of the plane over the square = 10 + 5 + 2.5
    assert v.cut == pytest.approx(10_000.0 * 17.5, rel=1e-12)
    assert v.fill == 0.0 and v.fill_area == 0.0


def _brute(f, level, n=2000):
    h = 100.0 / n
    c = (np.arange(n) + 0.5) * h
    x, y = np.meshgrid(c, c)
    d = f(x, y) - level
    return float(np.clip(d, 0, None).sum() * h * h), float(np.clip(-d, 0, None).sum() * h * h)


def test_tilted_plane_matches_an_independent_fine_grid():
    v = volume_level(LevelVolumeRequest(surface=square(tilted), level=17.0))
    cut, fill = _brute(tilted, 17.0)
    assert v.cut == pytest.approx(cut, rel=1e-5)
    assert v.fill == pytest.approx(fill, rel=1e-5)
    assert v.net == pytest.approx(10_000.0 * (17.5 - 17.0), rel=1e-12)  # exact identity


def pyramid_spec(a=10.0, h=6.0):
    pts = [(-a, -a, 0.0), (a, -a, 0.0), (a, a, 0.0), (-a, a, 0.0), (0.0, 0.0, h)]
    return SurfaceSpec(points=[SurfacePoint(x=E0 + x, y=N0 + y, z=z) for x, y, z in pts])


@pytest.mark.parametrize("level", [0.0, 1.5, 3.0, 5.9])
def test_pyramid(level):
    a, h = 10.0, 6.0
    base = (2 * a) ** 2
    total = base * h / 3
    top = base * (1 - level / h) ** 2 * (h - level) / 3  # similar pyramid above the level
    v = volume_level(LevelVolumeRequest(surface=pyramid_spec(a, h), level=level))
    assert v.cut == pytest.approx(top, rel=1e-12)
    assert v.fill == pytest.approx(base * level - total + top, rel=1e-12, abs=1e-9)
    assert v.cut_area == pytest.approx(base * (1 - level / h) ** 2, rel=1e-12)


def cone_spec(r=20.0, h=8.0, n=360, rings=1):
    pts = [(0.0, 0.0, h)]
    for k in range(1, rings + 1):
        rr = r * k / rings
        for j in range(n):
            t = 2 * math.pi * j / n
            pts.append((rr * math.cos(t), rr * math.sin(t), h * (1 - rr / r)))
    return SurfaceSpec(points=[SurfacePoint(x=E0 + x, y=N0 + y, z=z) for x, y, z in pts])


def test_cone_as_polygonal_pyramid_is_exact():
    r, h, n = 20.0, 8.0, 72
    v = volume_level(LevelVolumeRequest(surface=cone_spec(r, h, n), level=0.0))
    base = 0.5 * n * r * r * math.sin(2 * math.pi / n)
    assert v.cut == pytest.approx(base * h / 3, rel=1e-10)


def test_cone_converges_to_pi_r2_h_over_3():
    r, h = 20.0, 8.0
    v = volume_level(LevelVolumeRequest(surface=cone_spec(r, h, 360, rings=5), level=0.0))
    assert v.cut == pytest.approx(math.pi * r * r * h / 3, rel=1e-3)


def test_level_volume_inside_a_concave_boundary():
    ring = [(10, 10), (90, 10), (50, 50), (90, 90), (10, 90)]
    s = square(tilted).model_copy(
        update={"boundary": [PlanXY(x=E0 + x, y=N0 + y) for x, y in ring]}
    )
    v = volume_level(LevelVolumeRequest(surface=s, level=0.0))
    # ∫ plane = area · plane(centroid) for a linear function
    area = 80 * 80 - 0.5 * 80 * 40
    rect_c, tri_c = (50.0, 50.0), ((90 + 50 + 90) / 3, 50.0)
    cx = (80 * 80 * rect_c[0] - 1600 * tri_c[0]) / area
    cy = 50.0
    assert v.area == pytest.approx(area, rel=1e-12)
    assert v.cut == pytest.approx(area * tilted(cx, cy), rel=1e-11)


# ---------------------------------------------------------------------- vs surface


def test_parallel_planes():
    existing = square(tilted, seed=1)
    design = square(lambda x, y: tilted(x, y) - 2.0, seed=2, n=150)  # different points
    v = volume_surfaces(SurfaceVolumeRequest(existing=existing, design=design))
    assert v.cut == pytest.approx(20_000.0, rel=1e-11)
    assert v.fill == pytest.approx(0.0, abs=1e-8)
    assert v.cut_area == pytest.approx(10_000.0, rel=1e-11)
    assert v.area == pytest.approx(10_000.0, rel=1e-11)
    assert v.issues == []


def test_crossing_planes_split_cut_and_fill():
    design = square(lambda x, y: tilted(x, y) - 0.02 * (x - 50.0), seed=5)
    v = volume_surfaces(SurfaceVolumeRequest(existing=square(tilted), design=design))
    # existing − design = 0.02(x − 50): cut 100·∫₅₀¹⁰⁰ 0.02(x−50)dx = 2 500, fill the same
    assert v.cut == pytest.approx(2_500.0, rel=1e-10)
    assert v.fill == pytest.approx(2_500.0, rel=1e-10)
    assert v.cut_area == pytest.approx(5_000.0, rel=1e-10)


def test_partial_overlap_is_reported_and_only_common_area_counts():
    shifted = SurfaceSpec(
        points=[
            p.model_copy(update={"x": p.x + 50.0, "z": p.z - 1.0}) for p in square(tilted).points
        ]
    )
    # the design is shifted by 50 m: its plane is tilted(x − 50) − 1 = tilted − 6
    v = volume_surfaces(SurfaceVolumeRequest(existing=square(tilted), design=shifted))
    assert v.area == pytest.approx(5_000.0, rel=1e-11)
    assert v.cut == pytest.approx(5_000.0 * 6.0, rel=1e-11)
    assert [i.code for i in v.issues] == ["SURF_VOLUME_PARTIAL"]


def test_boundary_applies_to_both_surfaces():
    ring = [PlanXY(x=E0 + x, y=N0 + y) for x, y in [(0, 0), (40, 0), (40, 25), (0, 25)]]
    design = square(lambda x, y: tilted(x, y) - 1.0, seed=9)
    v = volume_surfaces(SurfaceVolumeRequest(existing=square(tilted), design=design, boundary=ring))
    assert v.area == pytest.approx(1_000.0, rel=1e-11)
    assert v.cut == pytest.approx(1_000.0, rel=1e-11)


def test_disjoint_surfaces_raise():
    far = SurfaceSpec(
        points=[p.model_copy(update={"x": p.x + 500.0}) for p in square(tilted).points]
    )
    with pytest.raises(ValueError, match="do not overlap"):
        volume_surfaces(SurfaceVolumeRequest(existing=square(tilted), design=far))


# --------------------------------------------------------------------------- profile


def _edges_crossed(spec, p0, p1):
    """Brute force: number of TIN edges properly crossed by the open segment p0→p1."""
    t = build_surface(spec)
    uniq, _ = edges_of(t.tri)
    a = t.xy[uniq[:, 0]] + t.origin
    b = t.xy[uniq[:, 1]] + t.origin
    p0, p1 = np.array(p0), np.array(p1)

    def cross(o, u, v):
        return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (
            v[..., 0] - o[..., 0]
        )

    d1 = cross(p0, p1, a)
    d2 = cross(p0, p1, b)
    d3 = cross(a, b, p0[None])
    d4 = cross(a, b, p1[None])
    return int(((d1 * d2 < 0) & (d3 * d4 < 0)).sum())


def test_long_profile_on_a_plane():
    s = square(tilted)
    a, b, c = (E0 + 5, N0 + 7), (E0 + 60, N0 + 52), (E0 + 95, N0 + 20)
    r = profile(ProfileRequest(surface=s, alignment=[PlanXY(x=p[0], y=p[1]) for p in (a, b, c)]))
    length = math.dist(a, b) + math.dist(b, c)
    assert r.length == pytest.approx(length)
    ch = [st.chainage for st in r.stations]
    assert ch[0] == 0.0 and ch[-1] == pytest.approx(length)
    assert all(q > p for p, q in itertools.pairwise(ch))
    assert {st.run for st in r.stations} == {0}
    for st in r.stations:
        assert st.z == pytest.approx(tilted(st.x - E0, st.y - N0), abs=1e-9)
    # a station at every edge crossing + the three vertices
    crossings = _edges_crossed(s, a, b) + _edges_crossed(s, b, c)
    assert len(r.stations) == crossings + 3
    assert r.issues == []


def test_profile_leaving_the_surface_has_gaps_and_runs():
    s = square(tilted)
    line = [PlanXY(x=E0 - 20, y=N0 + 50), PlanXY(x=E0 + 120, y=N0 + 50)]
    r = profile(ProfileRequest(surface=s, alignment=line))
    assert r.stations[0].chainage == pytest.approx(20.0)
    assert r.stations[-1].chainage == pytest.approx(120.0)
    assert [i.code for i in r.issues] == ["SURF_PROFILE_GAP"]


def test_cross_sections():
    s = square(tilted)
    line = [PlanXY(x=E0 + 20, y=N0 + 50), PlanXY(x=E0 + 80, y=N0 + 50)]
    r = profile(ProfileRequest(surface=s, alignment=line, section_interval=25.0, half_width=10.0))
    assert [cs.chainage for cs in r.sections] == [0.0, 25.0, 50.0, 60.0]
    for cs in r.sections:
        assert cs.azimuth == pytest.approx(math.pi / 2)  # alignment heads east
        assert cs.z == pytest.approx(tilted(cs.x - E0, cs.y - N0))
        offs = [st.chainage for st in cs.stations]
        assert offs[0] == pytest.approx(-10.0) and offs[-1] == pytest.approx(10.0)
        first = cs.stations[0]
        assert first.y - N0 == pytest.approx(60.0)  # negative offsets are on the left (north)
        for st in cs.stations:
            assert st.z == pytest.approx(tilted(st.x - E0, st.y - N0), abs=1e-9)


def test_too_many_sections_are_refused():
    line = [PlanXY(x=E0, y=N0), PlanXY(x=E0 + 100, y=N0)]
    with pytest.raises(ValueError, match="Too many cross-sections"):
        profile(ProfileRequest(surface=square(tilted), alignment=line, section_interval=0.01))
