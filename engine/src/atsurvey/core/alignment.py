"""Road alignment: horizontal geometry from the tangent polygon (PI method) and the vertical
profile with parabolic curves.

Horizontal (οριζοντιογραφία). At every interior vertex V with deflection Δ the curve is
clothoid (A₁, L₁) – circular arc (R) – clothoid (A₂, L₂), with L = A² / R. For each clothoid
(Kasper, Schürba & Lorenz, *Die Klothoide als Trassierungselement*; RAS-L; Greek ΟΜΟΕ-Χ):

* tangent angle      τ = L / 2R
* end coordinates    X + iY = L · Σₖ (iτ)ᵏ / (k! (2k+1))   (Fresnel series, exact for any τ)
* shift of the arc   ΔR = Y − R (1 − cos τ)
* centre abscissa    XM = X − R sin τ

Tangent lengths of the (possibly asymmetric) curve, from the vertex to TS and to ST:

    T₁ = XM₁ + (R + ΔR₂) / sin|Δ| − (R + ΔR₁) / tan|Δ|
    T₂ = XM₂ + (R + ΔR₁) / sin|Δ| − (R + ΔR₂) / tan|Δ|

which reduce to T = XM + (R + ΔR) tan(|Δ|/2) for a symmetric curve and T = R tan(|Δ|/2) for a
plain circular one. The central angle of the arc is |Δ| − τ₁ − τ₂.

Vertical (μηκοτομή): see ``core/alignment_profile.py``.

All computations in float64 without intermediate rounding; the point queries are exact
inversions of the same element functions (tested round-trip to 1e-9 m).
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .alignment_models import (
    MAX_STAKEOUT_ROWS,
    AlignmentElement,
    AlignmentRequest,
    AlignmentResult,
    AlignmentStakeoutRequest,
    AlignmentStakeoutResult,
    AlignmentStakeoutRow,
    AlignmentVertex,
    ElementKind,
    LocateRequest,
    LocateResult,
    MainPoint,
    MainPointCode,
    PointRow,
    StationRow,
    VertexRow,
)
from .alignment_profile import Profile
from .geodesy import grid_azimuth
from .issues import IssueSink
from .units import CC_TO_RAD, wrap_2pi, wrap_pi

#: Deflections below 1 cc are treated as a straight line through the vertex
ANGLE_EPS = CC_TO_RAD
LENGTH_EPS = 1e-6
#: A projected foot may lie this far outside an element and still count as on it
FOOT_TOL = 1e-9
#: Guideline range of the clothoid parameter (RAS-L, ΟΜΟΕ-Χ): R/3 ≤ A ≤ R
A_MIN_RATIO = 1.0 / 3.0


# ----------------------------------------------------------------------------- clothoid


def clothoid_xy(length: float, a: float) -> tuple[float, float]:
    """Local coordinates (X along the tangent, Y towards the centre) of the point at arc length
    ``length`` from the origin of a clothoid with parameter ``a``.

    X + iY = ∫₀ˡ exp(i s² / 2A²) ds = l · Σₖ (iθ)ᵏ / (k! (2k+1)),  θ = l² / 2A².
    The series converges for every θ; for θ ≤ π (the largest τ the geometry admits) the largest
    term is < 4, so the rounding error stays at the 1e-15 relative level."""
    if length == 0.0:
        return 0.0, 0.0
    theta = length * length / (2.0 * a * a)
    term = complex(1.0, 0.0)  # (iθ)^k / k!
    total = complex(0.0, 0.0)
    k = 0
    while True:
        add = term / (2 * k + 1)
        total += add
        if abs(add) < 1e-17 * max(abs(total), 1e-300) and k > 2:
            break
        k += 1
        term *= complex(0.0, theta) / k
        if k > 200:  # unreachable for θ ≤ π; guards against misuse
            raise ValueError("Clothoid series did not converge")
    return length * total.real, length * total.imag


# ----------------------------------------------------------------------------- elements


@dataclass(frozen=True)
class _Elem:
    """One geometric element. Clothoids entering a curve are evaluated from their start
    (curvature 0 → 1/R); clothoids leaving a curve from their end (1/R ← 0), which keeps both
    in the series' best-conditioned form and makes ST exact."""

    kind: ElementKind
    s0: float  # start chainage
    length: float
    x0: float  # anchor point: start, or end for an exiting clothoid
    y0: float
    az0: float  # anchor azimuth (forward direction)
    turn: int = 0  # +1 right (clockwise), -1 left
    radius: float | None = None
    a: float | None = None
    entering: bool = True
    vertex: str | None = None

    def at(self, s: float) -> tuple[float, float, float]:
        """Point and forward azimuth at local distance ``s`` (0 … length) from the start."""
        sa, ca = math.sin(self.az0), math.cos(self.az0)
        if self.kind == "tangent":
            return self.x0 + s * sa, self.y0 + s * ca, self.az0
        d = self.turn
        if self.kind == "arc":
            r = self.radius or 0.0
            phi = s / r
            chord = 2.0 * r * math.sin(phi / 2.0)
            am = self.az0 + d * phi / 2.0
            return (
                self.x0 + chord * math.sin(am),
                self.y0 + chord * math.cos(am),
                wrap_2pi(self.az0 + d * phi),
            )
        a = self.a or 0.0
        # right-hand normal n = (cos α, −sin α); the curve bends to the side d · n
        if self.entering:
            u, v = clothoid_xy(s, a)
            th = s * s / (2.0 * a * a)
            return (
                self.x0 + u * sa + d * v * ca,
                self.y0 + u * ca - d * v * sa,
                wrap_2pi(self.az0 + d * th),
            )
        l_back = self.length - s
        u, v = clothoid_xy(l_back, a)
        th = l_back * l_back / (2.0 * a * a)
        return (
            self.x0 - u * sa + d * v * ca,
            self.y0 - u * ca - d * v * sa,
            wrap_2pi(self.az0 - d * th),
        )

    def feet(self, px: float, py: float) -> list[tuple[float, float]]:
        """Local distances s with the perpendicular from P landing on this element, and the
        signed offsets (right positive)."""
        if self.kind == "tangent":
            sa, ca = math.sin(self.az0), math.cos(self.az0)
            dx, dy = px - self.x0, py - self.y0
            return [(dx * sa + dy * ca, dx * ca - dy * sa)]
        if self.kind == "arc":
            return self._arc_feet(px, py)
        return self._clothoid_feet(px, py)

    def _arc_feet(self, px: float, py: float) -> list[tuple[float, float]]:
        r, d = self.radius or 0.0, self.turn
        cx = self.x0 + d * r * math.cos(self.az0)
        cy = self.y0 - d * r * math.sin(self.az0)
        dist = math.hypot(px - cx, py - cy)
        if dist < 1e-9:
            return []  # the centre is equidistant from the whole arc
        phi = wrap_2pi(d * (math.atan2(px - cx, py - cy) - math.atan2(self.x0 - cx, self.y0 - cy)))
        s = r * phi
        if s > self.length:
            s_neg = r * (phi - 2.0 * math.pi)
            if -s_neg < s - self.length:
                s = s_neg
        return [(s, d * (r - dist))]

    def _clothoid_feet(self, px: float, py: float) -> list[tuple[float, float]]:
        def g(s: float) -> float:
            x, y, az = self.at(s)
            return (px - x) * math.sin(az) + (py - y) * math.cos(az)

        n = min(64, max(4, math.ceil(self.length / 5.0)))
        ss = [self.length * k / n for k in range(n + 1)]
        gs = [g(s) for s in ss]
        out: list[tuple[float, float]] = []
        for k in range(n):
            lo, hi, glo, ghi = ss[k], ss[k + 1], gs[k], gs[k + 1]
            if glo == 0.0:
                out.append(self._foot_at(lo, px, py))
                continue
            if glo * ghi > 0.0:
                continue
            for _ in range(80):  # bisection: g decreases through the foot
                mid = 0.5 * (lo + hi)
                gm = g(mid)
                if (gm > 0.0) == (glo > 0.0):
                    lo, glo = mid, gm
                else:
                    hi = mid
                if hi - lo < 1e-12:
                    break
            out.append(self._foot_at(0.5 * (lo + hi), px, py))
        if gs[-1] == 0.0:
            out.append(self._foot_at(ss[-1], px, py))
        return out

    def _foot_at(self, s: float, px: float, py: float) -> tuple[float, float]:
        x, y, az = self.at(s)
        return s, (px - x) * math.cos(az) - (py - y) * math.sin(az)


