"""Road alignment (core/alignment.py): clothoid accuracy, closed-form circular curves, element
continuity, chainage/offset round trips, issues, stakeout lists and the vertical profile."""

import itertools
import math

import numpy as np
import pytest
from scipy.special import fresnel

from atsurvey.core.alignment import Axis, Profile, alignment, clothoid_xy, locate, stakeout
from atsurvey.core.alignment_models import (
    AlignmentRequest,
    AlignmentStakeoutRequest,
    LocateRequest,
    VerticalProfile,
)
from atsurvey.core.units import wrap_pi

E0, N0 = 476_000.0, 4_205_000.0  # ΕΓΣΑ87 magnitudes: precision must survive large coordinates


def req(vertices, **kw):
    return AlignmentRequest.model_validate({"vertices": vertices, **kw})


def gl_clothoid(length, a, panels=40, order=40):
    """Independent truth: composite Gauss–Legendre quadrature of cos/sin(s² / 2A²)."""
    t, w = np.polynomial.legendre.leggauss(order)
    edges = np.linspace(0.0, length, panels + 1)
    x = y = 0.0
    for lo, hi in itertools.pairwise(edges):
        s = (hi - lo) / 2 * t + (hi + lo) / 2
        th = s * s / (2 * a * a)
        x += (hi - lo) / 2 * float(np.dot(w, np.cos(th)))
        y += (hi - lo) / 2 * float(np.dot(w, np.sin(th)))
    return x, y


# ------------------------------------------------------------------------------- clothoid


@pytest.mark.parametrize(
    ("a", "length"),
    [(30, 10), (60, 40), (100, 50), (150, 75), (250, 120), (400, 300), (800, 900), (90, 150)],
)
def test_clothoid_series_matches_independent_integrations(a, length):
    x, y = clothoid_xy(length, a)
    gx, gy = gl_clothoid(length, a)
    k = a * math.sqrt(math.pi)
    fs, fc = fresnel(length / k)
    assert abs(x - gx) < 1e-9 and abs(y - gy) < 1e-9  # ≪ 0.1 mm
    assert abs(x - k * fc) < 1e-9 and abs(y - k * fs) < 1e-9


def test_clothoid_large_turn_still_accurate():
    a = 50.0
    length = a * math.sqrt(2 * math.pi)  # τ = π
    x, y = clothoid_xy(length, a)
    gx, gy = gl_clothoid(length, a)
    assert abs(x - gx) < 1e-9 and abs(y - gy) < 1e-9


# ------------------------------------------------------------------------ circular curve


@pytest.mark.parametrize(
    ("delta_deg", "turn", "r"),
    [(20.0, 1, 250.0), (65.0, -1, 250.0), (120.0, 1, 250.0), (170.0, -1, 60.0)],
)
def test_circular_curve_against_closed_form(delta_deg, turn, r):
    d = math.radians(delta_deg)
    az2 = turn * d  # incoming heading north
    v = (E0, N0 + 1000.0)
    end = (v[0] + 2000 * math.sin(az2), v[1] + 2000 * math.cos(az2))
    res = alignment(
        req([{"x": E0, "y": N0}, {"x": v[0], "y": v[1], "radius": r}, {"x": end[0], "y": end[1]}])
    )
    assert not res.issues
    t = r * math.tan(d / 2)
    row = res.vertices[1]
    assert row.t_in == pytest.approx(t, abs=1e-9) and row.t_out == pytest.approx(t, abs=1e-9)
    assert row.arc_length == pytest.approx(r * d, abs=1e-9)
    assert row.external == pytest.approx(r * (1 / math.cos(d / 2) - 1), abs=1e-8)
    assert row.deflection == pytest.approx(turn * d, abs=1e-12)
    codes = [m.code for m in res.main_points]
    assert codes == ["BP", "PC", "MC", "PT", "EP"]
    pc, mc, pt = res.main_points[1:4]
    assert pc.chainage == pytest.approx(1000 - t, abs=1e-9)
    assert pt.chainage - pc.chainage == pytest.approx(r * d, abs=1e-9)
    assert math.hypot(pt.x - pc.x, pt.y - pc.y) == pytest.approx(2 * r * math.sin(d / 2), abs=1e-8)
    assert math.hypot(mc.x - v[0], mc.y - v[1]) == pytest.approx(row.external, abs=1e-8)
    assert res.length == pytest.approx(1000 + 2000 - 2 * t + r * d, abs=1e-8)


