"""Numerical precision of the float64 engine against a 50-digit Decimal reference.

Why not Decimal in the engine? Every coordinate goes through sin/cos/atan2; Decimal has no
trigonometry, and trigonometric results are irrational anyway, so exact decimal arithmetic
gains nothing. What matters is that float64 (≈ 15.9 significant digits) keeps the error far
below the measurement noise (≈ 1 mm) at ΕΓΣΑ87 magnitudes (E up to ~1 000 000 m,
N up to ~4 700 000 m). These tests prove that bound: the engine is compared with an
independent re-computation in 50-significant-digit Decimal arithmetic (sin/cos/π from the
recipes in the Python `decimal` documentation), fed with exactly the same input numbers.
"""

from __future__ import annotations

import math
import random
from decimal import Decimal, getcontext

import pytest

from atsurvey import ControlPoint, Observation, ProjectInput, Setup, TraverseSpec, compute_project
from atsurvey.core.models import ComputeSettings, ProjectResult, ReductionSettings
from atsurvey.core.units import from_rad, to_rad

getcontext().prec = 50

PLANE = ReductionSettings(scale_mode="none", elevation_reduction=False, curvature_refraction=False)


# ---- Decimal trigonometry (Python decimal documentation recipes) ---------------------------


def d_pi() -> Decimal:
    getcontext().prec += 2
    three = Decimal(3)
    lasts, t, s, n, na, d, da = 0, three, 3, 1, 0, 0, 24
    while s != lasts:
        lasts = s
        n, na = n + na, na + 8
        d, da = d + da, da + 32
        t = (t * n) / d
        s += t
    getcontext().prec -= 2
    return +s


def d_cos(x: Decimal) -> Decimal:
    getcontext().prec += 2
    i, lasts, s, fact, num, sign = 0, 0, Decimal(1), 1, Decimal(1), 1
    while s != lasts:
        lasts = s
        i += 2
        fact *= i * (i - 1)
        num *= x * x
        sign *= -1
        s += num / fact * sign
    getcontext().prec -= 2
    return +s


def d_sin(x: Decimal) -> Decimal:
    getcontext().prec += 2
    i, lasts, s, fact, num, sign = 1, 0, x, 1, x, 1
    while s != lasts:
        lasts = s
        i += 2
        fact *= i * (i - 1)
        num *= x * x
        sign *= -1
        s += num / fact * sign
    getcontext().prec -= 2
    return +s


PI = d_pi()
TWO_PI = 2 * PI


def d_reduce(a: Decimal) -> Decimal:
    """Reduce to (-π, π] so the Taylor series converge quickly."""
    a = a % TWO_PI
    return a - TWO_PI if a > PI else a


# ---- an open traverse that both engines can compute from identical inputs -------------------


def open_traverse(n_legs: int, seed: int, x0: float, y0: float):
    """Start orientation due north (azimuth exactly 0), angles and distances random floats.

    The observations use hz_bs = 0 and hz_fs = β and no zenith, so the engine's angle and
    horizontal distance equal the input floats bit for bit; the only difference between the
    two computations is the arithmetic precision.
    """
    rng = random.Random(seed)
    names = ["A", "B"] + [f"P{i}" for i in range(n_legs)]
    betas = [rng.uniform(math.pi * 0.6, math.pi * 1.4) for _ in range(n_legs)]
    dists = [rng.uniform(150.0, 900.0) for _ in range(n_legs)]
    setups = []
    for i in range(1, len(names) - 1):
        bs, st, fs = names[i - 1], names[i], names[i + 1]
        obs = [
            Observation(target=bs, hz=0.0, sd=dists[i - 2] if i > 1 else None),
            Observation(target=fs, hz=betas[i - 1], sd=dists[i - 1]),
        ]
        setups.append(Setup(station=st, observations=obs))
    inp = ProjectInput(
        control_points=[
            ControlPoint(name="A", x=x0, y=y0 - 500.0),
            ControlPoint(name="B", x=x0, y=y0),
        ],
        setups=setups,
        traverses=[TraverseSpec(route=names, kind="open")],
        settings=ComputeSettings(reduction=PLANE, compute_detail=False),
    )
    return inp, names, betas, dists


def decimal_reference(x0: float, y0: float, betas: list[float], dists: list[float]):
    x, y = Decimal(x0), Decimal(y0)
    az = Decimal(0)  # A → B is due north
    out = []
    for beta, d in zip(betas, dists, strict=True):
        az = az + Decimal(beta) + PI
        a = d_reduce(az)
        x += Decimal(d) * d_sin(a)
        y += Decimal(d) * d_cos(a)
        out.append((x, y))
    return out