# ------------------------------------------------------------------------------- curves


@dataclass(frozen=True)
class _Curve:
    vertex: str | None
    turn: int
    deflection: float
    radius: float
    a1: float
    l1: float
    a2: float
    l2: float
    tau1: float
    tau2: float
    shift1: float
    shift2: float
    xm1: float
    xm2: float
    t1: float
    t2: float
    az_in: float
    az_out: float
    ts: tuple[float, float]
    st: tuple[float, float]
    centre: tuple[float, float]
    arc_angle: float


@dataclass
class _Geometry:
    elements: list[_Elem] = field(default_factory=list)
    vertex_rows: list[VertexRow] = field(default_factory=list)
    main_points: list[tuple[MainPointCode, str | None, float]] = field(default_factory=list)
    issues: IssueSink = field(default_factory=IssueSink)
    start: float = 0.0
    end: float = 0.0

    @property
    def errors(self) -> list[str]:
        return [i.message for i in self.issues.items if i.severity == "error"]


def _label(v: AlignmentVertex, i: int) -> str:
    return v.name or f"K{i}"


def _spiral(v: AlignmentVertex, radius: float) -> tuple[float, float, float, float]:
    """(A₁, L₁, A₂, L₂); exit = entry when no exit value is given."""

    def resolve(a: float | None, length: float | None) -> tuple[float, float] | None:
        if a is not None:
            return a, a * a / radius
        if length is not None:
            return math.sqrt(length * radius), length
        return None

    first = resolve(v.a_in, v.l_in)
    second = resolve(v.a_out, v.l_out)
    if second is None:
        second = first if first is not None else (0.0, 0.0)
    if first is None:
        first = (0.0, 0.0)
    return first[0], first[1], second[0], second[1]


