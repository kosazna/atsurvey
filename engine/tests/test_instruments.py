"""Instrument checks: two-face test, two-peg test and EDM additive constant."""

import math

import numpy as np
import pytest
from pydantic import ValidationError

from atsurvey.core.instruments import (
    RAD_TO_CC,
    EdmObservation,
    EdmRequest,
    PegSetup,
    TwoFaceRequest,
    TwoFaceTarget,
    TwoPegRequest,
    edm_constant,
    two_face_test,
    two_peg_test,
)

CC = 1.0 / RAD_TO_CC  # one centesimal second in radians
GON = math.pi / 200.0


def face_pair(name, r, z, c, i, a=0.0, noise=(0.0, 0.0, 0.0, 0.0)):
    e = c / math.sin(z) + a * math.cos(z) / math.sin(z)
    return TwoFaceTarget(
        name=name,
        hz1=(r + e + noise[0]) % (2 * math.pi),
        hz2=(r + math.pi - e + noise[1]) % (2 * math.pi),
        v1=z + i + noise[2],
        v2=2 * math.pi - z + i + noise[3],
    )


TARGETS = [(0.3, 100), (1.7, 70), (2.9, 120), (4.1, 85), (5.5, 112)]  # (Hz rad, z gon)


def test_two_face_recovers_c_i_and_a_exactly():
    c, i, a = 12 * CC, -25 * CC, 30 * CC
    req = TwoFaceRequest(
        targets=[face_pair(f"T{k}", r, z * GON, c, i, a) for k, (r, z) in enumerate(TARGETS)]
    )
    res = two_face_test(req)
    assert res.trunnion_estimated
    assert res.collimation == pytest.approx(c, abs=1e-12)
    assert res.trunnion == pytest.approx(a, abs=1e-12)
    assert res.index == pytest.approx(i, abs=1e-12)
    assert res.dof_hz == 3 and res.dof_v == 4
    assert res.sigma_collimation == pytest.approx(0, abs=1e-12)
    for row, (r, z) in zip(res.rows, TARGETS, strict=True):
        assert row.zenith == pytest.approx(z * GON, abs=1e-12)
        assert row.hz == pytest.approx(r, abs=1e-12)  # face mean is free of c and a
    assert res.issues == []


def test_two_face_horizontal_targets_only_estimates_collimation():
    c, i, a = -8 * CC, 15 * CC, 40 * CC
    req = TwoFaceRequest(
        targets=[face_pair(f"T{k}", r, 100 * GON, c, i, a) for k, (r, _) in enumerate(TARGETS)]
    )
    res = two_face_test(req)
    assert not res.trunnion_estimated and res.trunnion is None
    assert res.collimation == pytest.approx(c, abs=1e-12)  # cot z = 0: a has no effect
    assert [x.code for x in res.issues] == ["INSTR_TRUNNION_UNRESOLVED"]
    with pytest.raises(ValueError, match="cannot be separated"):
        two_face_test(req.model_copy(update={"trunnion": "always"}))


def test_two_face_noise_gives_sensible_sigma():
    rng = np.random.default_rng(1)
    c, i, a = 10 * CC, 5 * CC, -20 * CC
    targets = []
    for k in range(40):
        r, z = TARGETS[k % 5]
        targets.append(face_pair(f"T{k}", r, z * GON, c, i, a, tuple(rng.normal(0, 3 * CC, 4))))
    res = two_face_test(TwoFaceRequest(targets=targets))
    # δ = ½(Hz_I − Hz_II): σ_δ = 3cc/√2 ≈ 2.1cc; same for i
    assert res.s0_hz == pytest.approx(3 * CC / math.sqrt(2), rel=0.3)
    assert res.s0_v == pytest.approx(3 * CC / math.sqrt(2), rel=0.3)
    assert abs(res.collimation - c) < 4 * (res.sigma_collimation or 0)
    assert abs((res.trunnion or 0) - a) < 4 * (res.sigma_trunnion or 0)
    assert abs(res.index - i) < 4 * (res.sigma_index or 0)


def test_two_face_wraps_around_zero_and_flags_bad_pairs():
    c = 20 * CC
    t = face_pair("N", 2 * math.pi - 5 * CC, 100 * GON, c, 0.0)
    res = two_face_test(TwoFaceRequest(targets=[t]))
    assert res.collimation == pytest.approx(c, abs=1e-12)
    assert res.sigma_collimation is None and res.dof_hz == 0
    bad = t.model_copy(update={"hz2": t.hz2 + 0.05})
    res = two_face_test(TwoFaceRequest(targets=[bad]))
    assert res.issues[0].code == "INSTR_FACE_MISMATCH"
    steep = face_pair("S", 1.0, 2 * GON, c, 0.0)
    with pytest.raises(ValueError, match="too steep"):
        two_face_test(TwoFaceRequest(targets=[steep]))


def _peg_readings(eps, ha, hb, hi, sa, sb):
    """Staff readings from an instrument at collimation height hi with inclination eps."""
    return PegSetup(a=hi - ha + eps * sa, b=hi - hb + eps * sb, dist_a=sa, dist_b=sb)