@pytest.mark.parametrize(
    ("x0", "y0"),
    [
        (476_000.123, 4_205_000.456),  # Attica
        (899_999.987, 4_699_999.991),  # worst-case ΕΓΣΑ87 magnitudes (NE Greece)
        (101_000.001, 3_850_000.002),  # far west / south (Crete, Ionian)
    ],
)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_float64_matches_50_digit_decimal_to_the_nanometre(x0, y0, seed):
    n = 60  # a long traverse: ~30 km of legs
    inp, names, betas, dists = open_traverse(n, seed, x0, y0)
    result = compute_project(inp)
    assert result.traverses[0].status == "ok", [i.message for i in result.issues]
    pts = {p.name: p for p in result.points}
    ref = decimal_reference(x0, y0, betas, dists)
    worst = max(
        max(abs(Decimal(pts[name].x) - rx), abs(Decimal(pts[name].y) - ry))
        for name, (rx, ry) in zip(names[2:], ref, strict=True)
    )
    # 1e-6 m = one micrometre; measurement noise is ~1e-3 m
    assert worst < Decimal("1e-6"), f"max deviation {worst} m"


def test_bowditch_closure_on_long_perfect_traverse_is_exact():
    """A 60-leg traverse that returns to its start must close to well below a micrometre."""
    rng = random.Random(42)
    x0, y0 = 899_999.987, 4_699_999.991
    n = 60
    # regular polygon walk: exterior turns sum to 2π, so the loop closes exactly in theory
    turn = 2 * math.pi / n
    names = ["A", "B"] + [f"P{i}" for i in range(n - 1)] + ["B", "A"]
    side = 400.0 + rng.random()
    truth = {"B": (x0, y0)}
    az = math.pi / 2  # A→B due east
    truth["A"] = (x0 - 300.0, y0)
    pos = truth["B"]
    for i in range(n - 1):
        pos = (pos[0] + side * math.sin(az), pos[1] + side * math.cos(az))
        truth[f"P{i}"] = pos
        az += turn
    # build observations from the geometry
    setups = []
    route = names
    for i in range(1, len(route) - 1):
        bs, st, fs = route[i - 1], route[i], route[i + 1]
        (xb, yb), (xs, ys), (xf, yf) = truth[bs], truth[st], truth[fs]
        a_b = math.atan2(xb - xs, yb - ys)
        a_f = math.atan2(xf - xs, yf - ys)
        setups.append(
            Setup(
                station=st,
                observations=[
                    Observation(target=bs, hz=0.0, sd=math.hypot(xb - xs, yb - ys)),
                    Observation(
                        target=fs, hz=(a_f - a_b) % (2 * math.pi), sd=math.hypot(xf - xs, yf - ys)
                    ),
                ],
            )
        )
    r = compute_project(
        ProjectInput(
            control_points=[
                ControlPoint(name="A", x=truth["A"][0], y=truth["A"][1]),
                ControlPoint(name="B", x=x0, y=y0),
            ],
            setups=setups,
            traverses=[TraverseSpec(route=route)],
            settings=ComputeSettings(reduction=PLANE, compute_detail=False),
        )
    )
    t = r.traverses[0]
    assert t.kind == "closed"
    assert abs(t.angular_misclosure) < 1e-12  # radians
    assert t.linear_misclosure < 1e-7  # 0.1 µm over ~24 km


def test_json_round_trip_is_bit_exact():
    inp, *_ = open_traverse(20, 7, 899_999.987, 4_699_999.991)
    result = compute_project(inp)
    again = ProjectResult.model_validate_json(result.model_dump_json())
    for a, b in zip(result.points, again.points, strict=True):
        assert a.x == b.x and a.y == b.y  # identical binary values, not just close


@pytest.mark.parametrize("unit", ["gon", "deg", "dms"])
def test_angle_unit_round_trip(unit):
    rng = random.Random(3)
    for _ in range(2000):
        v = rng.uniform(0, 400 if unit == "gon" else 360)
        if unit == "dms":
            d = math.floor(v)
            v = d + rng.randrange(60) / 100 + rng.randrange(6000) / 1_000_000
        back = from_rad(to_rad(v, unit), unit)
        assert back == pytest.approx(v, abs=1e-9)