def _curve_at(vs: list[AlignmentVertex], i: int, sink: IssueSink) -> _Curve | None:
    prev, v, nxt = vs[i - 1], vs[i], vs[i + 1]
    name = _label(v, i)
    az_in = grid_azimuth(prev.x, prev.y, v.x, v.y)
    az_out = grid_azimuth(v.x, v.y, nxt.x, nxt.y)
    delta = wrap_pi(az_out - az_in)
    big = abs(delta)
    if big < ANGLE_EPS:
        if v.radius is not None:
            sink.warning(
                "ALIGN_NO_DEFLECTION",
                f"Vertex {name} is on a straight line; its curve is ignored",
                vertex=name,
            )
        return None
    if v.radius is None:
        sink.error(
            "ALIGN_NO_RADIUS",
            f"Vertex {name} changes direction but has no radius",
            vertex=name,
        )
        return None
    if big > math.pi - 1e-9:
        sink.error("ALIGN_REVERSAL", f"The axis reverses direction at {name}", vertex=name)
        return None
    r = v.radius
    a1, l1, a2, l2 = _spiral(v, r)
    tau1, tau2 = l1 / (2.0 * r), l2 / (2.0 * r)
    if tau1 + tau2 > big + 1e-12:
        sink.error(
            "ALIGN_CLOTHOIDS_TOO_LONG",
            f"At {name} the clothoids turn more than the deflection; shorten them or raise R",
            vertex=name,
        )
        return None
    for a in sorted({a1, a2}):  # once per distinct parameter
        if a > 0.0 and not (A_MIN_RATIO * r - 1e-9 <= a <= r + 1e-9):
            sink.warning(
                "ALIGN_CLOTHOID_RANGE",
                f"At {name} the clothoid parameter A = {a:.1f} is outside R/3 … R",
                vertex=name,
                a=round(a, 3),
                radius=round(r, 3),
            )
    x1, y1 = clothoid_xy(l1, a1) if l1 > 0 else (0.0, 0.0)
    x2, y2 = clothoid_xy(l2, a2) if l2 > 0 else (0.0, 0.0)
    shift1, shift2 = y1 - r * (1.0 - math.cos(tau1)), y2 - r * (1.0 - math.cos(tau2))
    xm1, xm2 = x1 - r * math.sin(tau1), x2 - r * math.sin(tau2)
    p1, p2 = r + shift1, r + shift2
    t1 = xm1 + p2 / math.sin(big) - p1 / math.tan(big)
    t2 = xm2 + p1 / math.sin(big) - p2 / math.tan(big)
    if t1 < 0.0 or t2 < 0.0:
        sink.error(
            "ALIGN_NEGATIVE_TANGENT",
            f"The curve at {name} starts or ends beyond its vertex; check the clothoids",
            vertex=name,
        )
        return None
    d = 1 if delta > 0 else -1
    ts = (v.x - t1 * math.sin(az_in), v.y - t1 * math.cos(az_in))
    st = (v.x + t2 * math.sin(az_out), v.y + t2 * math.cos(az_out))
    # centre: XM along the incoming tangent from TS, then R + ΔR to the inside
    cx = ts[0] + xm1 * math.sin(az_in) + d * p1 * math.cos(az_in)
    cy = ts[1] + xm1 * math.cos(az_in) - d * p1 * math.sin(az_in)
    return _Curve(
        vertex=name,
        turn=d,
        deflection=delta,
        radius=r,
        a1=a1,
        l1=l1,
        a2=a2,
        l2=l2,
        tau1=tau1,
        tau2=tau2,
        shift1=shift1,
        shift2=shift2,
        xm1=xm1,
        xm2=xm2,
        t1=t1,
        t2=t2,
        az_in=az_in,
        az_out=az_out,
        ts=ts,
        st=st,
        centre=(cx, cy),
        arc_angle=big - tau1 - tau2,
    )