# --------------------------------------------------------------------- spiral-arc-spiral


def _check_continuity(axis: Axis):
    els = axis.elements
    for a, b in itertools.pairwise(els):
        xa, ya, aa = a.at(a.length)
        xb, yb, ab = b.at(0.0)
        assert math.hypot(xa - xb, ya - yb) < 1e-9, (a.kind, b.kind)
        assert abs(wrap_pi(aa - ab)) < 1e-12
        assert b.s0 == pytest.approx(a.s0 + a.length, abs=1e-9)


@pytest.mark.parametrize("turn", [1, -1])
def test_symmetric_clothoid_curve_geometry(turn):
    r, a, d = 400.0, 200.0, math.radians(48.0)
    length = a * a / r  # 100 m
    tau = length / (2 * r)
    v = (E0, N0 + 800.0)
    az2 = turn * d
    end = (v[0] + 900 * math.sin(az2), v[1] + 900 * math.cos(az2))
    rq = req(
        [
            {"x": E0, "y": N0},
            {"name": "K1", "x": v[0], "y": v[1], "radius": r, "a_in": a},
            {"x": end[0], "y": end[1]},
        ]
    )
    res = alignment(rq)
    assert not res.issues
    row = res.vertices[1]
    x_end, y_end = clothoid_xy(length, a)
    shift = y_end - r * (1 - math.cos(tau))
    xm = x_end - r * math.sin(tau)
    assert row.tau_in == pytest.approx(tau) and row.l_out == pytest.approx(length)
    assert row.shift_in == pytest.approx(shift, abs=1e-12)
    # textbook approximations ΔR ≈ L²/24R, XM ≈ L/2 − L³/240R²
    assert shift == pytest.approx(length**2 / (24 * r), rel=1e-3)
    assert xm == pytest.approx(length / 2 - length**3 / (240 * r * r), rel=1e-6)
    assert row.t_in == pytest.approx(xm + (r + shift) * math.tan(d / 2), abs=1e-9)
    assert row.t_out == pytest.approx(row.t_in, abs=1e-9)
    assert row.arc_angle == pytest.approx(d - 2 * tau, abs=1e-12)

    axis = Axis(rq)
    _check_continuity(axis)
    kinds = [e.kind for e in axis.elements]
    assert kinds == ["tangent", "clothoid", "arc", "clothoid", "tangent"]
    mp = {m.code: m for m in res.main_points}
    assert list(mp) == ["BP", "TS", "SC", "MC", "CS", "ST", "EP"]
    assert mp["SC"].chainage - mp["TS"].chainage == pytest.approx(length)
    assert mp["ST"].chainage - mp["CS"].chainage == pytest.approx(length)
    assert wrap_pi(mp["SC"].azimuth - mp["TS"].azimuth) == pytest.approx(turn * tau, abs=1e-12)
    assert wrap_pi(mp["ST"].azimuth - mp["TS"].azimuth) == pytest.approx(turn * d, abs=1e-12)
    # ST lies on the outgoing tangent at T from the vertex; MC on the bisector at E
    assert math.hypot(mp["ST"].x - v[0], mp["ST"].y - v[1]) == pytest.approx(row.t_out, abs=1e-9)
    assert math.hypot(mp["MC"].x - v[0], mp["MC"].y - v[1]) == pytest.approx(row.external, abs=1e-9)
    # the arc is at distance R from the centre, the SC point too
    assert row.centre_x is not None and row.centre_y is not None
    assert math.hypot(mp["SC"].x - row.centre_x, mp["SC"].y - row.centre_y) == pytest.approx(
        r, abs=1e-9
    )
    assert math.hypot(mp["CS"].x - row.centre_x, mp["CS"].y - row.centre_y) == pytest.approx(
        r, abs=1e-9
    )