@pytest.mark.parametrize(
    ("method", "d1", "d2"),
    [
        ("forstner", (15, 30), (30, 15)),
        ("kukkamaki", (10, 10), (40, 20)),
        ("middle_end", (15, 15), (33, 3)),
    ],
)
def test_two_peg_known_values(method, d1, d2):
    eps = 2e-3 / 30.0  # 2 mm per 30 m
    ha, hb = 100.000, 100.4567
    s1 = _peg_readings(eps, ha, hb, 101.5, *d1)
    s2 = _peg_readings(eps, ha, hb, 101.62, *d2)
    r = two_peg_test(TwoPegRequest(method=method, setup1=s1, setup2=s2))
    assert r.epsilon == pytest.approx(eps, rel=1e-9)
    assert r.error_mm_per_30m == pytest.approx(2.0, rel=1e-9)
    assert r.error_arcsec == pytest.approx(math.atan(eps) * 206264.806, rel=1e-8)
    assert r.error_cc == pytest.approx(math.atan(eps) * 636619.772, rel=1e-8)
    assert r.dh_true == pytest.approx(hb - ha, abs=1e-12)
    assert r.corrected_a2 == pytest.approx(101.62 - ha, abs=1e-12)
    assert r.corrected_b2 == pytest.approx(101.62 - hb, abs=1e-12)
    assert r.within_tolerance  # default 3 mm / 30 m


def test_two_peg_textbook_numbers_and_tolerance():
    # setup 1 in the middle: a 1.523, b 1.211 (Δh true +0.312); setup 2 near A (3 m / 57 m):
    # a 1.408, b 1.083 → ε = (0.312 − 0.325) / (0 − (3 − 57)) = −0.013/54
    r = two_peg_test(
        TwoPegRequest(
            method="middle_end",
            setup1=PegSetup(a=1.523, b=1.211, dist_a=30, dist_b=30),
            setup2=PegSetup(a=1.408, b=1.083, dist_a=3, dist_b=57),
            tolerance_mm_per_30m=3.0,
        )
    )
    assert r.epsilon == pytest.approx(-0.013 / 54)
    assert r.error_mm_per_30m == pytest.approx(-0.013 / 54 * 30000)
    assert not r.within_tolerance  # 7.2 mm / 30 m
    assert r.dh_true == pytest.approx(0.312)
    assert r.corrected_b2 - r.corrected_a2 == pytest.approx(-0.312)


def test_two_peg_needs_different_imbalance():
    s = PegSetup(a=1.5, b=1.2, dist_a=20, dist_b=20)
    with pytest.raises(ValidationError, match="different sight lengths"):
        TwoPegRequest(setup1=s, setup2=s)


PILLARS = ["P0", "P1", "P2", "P3"]
TRUE_X = [0.0, 52.3456, 131.0021, 247.8888]


def _baseline(k0, scale=0.0, rng=None, sigma=0.0005, repeat=1):
    obs = []
    for _ in range(repeat):
        for i in range(len(PILLARS)):
            for j in range(i + 1, len(PILLARS)):
                true = TRUE_X[j] - TRUE_X[i]
                d = (true - k0) / (1 + scale)  # instrument reading: d + k0 + scale·d = true
                if rng is not None:
                    d += rng.normal(0, sigma)
                obs.append(EdmObservation(frm=PILLARS[i], to=PILLARS[j], distance=d))
    return obs


def test_edm_constant_recovered_exactly_with_unknown_positions():
    r = edm_constant(EdmRequest(pillars=PILLARS, observations=_baseline(-0.0234)))
    assert r.constant == pytest.approx(-0.0234, abs=1e-10)
    assert r.positions == pytest.approx(TRUE_X, abs=1e-9)
    assert r.dof == 2 and r.scale_ppm is None
    assert all(abs(row.residual) < 1e-9 for row in r.rows)
    assert r.rows[0].adjusted == pytest.approx(TRUE_X[1])


def test_edm_constant_with_noise_and_reversed_observations():
    rng = np.random.default_rng(9)
    obs = _baseline(0.0112, rng=rng, repeat=5)
    obs = [
        o.model_copy(update={"frm": o.to, "to": o.frm}) if k % 3 == 0 else o
        for k, o in enumerate(obs)
    ]
    r = edm_constant(EdmRequest(pillars=PILLARS, observations=obs))
    assert r.dof == 30 - 4
    assert r.s0 == pytest.approx(0.0005, rel=0.35)
    assert abs(r.constant - 0.0112) < 4 * (r.sigma_constant or 0)
    # d + v + k0 = x_j − x_i
    for row in r.rows:
        assert row.distance + row.residual + r.constant == pytest.approx(row.adjusted, abs=1e-9)


def test_edm_constant_and_scale_with_certified_baseline():
    obs = _baseline(0.0071, scale=-12e-6)
    r = edm_constant(EdmRequest(pillars=PILLARS, observations=obs, positions=TRUE_X))
    assert r.constant == pytest.approx(0.0071, abs=1e-9)
    assert r.scale_ppm == pytest.approx(-12, abs=1e-4)
    assert r.dof == 4


def test_edm_three_pillars_no_redundancy_and_singular_layouts():
    obs = [o for o in _baseline(0.01) if "P3" not in (o.frm, o.to)]
    r = edm_constant(EdmRequest(pillars=PILLARS[:3], observations=obs))
    assert r.constant == pytest.approx(0.01, abs=1e-9)
    assert r.dof == 0 and r.sigma_constant is None
    assert [i.code for i in r.issues] == ["INSTR_EDM_NO_REDUNDANCY"]
    consecutive = [
        EdmObservation(frm="P0", to="P1", distance=50),
        EdmObservation(frm="P1", to="P2", distance=60),
        EdmObservation(frm="P1", to="P2", distance=60.001),
    ]
    with pytest.raises(ValueError, match="not determined"):
        edm_constant(EdmRequest(pillars=PILLARS[:3], observations=consecutive))


def test_edm_validation():
    obs = _baseline(0.0)
    with pytest.raises(ValidationError, match="unknown pillar"):
        EdmRequest(pillars=["A", "B", "C"], observations=obs)
    with pytest.raises(ValidationError, match="unique"):
        EdmRequest(pillars=["P0", "P0", "P1"], observations=obs)
    with pytest.raises(ValidationError, match="increase"):
        EdmRequest(pillars=PILLARS, observations=obs, positions=[0, 10, 5, 20])