def _check_vertices(vs: list[AlignmentVertex]) -> None:
    for i in range(len(vs) - 1):
        if math.hypot(vs[i + 1].x - vs[i].x, vs[i + 1].y - vs[i].y) < LENGTH_EPS:
            raise ValueError(f"Vertices {_label(vs[i], i)} and {_label(vs[i + 1], i + 1)} coincide")


def _tangent_lengths(
    vs: list[AlignmentVertex], curves: list[_Curve | None], sink: IssueSink
) -> list[float]:
    lengths = []
    for i in range(len(vs) - 1):
        side = math.hypot(vs[i + 1].x - vs[i].x, vs[i + 1].y - vs[i].y)
        c_prev, c_next = curves[i], curves[i + 1]
        before = c_prev.t2 if c_prev is not None else 0.0
        after = c_next.t1 if c_next is not None else 0.0
        free = side - before - after
        if free < -LENGTH_EPS:
            a, b = _label(vs[i], i), _label(vs[i + 1], i + 1)
            sink.error(
                "ALIGN_OVERLAP",
                f"The curves at {a} and {b} overlap by {-free:.3f} m",
                vertex_a=a,
                vertex_b=b,
                overlap=round(-free, 3),
            )
        lengths.append(max(free, 0.0))
    return lengths


def build(req: AlignmentRequest) -> _Geometry:
    """Element sequence, vertex table and main points. Errors are collected as issues; with any
    error the element list stays empty."""
    vs = req.vertices
    _check_vertices(vs)
    geo = _Geometry(start=req.start_chainage, end=req.start_chainage)
    curves: list[_Curve | None] = [None] * len(vs)
    for i in range(1, len(vs) - 1):
        curves[i] = _curve_at(vs, i, geo.issues)
    free = _tangent_lengths(vs, curves, geo.issues)
    if geo.errors:
        geo.vertex_rows = [_vertex_row(v, i, curves[i]) for i, v in enumerate(vs)]
        return geo

    lengths: list[float] = []

    def chain() -> float:
        return req.start_chainage + math.fsum(lengths)

    def push(e: _Elem) -> None:
        geo.elements.append(e)
        lengths.append(e.length)

    starts: dict[int, float] = {}
    ends: dict[int, float] = {}
    geo.main_points.append(("BP", _label(vs[0], 0), chain()))
    for i in range(len(vs) - 1):
        a = vs[i]
        c = curves[i]
        x0, y0 = c.st if c is not None else (a.x, a.y)
        if free[i] > 0.0:
            az = grid_azimuth(a.x, a.y, vs[i + 1].x, vs[i + 1].y)
            push(_Elem("tangent", chain(), free[i], x0, y0, az))
        nxt = curves[i + 1]
        if nxt is not None:
            starts[i + 1] = chain()
            _push_curve(nxt, chain, push, geo)
            ends[i + 1] = chain()
    geo.main_points.append(("EP", _label(vs[-1], len(vs) - 1), chain()))
    geo.end = chain()
    geo.vertex_rows = [
        _vertex_row(v, i, curves[i], starts.get(i), ends.get(i)) for i, v in enumerate(vs)
    ]
    return geo


