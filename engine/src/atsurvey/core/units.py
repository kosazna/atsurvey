"""Angle units and conversions.

Internally the engine works exclusively in **radians** and **metres**. Conversion to
and from the user's preferred unit happens only at the boundaries (parsers, API, UI,
exports). Greek practice uses grads (gon, 400 per circle), so that is the default
display unit throughout the product.
"""

from __future__ import annotations

import math
from typing import Literal

AngleUnit = Literal["gon", "deg", "dms", "rad"]

TWO_PI = 2.0 * math.pi
GON_TO_RAD = math.pi / 200.0
DEG_TO_RAD = math.pi / 180.0
#: One centesimal second (cc) = 1e-4 gon. Greek misclosures are quoted in cc.
CC_TO_RAD = 1e-4 * GON_TO_RAD


def wrap_2pi(a: float) -> float:
    """Normalise an angle to [0, 2π)."""
    r = math.fmod(a, TWO_PI)
    if r < 0:
        r += TWO_PI
    # fmod can return 2π - ε that rounds to 2π for values like -1e-17
    return 0.0 if r >= TWO_PI else r


def wrap_pi(a: float) -> float:
    """Normalise an angle to [-π, π)."""
    return wrap_2pi(a + math.pi) - math.pi


def dms_to_deg(value: float) -> float:
    """Convert a packed DDD.MMSSss value (e.g. 123.4530 = 123°45'30") to decimal degrees."""
    sign = -1.0 if value < 0 else 1.0
    v = abs(value)
    d = math.floor(v)
    rest = (v - d) * 100.0
    m = math.floor(rest + 1e-9)
    s = (rest - m) * 100.0
    return sign * (d + m / 60.0 + s / 3600.0)


def deg_to_dms(value: float) -> float:
    """Inverse of :func:`dms_to_deg` (packed DDD.MMSSss)."""
    sign = -1.0 if value < 0 else 1.0
    v = abs(value)
    d = math.floor(v)
    m_full = (v - d) * 60.0
    m = math.floor(m_full + 1e-12)
    s = (m_full - m) * 60.0
    if s >= 59.99999999:
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        d += 1
    return sign * (d + m / 100.0 + s / 10000.0)


def to_rad(value: float, unit: AngleUnit) -> float:
    if unit == "gon":
        return value * GON_TO_RAD
    if unit == "deg":
        return value * DEG_TO_RAD
    if unit == "dms":
        return dms_to_deg(value) * DEG_TO_RAD
    if unit == "rad":
        return value
    raise ValueError(f"Unknown angle unit: {unit}")


def from_rad(value: float, unit: AngleUnit) -> float:
    if unit == "gon":
        return value / GON_TO_RAD
    if unit == "deg":
        return value / DEG_TO_RAD
    if unit == "dms":
        return deg_to_dms(value / DEG_TO_RAD)
    if unit == "rad":
        return value
    raise ValueError(f"Unknown angle unit: {unit}")


def rad_to_cc(value: float) -> float:
    return value / CC_TO_RAD


def circular_mean(angles: list[float]) -> float:
    """Mean of directions, robust to the 0/2π wrap. Result in [0, 2π)."""
    if not angles:
        raise ValueError("circular_mean of empty list")
    ref = angles[0]
    offset = sum(wrap_pi(a - ref) for a in angles) / len(angles)
    return wrap_2pi(ref + offset)


def circular_spread(angles: list[float]) -> float:
    """Max − min of directions around their circular mean (radians, ≥ 0)."""
    if len(angles) < 2:
        return 0.0
    m = circular_mean(angles)
    dev = [wrap_pi(a - m) for a in angles]
    return max(dev) - min(dev)