def test_asymmetric_curve_and_mirror_image():
    verts = [
        {"x": E0, "y": N0},
        {"name": "K1", "x": E0 + 50, "y": N0 + 600, "radius": 300, "l_in": 60, "a_out": 220},
        {"name": "K2", "x": E0 + 700, "y": N0 + 900, "radius": 500, "l_in": 0, "l_out": 80},
        {"name": "K3", "x": E0 + 1200, "y": N0 + 700, "radius": 250},
        {"x": E0 + 1500, "y": N0 + 1200},
    ]
    rq = req(verts)
    res = alignment(rq)
    assert [i.code for i in res.issues] == []
    axis = Axis(rq)
    _check_continuity(axis)
    k1 = res.vertices[1]
    assert k1.l_in == pytest.approx(60) and k1.l_out == pytest.approx(220**2 / 300)
    # the centre is R + ΔR from both tangent lines (independent check of T₁, T₂)
    for (p, q), shift in (
        ((verts[0], verts[1]), k1.shift_in),
        ((verts[1], verts[2]), k1.shift_out),
    ):
        dx, dy = q["x"] - p["x"], q["y"] - p["y"]
        assert k1.centre_x is not None and k1.centre_y is not None and shift is not None
        dist = abs((k1.centre_x - p["x"]) * dy - (k1.centre_y - p["y"]) * dx) / math.hypot(dx, dy)
        assert dist == pytest.approx(300 + shift, abs=1e-9)
    codes = [m.code for m in res.main_points if m.vertex == "K2"]
    assert codes == ["PC", "MC", "CS", "ST"]
    mirror = alignment(req([{**v, "x": 2 * E0 - v["x"]} for v in verts]))
    for a, b in zip(res.vertices, mirror.vertices, strict=True):
        if a.deflection is not None:
            assert b.deflection == pytest.approx(-a.deflection, abs=1e-12)
            assert b.t_in == pytest.approx(a.t_in, abs=1e-9)
            assert b.t_out == pytest.approx(a.t_out, abs=1e-9)
    assert mirror.length == pytest.approx(res.length, abs=1e-9)


# --------------------------------------------------------------------- round trips


ROAD = [
    {"x": E0, "y": N0},
    {"name": "K1", "x": E0, "y": N0 + 500, "radius": 300, "a_in": 150},
    {"name": "K2", "x": E0 + 400, "y": N0 + 800, "radius": 250},
    {"name": "K3", "x": E0 + 900, "y": N0 + 800, "radius": 200, "l_in": 50, "l_out": 70},
    {"x": E0 + 1200, "y": N0 + 1300},
]


@pytest.mark.parametrize("offset", [-15.0, -2.5, 0.0, 3.0, 18.0])
def test_chainage_offset_round_trip_on_every_element(offset):
    axis = Axis(req(ROAD, start_chainage=1000.0))
    assert {e.kind for e in axis.elements} == {"tangent", "clothoid", "arc"}
    for e in axis.elements:
        for f in (0.0, 0.13, 0.5, 0.87, 1.0):
            ch = e.s0 + f * e.length
            x, y, az, inside = axis.point_at(ch, offset)
            assert inside
            ch2, off2, az2, _k, inside2 = axis.station_of(x, y)
            assert inside2
            assert ch2 == pytest.approx(ch, abs=1e-8)
            assert off2 == pytest.approx(offset, abs=1e-8)
            assert abs(wrap_pi(az2 - az)) < 1e-10