def _push_curve(
    c: _Curve, chain: Callable[[], float], push: Callable[[_Elem], None], geo: _Geometry
) -> None:
    """Clothoid – arc – clothoid of one vertex, with their main points."""
    d, name = c.turn, c.vertex
    mp = geo.main_points
    mp.append(("TS" if c.l1 > 0 else "PC", name, chain()))
    if c.l1 > 0:
        push(
            _Elem(
                "clothoid", chain(), c.l1, c.ts[0], c.ts[1], c.az_in, d, c.radius, c.a1, True, name
            )
        )
        mp.append(("SC", name, chain()))
    arc_len = c.radius * c.arc_angle
    if c.l1 > 0:
        sx, sy, saz = geo.elements[-1].at(c.l1)
    else:
        sx, sy, saz = c.ts[0], c.ts[1], c.az_in
    if arc_len > 0.0:
        mp.append(("MC", name, chain() + arc_len / 2.0))
        push(_Elem("arc", chain(), arc_len, sx, sy, saz, d, c.radius, None, True, name))
    if c.l2 > 0:
        mp.append(("CS", name, chain()))
        push(
            _Elem(
                "clothoid",
                chain(),
                c.l2,
                c.st[0],
                c.st[1],
                c.az_out,
                d,
                c.radius,
                c.a2,
                False,
                name,
            )
        )
    mp.append(("ST" if c.l2 > 0 else "PT", name, chain()))


def _vertex_row(
    v: AlignmentVertex,
    i: int,
    c: _Curve | None,
    ch_start: float | None = None,
    ch_end: float | None = None,
) -> VertexRow:
    name = _label(v, i)
    if c is None:
        return VertexRow(name=name, x=v.x, y=v.y)
    arc_len = c.radius * c.arc_angle
    return VertexRow(
        name=name,
        x=v.x,
        y=v.y,
        deflection=c.deflection,
        radius=c.radius,
        a_in=c.a1,
        l_in=c.l1,
        a_out=c.a2,
        l_out=c.l2,
        tau_in=c.tau1,
        tau_out=c.tau2,
        shift_in=c.shift1,
        shift_out=c.shift2,
        xm_in=c.xm1,
        xm_out=c.xm2,
        t_in=c.t1,
        t_out=c.t2,
        arc_angle=c.arc_angle,
        arc_length=arc_len,
        curve_length=c.l1 + arc_len + c.l2,
        external=math.hypot(v.x - c.centre[0], v.y - c.centre[1]) - c.radius,
        centre_x=c.centre[0],
        centre_y=c.centre[1],
        chainage_start=ch_start,
        chainage_end=ch_end,
    )


# --------------------------------------------------------------------------- the axis


def _joined(errors: list[str], limit: int = 5) -> str:
    more = f" (+{len(errors) - limit} more)" if len(errors) > limit else ""
    return "; ".join(errors[:limit]) + more


class Axis:
    """A built alignment that answers point queries."""

    def __init__(self, req: AlignmentRequest) -> None:
        self.req = req
        self.geo = build(req)
        if self.geo.errors:
            raise ValueError(_joined(self.geo.errors))
        self.elements = self.geo.elements
        self.starts = [e.s0 for e in self.elements]
        # bounding discs: every point of an element is within L/2 of its middle point
        mids = [e.at(e.length / 2.0) for e in self.elements]
        self._mx = np.array([m[0] for m in mids])
        self._my = np.array([m[1] for m in mids])
        self._mr = np.array([e.length / 2.0 for e in self.elements])
        self.profile = Profile(req.profile) if req.profile is not None else None
        if self.profile is not None and self.profile.errors:
            raise ValueError(_joined(self.profile.errors))

    @property
    def start(self) -> float:
        return self.geo.start

    @property
    def end(self) -> float:
        return self.geo.end

    def _ends(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        first, last = self.elements[0], self.elements[-1]
        return first.at(0.0), last.at(last.length)

    def point_at(self, chainage: float, offset: float = 0.0) -> tuple[float, float, float, bool]:
        """(x, y, azimuth, inside) of the point at a chainage and right-positive offset.
        Chainages beyond the ends are extended along the end tangents (inside = False)."""
        (x0, y0, a0), (x1, y1, a1) = self._ends()
        if chainage < self.start - FOOT_TOL:
            s = chainage - self.start
            x, y, az, inside = x0 + s * math.sin(a0), y0 + s * math.cos(a0), a0, False
        elif chainage > self.end + FOOT_TOL:
            s = chainage - self.end
            x, y, az, inside = x1 + s * math.sin(a1), y1 + s * math.cos(a1), a1, False
        else:
            k = max(0, bisect.bisect_right(self.starts, chainage) - 1)
            e = self.elements[k]
            x, y, az = e.at(min(max(chainage - e.s0, 0.0), e.length))
            inside = True
        return x + offset * math.cos(az), y - offset * math.sin(az), az, inside

    def station_of(self, px: float, py: float) -> tuple[float, float, float, int | None, bool]:
        """(chainage, offset, azimuth, element, inside) of the perpendicular foot of P.
        Among several feet the nearest one wins; elements whose bounding disc is farther than
        the best foot so far are skipped."""
        lower = np.maximum(np.hypot(self._mx - px, self._my - py) - self._mr, 0.0)
        best: tuple[float, float, int] | None = None  # (|offset|, s, k)
        best_off = 0.0
        for k in np.argsort(lower, kind="stable"):
            k = int(k)
            if best is not None and lower[k] > best[0] + 1e-9:
                break
            e = self.elements[k]
            for s, off in e.feet(px, py):
                if -FOOT_TOL <= s <= e.length + FOOT_TOL and (best is None or abs(off) < best[0]):
                    best, best_off = (abs(off), min(max(s, 0.0), e.length), k), off
        if best is not None:
            _, s, k = best
            e = self.elements[k]
            return e.s0 + s, best_off, e.at(s)[2], k, True
        return self._extended(px, py)

    def _extended(self, px: float, py: float) -> tuple[float, float, float, int | None, bool]:
        """Foot on the extension of the first or last tangent direction (whichever is nearer)."""
        cands = []
        for (x, y, a), ref, before in zip(
            self._ends(), (self.start, self.end), (True, False), strict=True
        ):
            dx, dy = px - x, py - y
            s = dx * math.sin(a) + dy * math.cos(a)
            off = dx * math.cos(a) - dy * math.sin(a)
            beyond = min(s, 0.0) if before else max(s, 0.0)
            cands.append((math.hypot(beyond, off), ref + s, off, a))
        _, ch, off, az = min(cands)
        return ch, off, az, None, False


# ---------------------------------------------------------------------------- endpoints


def _polyline(elements: list[_Elem]) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for e in elements:
        if e.kind == "tangent":
            n = 1
        else:
            turn = (
                e.length / (e.radius or 1.0)
                if e.kind == "arc"
                else e.length / (2 * (e.radius or 1.0))
            )
            n = min(128, max(2, math.ceil(math.degrees(turn))))
        for i in range(0 if not pts else 1, n + 1):
            x, y, _ = e.at(e.length * i / n)
            pts.append((x, y))
    return pts


def _element_row(e: _Elem) -> AlignmentElement:
    x0, y0, a0 = e.at(0.0)
    x1, y1, a1 = e.at(e.length)
    return AlignmentElement(
        kind=e.kind,
        vertex=e.vertex,
        start_chainage=e.s0,
        end_chainage=e.s0 + e.length,
        length=e.length,
        start_x=x0,
        start_y=y0,
        end_x=x1,
        end_y=y1,
        start_azimuth=a0,
        end_azimuth=a1,
        radius=e.radius,
        a=e.a,
        turn=None if e.turn == 0 else ("right" if e.turn > 0 else "left"),
    )


def alignment(req: AlignmentRequest) -> AlignmentResult:
    """Element table, vertex table, main points and (optionally) the vertical profile."""
    geo = build(req)
    issues = list(geo.issues.items)
    prof = None
    profile_res = None
    if req.profile is not None:
        prof = Profile(req.profile)
        issues += prof.sink.items
        profile_res = prof.result() if not prof.errors else None
    if geo.errors:
        return AlignmentResult(
            vertices=geo.vertex_rows,
            elements=[],
            main_points=[],
            start_chainage=geo.start,
            end_chainage=geo.start,
            length=0.0,
            polyline=[(v.x, v.y) for v in req.vertices],
            profile=profile_res,
            issues=issues,
        )
    axis_pts = _AxisPoints(geo.elements, geo.start, geo.end)
    main = []
    for code, vertex, ch in geo.main_points:
        x, y, az = axis_pts.at(ch)
        z = prof.at(ch) if prof is not None and not prof.errors else None
        main.append(
            MainPoint(
                code=code, vertex=vertex, chainage=ch, x=x, y=y, azimuth=az, z=z[0] if z else None
            )
        )
    return AlignmentResult(
        vertices=geo.vertex_rows,
        elements=[_element_row(e) for e in geo.elements],
        main_points=main,
        start_chainage=geo.start,
        end_chainage=geo.end,
        length=geo.end - geo.start,
        polyline=_polyline(geo.elements),
        profile=profile_res,
        issues=issues,
    )


class _AxisPoints:
    def __init__(self, elements: list[_Elem], start: float, end: float) -> None:
        self.elements, self.start, self.end = elements, start, end
        self.starts = [e.s0 for e in elements]

    def at(self, ch: float) -> tuple[float, float, float]:
        k = min(max(bisect.bisect_right(self.starts, ch) - 1, 0), len(self.elements) - 1)
        e = self.elements[k]
        return e.at(min(max(ch - e.s0, 0.0), e.length))


def _z(axis: Axis, ch: float) -> float | None:
    if axis.profile is None:
        return None
    r = axis.profile.at(ch)
    return r[0] if r else None


def locate(req: LocateRequest) -> LocateResult:
    """(chainage, offset) ↔ (x, y) on a built alignment."""
    axis = Axis(req.alignment)
    stations = []
    for q in req.stations:
        x, y, az, inside = axis.point_at(q.chainage, q.offset)
        stations.append(
            StationRow(
                name=q.name,
                chainage=q.chainage,
                offset=q.offset,
                x=x,
                y=y,
                azimuth=az,
                z=_z(axis, q.chainage),
                inside=inside,
            )
        )
    points = []
    for p in req.points:
        ch, off, az, k, inside = axis.station_of(p.x, p.y)
        zd = _z(axis, ch)
        points.append(
            PointRow(
                name=p.name,
                x=p.x,
                y=p.y,
                chainage=ch,
                offset=off,
                azimuth=az,
                element=k,
                inside=inside,
                z_design=zd,
                dz=p.z - zd if p.z is not None and zd is not None else None,
            )
        )
    return LocateResult(stations=stations, points=points)


def stakeout(req: AlignmentStakeoutRequest) -> AlignmentStakeoutResult:
    """Points every ``interval`` metres of chainage (round chainages) plus all main points,
    each at the requested offsets (negative = left)."""
    axis = Axis(req.alignment)
    lo = axis.start if req.from_chainage is None else max(axis.start, req.from_chainage)
    hi = axis.end if req.to_chainage is None else min(axis.end, req.to_chainage)
    if lo > hi:
        raise ValueError("The chainage range does not overlap the alignment")
    step = req.interval
    k0, k1 = math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9)
    n_regular = max(0, k1 - k0 + 1)
    stations: dict[float, tuple[MainPointCode | None, str | None]] = {}
    if req.include_main_points:
        for code, vertex, ch in axis.geo.main_points:
            if lo - 1e-9 <= ch <= hi + 1e-9:
                stations[ch] = (code, vertex)
    if (n_regular + len(stations) + 2) * len(req.offsets) > MAX_STAKEOUT_ROWS:
        raise ValueError(
            f"Too many stakeout points (limit {MAX_STAKEOUT_ROWS:,}); increase the interval"
        )
    keys = sorted(stations)
    for ch in [lo, hi, *(k * step for k in range(k0, k1 + 1))]:
        j = bisect.bisect_left(keys, ch - 1e-6)
        if j < len(keys) and abs(keys[j] - ch) <= 1e-6:
            continue  # a main point already sits here
        stations.setdefault(ch, (None, None))
    offsets = sorted(set(req.offsets))
    rows = []
    for ch in sorted(stations):
        code, vertex = stations[ch]
        z = _z(axis, ch)
        for off in offsets:
            x, y, az, _ = axis.point_at(ch, off)
            rows.append(
                AlignmentStakeoutRow(
                    chainage=ch, offset=off, code=code, vertex=vertex, x=x, y=y, azimuth=az, z=z
                )
            )
    return AlignmentStakeoutResult(rows=rows)