def test_projection_beyond_the_ends_extends_the_end_tangents():
    axis = Axis(req(ROAD))
    x, y, _, inside = axis.point_at(-30.0, 4.0)
    assert not inside and (x, y) == pytest.approx((E0 + 4.0, N0 - 30.0))
    ch, off, _, k, inside = axis.station_of(E0 - 5.0, N0 - 20.0)
    assert not inside and k is None
    assert (ch, off) == pytest.approx((-20.0, -5.0))
    end_x, end_y, _, _ = axis.point_at(axis.end + 10.0, 0.0)
    ch, off, *_ = axis.station_of(end_x, end_y)
    assert ch == pytest.approx(axis.end + 10.0) and off == pytest.approx(0.0, abs=1e-9)


def test_locate_endpoint_with_profile_cut_and_fill():
    prof = {"pvis": [{"chainage": 0, "elevation": 100}, {"chainage": 2000, "elevation": 120}]}
    res = locate(
        LocateRequest.model_validate(
            {
                "alignment": {"vertices": ROAD, "profile": prof},
                "stations": [{"name": "s", "chainage": 250, "offset": -3.5}],
                "points": [{"name": "p", "x": E0 + 2, "y": N0 + 100, "z": 101.5}],
            }
        )
    )
    s = res.stations[0]
    assert (s.x, s.y, s.z) == pytest.approx((E0 - 3.5, N0 + 250, 102.5))
    p = res.points[0]
    assert (p.chainage, p.offset, p.z_design) == pytest.approx((100, 2, 101))
    assert p.dz == pytest.approx(0.5)


# -------------------------------------------------------------------------------- issues


def test_issues_for_inconsistent_geometry():
    def codes(vs):
        return [i.code for i in alignment(req(vs)).issues]

    base = [{"x": 0, "y": 0}, {"x": 0, "y": 100}, {"x": 100, "y": 100}]
    assert codes(base) == ["ALIGN_NO_RADIUS"]
    assert codes([base[0], {**base[1], "radius": 200}, base[2]]) == ["ALIGN_OVERLAP"] * 2
    assert codes([base[0], {**base[1], "radius": 20, "l_in": 40}, base[2]]) == [
        "ALIGN_CLOTHOIDS_TOO_LONG"
    ]
    assert codes([base[0], {**base[1], "radius": 30, "a_in": 5}, base[2]]) == [
        "ALIGN_CLOTHOID_RANGE"
    ]
    straight = [{"x": 0, "y": 0}, {"x": 0, "y": 50, "radius": 100}, {"x": 0, "y": 100}]
    r = alignment(req(straight))
    assert [i.code for i in r.issues] == ["ALIGN_NO_DEFLECTION"]
    assert r.length == pytest.approx(100)
    bad = alignment(req([base[0], {**base[1], "radius": 200}, base[2]]))
    assert bad.elements == [] and bad.issues[0].params["overlap"] > 0
    with pytest.raises(ValueError, match="overlap"):
        Axis(req([base[0], {**base[1], "radius": 200}, base[2]]))
    with pytest.raises(ValueError, match="coincide"):
        alignment(req([{"x": 0, "y": 0}, {"x": 0, "y": 0}]))
    with pytest.raises(ValueError, match="not both"):
        req(
            [
                {"x": 0, "y": 0},
                {"x": 0, "y": 1, "radius": 5, "a_in": 1, "l_in": 2},
                {"x": 1, "y": 1},
            ]
        )
    with pytest.raises(ValueError, match="radius"):
        req([{"x": 0, "y": 0}, {"x": 0, "y": 1, "a_in": 1}, {"x": 1, "y": 1}])


# ------------------------------------------------------------------------------ stakeout


def test_stakeout_round_chainages_main_points_and_offsets():
    rq = AlignmentStakeoutRequest.model_validate(
        {
            "alignment": {"vertices": ROAD, "start_chainage": 1013.5},
            "interval": 20,
            "offsets": [3.5, -3.5, 0],
        }
    )
    rows = stakeout(rq).rows
    axis = Axis(rq.alignment)
    chs = sorted({r.chainage for r in rows})
    regular = [c for c in chs if not any(r.code for r in rows if r.chainage == c)]
    assert chs[0] == pytest.approx(1013.5) and chs[1] == pytest.approx(1020.0)
    assert all(abs(c / 20 - round(c / 20)) < 1e-9 for c in regular)
    codes = [r.code for r in rows if r.code and r.offset == 0]
    assert codes == [m[0] for m in axis.geo.main_points]
    for r in rows:
        x, y, *_ = axis.point_at(r.chainage, r.offset)
        assert (r.x, r.y) == pytest.approx((x, y), abs=1e-9)
    first = [r.offset for r in rows if r.chainage == chs[0]]
    assert first == [-3.5, 0.0, 3.5]
    with pytest.raises(ValueError, match="Too many"):
        stakeout(
            AlignmentStakeoutRequest.model_validate(
                {"alignment": {"vertices": ROAD}, "interval": 0.01, "offsets": [0, 1]}
            )
        )
    with pytest.raises(ValueError, match="range"):
        stakeout(
            AlignmentStakeoutRequest.model_validate(
                {"alignment": {"vertices": ROAD}, "from_chainage": 5000, "to_chainage": 6000}
            )
        )


# ------------------------------------------------------------------------------- profile


def test_parabolic_vertical_curve():
    p = Profile(
        VerticalProfile.model_validate(
            {
                "pvis": [
                    {"chainage": 0, "elevation": 100},
                    {"name": "V1", "chainage": 200, "elevation": 108, "length": 120},  # +4 % → −2 %
                    {"chainage": 500, "elevation": 102},
                ]
            }
        )
    )
    assert not p.errors
    g1, g2, L = 0.04, -0.02, 120.0
    z_pvi, grade = p.at(200)  # type: ignore[misc]
    assert z_pvi == pytest.approx(108 + (g2 - g1) * L / 8, abs=1e-12)  # mid-ordinate
    assert grade == pytest.approx((g1 + g2) / 2)
    assert p.at(140) == pytest.approx((108 - g1 * 60, g1))
    assert p.at(260) == pytest.approx((108 + g2 * 60, g2))
    assert p.at(50) == pytest.approx((102, g1))
    assert p.at(600) is None
    c = p.result().curves[0]
    assert c.kind == "crest" and c.radius == pytest.approx(L / 0.06)
    x = -g1 * L / (g2 - g1)
    assert c.extreme_chainage == pytest.approx(140 + x)
    assert c.extreme_elevation == pytest.approx(p.at(140 + x)[0])  # type: ignore[index]
    by_h = Profile(
        VerticalProfile.model_validate(
            {
                "pvis": [
                    {"chainage": 0, "elevation": 100},
                    {"chainage": 200, "elevation": 108, "radius": 2000},
                    {"chainage": 500, "elevation": 102},
                ]
            }
        )
    )
    assert by_h.lengths[1] == pytest.approx(120.0)


def test_profile_errors():
    over = Profile(
        VerticalProfile.model_validate(
            {
                "pvis": [
                    {"chainage": 0, "elevation": 0},
                    {"chainage": 50, "elevation": 5, "length": 200},
                    {"chainage": 300, "elevation": 0},
                ]
            }
        )
    )
    assert [i.code for i in over.sink.items] == ["ALIGN_VERTICAL_OVERLAP"]
    with pytest.raises(ValueError, match="increasing"):
        Profile(
            VerticalProfile.model_validate(
                {"pvis": [{"chainage": 10, "elevation": 0}, {"chainage": 10, "elevation": 1}]}
            )
        )
    res = alignment(
        req(
            ROAD,
            profile={
                "pvis": [
                    {"chainage": 0, "elevation": 0},
                    {"chainage": 50, "elevation": 5, "length": 200},
                    {"chainage": 300, "elevation": 0},
                ]
            },
        )
    )
    assert res.profile is None and res.elements
    with pytest.raises(ValueError, match="overlap"):
        Axis(
            req(
                ROAD,
                profile={
                    "pvis": [
                        {"chainage": 0, "elevation": 0},
                        {"chainage": 50, "elevation": 5, "length": 200},
                        {"chainage": 300, "elevation": 0},
                    ]
                },
            )
        )
