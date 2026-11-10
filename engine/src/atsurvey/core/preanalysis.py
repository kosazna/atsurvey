"""Network pre-analysis (προανάλυση, network design): precision and reliability of a PLANNED
network from approximate coordinates and a planned observation set — no measurements needed.

Model
-----
The functional model is the one of the least-squares adjustment (core/adjust.py): the same
design-matrix code (``_hz_linearise``, ``_h_design``), unknown layout (x, y per free point plus
one orientation per setup), datum (control points fixed), normal equations and singularity
check. With σ0 = 1 a priori:

* ``Qxx = (AᵀPA)⁻¹``; ``σx = √qxx``, ``σy = √qyy``, Helmert point error ``√(σx² + σy²)``.
* Absolute and relative standard ellipses from the 2×2 blocks of Qxx (relative: ``Q_Δ = Q_jj
  + Q_ii − Q_ij − Q_ji``); 95 % scaling ``k = √χ²₂(0.95) = √(−2 ln 0.05) = 2.4477``
  (Mikhail & Ackermann 1976, §4; Ghilani 2017, ch. 19).
* Redundancy numbers ``r_i = 1 − p_i·a_i Qxx a_iᵀ`` (Σr_i = n − u).
* Internal reliability (Baarda 1968): minimal detectable bias ``∇_i = δ0·σ_i/√r_i`` with
  ``δ0 = N⁻¹(1 − α0/2) + N⁻¹(β0)``; α0 = 0.1 %, β0 = 80 % give δ0 = 4.13, λ0 = δ0² = 17.07.
* External reliability: ``δ̄_i = δ0·√((1 − r_i)/r_i)`` and the actual effect of an undetected
  ∇_i on the coordinates, ``Δx̂ = Qxx a_iᵀ p_i ∇_i`` (largest point displacement reported).

Stochastic model (σ_ci, σ_ct centring of instrument and target, D the planned distance):
direction ``σ² = σ_r² + (σ_ci² + σ_ct²)/D²``; distance ``σ² = (a + b·D)² + σ_ci² + σ_ct²``;
height difference ``σ = max(σ_h·√(D km), 1 mm)`` as in the adjustment. Note: the adjustment
uses one centring value c with ``2c²/D²`` for directions but ``c²`` for distances; see
docs/analysis.md.

References: Baarda W. (1968) *A testing procedure for use in geodetic networks*, Netherlands
Geodetic Commission, Publ. on Geodesy 2(5); Kuang S. (1996) *Geodetic Network Analysis and
Optimal Design*; Ghilani C. (2017) *Adjustment Computations*, 6th ed.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from .adjust import (
    MAX_UNKNOWNS,
    MIN_REDUNDANCY,
    _assemble,
    _components,
    _ellipse,
    _h_design,
    _hz_columns,
    _hz_linearise,
    _Obs,
    _prune,
    _redundancy,
    _Singular,
    _solve,
)
from .issues import IssueSink
from .models import ErrorEllipse
from .preanalysis_models import (
    InstrumentSpec,
    ObservationReliability,
    PlannedObservation,
    PointPrecision,
    PreanalysisRequest,
    PreanalysisResult,
    RelativePrecision,
)
from .units import CC_TO_RAD

WEAK_REDUNDANCY = 0.3  # r below this: poorly controlled observation
K95 = math.sqrt(-2.0 * math.log(0.05))  # √χ²₂(0.95)
MIN_DISTANCE = 1e-3  # m
LISTED = 8  # observations named in an aggregated issue


def reliability_constants(alpha0: float, beta0: float) -> tuple[float, float]:
    """δ0 = N⁻¹(1 − α0/2) + N⁻¹(β0) and λ0 = δ0² (Baarda 1968)."""
    nd = NormalDist()
    delta0 = nd.inv_cdf(1.0 - alpha0 / 2.0) + nd.inv_cdf(beta0)
    return delta0, delta0 * delta0


def observation_sigma(kind: str, d: float, spec: InstrumentSpec) -> float:
    """A priori σ of a planned observation of length ``d`` (rad for directions, m otherwise)."""
    ci = spec.sigma_centering_instrument_mm / 1000.0
    ct = spec.sigma_centering_target_mm / 1000.0
    if kind == "direction":
        sr = spec.sigma_direction_cc * CC_TO_RAD
        return math.sqrt(sr * sr + (ci * ci + ct * ct) / (d * d))
    if kind == "distance":
        lin = spec.sigma_distance_mm / 1000.0 + spec.sigma_distance_ppm * 1e-6 * d
        return math.sqrt(lin * lin + ci * ci + ct * ct)
    return max(spec.sigma_height_mm * math.sqrt(d / 1000.0), 1.0) / 1000.0


def _scaled(e: ErrorEllipse) -> tuple[ErrorEllipse, float, float]:
    return e.model_copy(update={"k95": K95}), e.a * K95, e.b * K95


class _Net:
    """One solved (horizontal or height) sub-network: observations with their request rows,
    design rows, weights, cofactor matrix and unknown columns of the points."""

    def __init__(
        self,
        obs: list[_Obs],
        rows: list[int],
        design: tuple[np.ndarray, np.ndarray],
        p: np.ndarray,
        q: np.ndarray,
        cols: dict[str, int],
        two_d: bool,
    ) -> None:
        self.obs, self.rows, self.p, self.q, self.cols = obs, rows, p, q, cols
        self.idx, self.coef = design
        n = q.shape[0]
        self._qpad = np.zeros((n + 1, n + 1))  # pad column n matches the design's pad index
        self._qpad[:n, :n] = q
        self._names = list(cols)
        self._pc = np.array([cols[k] for k in self._names], dtype=np.int64)
        self._2d = two_d

    @property
    def n_unknowns(self) -> int:
        return self.q.shape[0]

    def shifts(self, k: int, bias: float) -> tuple[float, str]:
        """Largest point displacement from a bias in observation k: Δx̂ = Q a_kᵀ p_k ∇_k."""
        n = self.q.shape[0]
        dx = (self._qpad[:n, self.idx[k]] @ self.coef[k]) * (self.p[k] * bias)
        d = np.hypot(dx[self._pc], dx[self._pc + 1]) if self._2d else np.abs(dx[self._pc])
        if not len(d):
            return 0.0, ""
        j = int(np.argmax(d))
        return float(d[j]), self._names[j]


# --------------------------------------------------------------------------- validation


def _validate(req: PreanalysisRequest) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    for p in req.points:
        if p.name in coords:
            raise ValueError(f"Duplicate point name: {p.name}")
        coords[p.name] = (p.x, p.y)
    for i, o in enumerate(req.observations, 1):
        for name in (o.station, o.target):
            if name not in coords:
                raise ValueError(f"Observation {i}: unknown point {name}")
        if o.station == o.target:
            raise ValueError(f"Observation {i}: station and target are the same point")
        (xs, ys), (xt, yt) = coords[o.station], coords[o.target]
        if math.hypot(xt - xs, yt - ys) < MIN_DISTANCE:
            raise ValueError(f"Observation {i}: {o.station} and {o.target} coincide")
    for a, b in req.relative_pairs:
        if a not in coords or b not in coords:
            raise ValueError(f"Relative pair {a}–{b}: unknown point")
    return coords


def _setup_ids(observations: list[PlannedObservation]) -> list[int]:
    """Orientation group per observation: (station, setup label or station)."""
    ids: dict[tuple[str, str], int] = {}
    return [ids.setdefault((o.station, o.setup or o.station), len(ids)) for o in observations]


def _planned(
    req: PreanalysisRequest, coords: dict[str, tuple[float, float]], height: bool
) -> tuple[list[_Obs], list[int]]:
    """Planned observations of one sub-network as adjustment observations (value 0)."""
    setup_ids = _setup_ids(req.observations)
    obs: list[_Obs] = []
    rows: list[int] = []
    for i, o in enumerate(req.observations):
        if (o.kind == "height") != height:
            continue
        (xs, ys), (xt, yt) = coords[o.station], coords[o.target]
        sig = observation_sigma(o.kind, math.hypot(xt - xs, yt - ys), req.instrument)
        obs.append(_Obs(o.kind, setup_ids[i], o.station, o.target, 0.0, sig))
        rows.append(i)
    return obs, rows


# --------------------------------------------------------------------------- sub-networks


def _horizontal(
    req: PreanalysisRequest,
    coords: dict[str, tuple[float, float]],
    fixed: set[str],
    sink: IssueSink,
) -> tuple[_Net | None, list[str]]:
    obs, rows = _planned(req, coords, height=False)
    if not obs:
        return None, []
    free = {p.name for p in req.points if not p.fixed}
    row_of = {id(o): r for o, r in zip(obs, rows, strict=True)}
    free_h, obs, removed = _prune(free, obs)
    rows = [row_of[id(o)] for o in obs]
    if removed:
        sink.warning(
            "PREANALYSIS_UNDETERMINED",
            f"Not determined by the planned observations (fewer than two): {', '.join(removed)}",
            points=removed,
        )
    if not free_h:
        return None, removed
    fixed_in = {n for o in obs for n in (o.station, o.target) if n in fixed}
    if len(fixed_in) < 2:
        sink.error(
            "PREANALYSIS_DATUM",
            f"At least 2 control points must be connected to the network (found {len(fixed_in)})",
            dimension="horizontal",
            fixed=len(fixed_in),
        )
        return None, removed
    unknown = sorted(free_h)
    point_cols, ori_cols, _, n = _hz_columns(obs, unknown)
    if n > MAX_UNKNOWNS:
        raise ValueError(f"Network too large ({n} unknowns, limit {MAX_UNKNOWNS})")
    xy = {name: [x, y] for name, (x, y) in coords.items()}
    idx, coef, _, _ = _hz_linearise(obs, xy, dict.fromkeys(ori_cols, 0.0), point_cols, ori_cols, n)
    return _solve_net(obs, rows, (idx, coef), point_cols, n, "horizontal", sink), removed


def _heights(
    req: PreanalysisRequest,
    coords: dict[str, tuple[float, float]],
    fixed: set[str],
    sink: IssueSink,
) -> _Net | None:
    obs, rows = _planned(req, coords, height=True)
    if not obs:
        return None
    comp = _components([(o.station, o.target) for o in obs])
    anchored = {comp[n] for n in fixed if n in comp}
    keep = [k for k, o in enumerate(obs) if comp[o.station] in anchored]
    if len(keep) < len(obs):
        lost = sorted({n for o in obs for n in (o.station, o.target) if comp[n] not in anchored})
        sink.warning(
            "PREANALYSIS_DATUM",
            f"Heights of {', '.join(lost)} are not connected to a control point",
            dimension="height",
            fixed=0,
        )
    obs = [obs[k] for k in keep]
    rows = [rows[k] for k in keep]
    free_z = sorted({n for o in obs for n in (o.station, o.target) if n not in fixed})
    if not free_z:
        return None
    cols = {name: i for i, name in enumerate(free_z)}
    n = len(free_z)
    return _solve_net(obs, rows, _h_design(obs, cols, n), cols, n, "height", sink)


def _solve_net(
    obs: list[_Obs],
    rows: list[int],
    design: tuple[np.ndarray, np.ndarray],
    cols: dict[str, int],
    n: int,
    dim: str,
    sink: IssueSink,
) -> _Net | None:
    """Qxx = (AᵀPA)⁻¹ with the adjustment's solver, then the redundancy numbers."""
    idx, coef = design
    p = np.array([1.0 / (o.sigma * o.sigma) for o in obs])
    nmat, _ = _assemble(n, idx, coef, p, np.zeros(len(obs)))
    try:
        _, q = _solve(nmat, np.zeros(n), want_inverse=True)
    except _Singular:
        sink.error(
            "PREANALYSIS_SINGULAR",
            f"The planned {dim} network cannot be solved (datum defect or weak geometry, "
            "e.g. a point determined only by collinear observations)",
            dimension=dim,
        )
        return None
    assert q is not None
    for o, r in zip(obs, _redundancy(q, idx, coef, p), strict=True):
        o.redundancy = float(r)
    return _Net(obs, rows, design, p, q, cols, dim == "horizontal")


# --------------------------------------------------------------------------- results


def _reliability(net: _Net, k: int, delta0: float) -> ObservationReliability:
    o = net.obs[k]
    r = o.redundancy
    base = {"kind": o.kind, "station": o.station, "target": o.target, "sigma": o.sigma}
    if r < MIN_REDUNDANCY:
        return ObservationReliability(
            **base,
            redundancy=r,
            mdb=None,
            external=None,
            max_shift=None,
            max_shift_point=None,
            status="uncontrolled",
        )
    mdb = delta0 * o.sigma / math.sqrt(r)
    shift, point = net.shifts(k, mdb)
    return ObservationReliability(
        **base,
        redundancy=r,
        mdb=mdb,
        external=delta0 * math.sqrt((1.0 - r) / r),
        max_shift=shift,
        max_shift_point=point or None,
        status="weak" if r < WEAK_REDUNDANCY else "ok",
    )


def _points(hz: _Net | None, h: _Net | None) -> list[PointPrecision]:
    names = sorted(set(hz.cols if hz else ()) | set(h.cols if h else ()))
    out: list[PointPrecision] = []
    for name in names:
        sz = (
            math.sqrt(max(float(h.q[h.cols[name], h.cols[name]]), 0.0))
            if h and name in h.cols
            else None
        )
        if hz is None or name not in hz.cols:
            out.append(PointPrecision(name=name, sz=sz))
            continue
        c = hz.cols[name]
        qxx, qyy, qxy = float(hz.q[c, c]), float(hz.q[c + 1, c + 1]), float(hz.q[c, c + 1])
        sx, sy = math.sqrt(max(qxx, 0.0)), math.sqrt(max(qyy, 0.0))
        ell, a95, b95 = _scaled(_ellipse(qxx, qyy, qxy, 1.0))
        out.append(
            PointPrecision(
                name=name,
                sx=sx,
                sy=sy,
                spos=math.hypot(sx, sy),
                ellipse=ell,
                a95=a95,
                b95=b95,
                sz=sz,
            )
        )
    return out


def _block(q: np.ndarray, ca: int | None, cb: int | None) -> np.ndarray:
    """2×2 cofactor block between points a and b (zero for a fixed point)."""
    if ca is None or cb is None:
        return np.zeros((2, 2))
    return q[ca : ca + 2, cb : cb + 2]


def _relative(
    pairs: list[tuple[str, str]],
    coords: dict[str, tuple[float, float]],
    fixed: set[str],
    hz: _Net | None,
) -> list[RelativePrecision]:
    """Relative ellipses: Q_Δ = Q_bb + Q_aa − Q_ab − Q_ba (Ghilani 2017, §19.6)."""
    if hz is None:
        return []
    out: list[RelativePrecision] = []
    seen: set[frozenset[str]] = set()
    for a, b in pairs:
        key = frozenset((a, b))
        ca, cb = hz.cols.get(a), hz.cols.get(b)
        if a == b or key in seen or (ca is None and cb is None):
            continue
        if (ca is None and a not in fixed) or (cb is None and b not in fixed):
            continue  # a point that is not part of the solved network
        seen.add(key)
        qd = (
            _block(hz.q, cb, cb)
            + _block(hz.q, ca, ca)
            - _block(hz.q, ca, cb)
            - _block(hz.q, cb, ca)
        )
        (xa, ya), (xb, yb) = coords[a], coords[b]
        dx, dy = xb - xa, yb - ya
        d = math.hypot(dx, dy)
        gd = np.array([dx / d, dy / d])
        ga = np.array([dy / (d * d), -dx / (d * d)])  # ∂α/∂(Δx, Δy), α = atan2(Δx, Δy)
        s_az = math.sqrt(max(float(ga @ qd @ ga), 0.0))
        ell, a95, b95 = _scaled(_ellipse(float(qd[0, 0]), float(qd[1, 1]), float(qd[0, 1]), 1.0))
        out.append(
            RelativePrecision(
                frm=a,
                to=b,
                distance=d,
                s_distance=math.sqrt(max(float(gd @ qd @ gd), 0.0)),
                s_azimuth=s_az,
                s_transverse=d * s_az,
                ellipse=ell,
                a95=a95,
                b95=b95,
            )
        )
    return out


def _flag(rel: list[ObservationReliability], sink: IssueSink) -> None:
    def names(status: str) -> list[str]:
        return [f"{o.kind} {o.station}→{o.target}" for o in rel if o.status == status]

    unc = names("uncontrolled")
    if unc:
        sink.warning(
            "PREANALYSIS_UNCONTROLLED",
            f"{len(unc)} observation(s) are not controlled (r ≈ 0): a blunder in them cannot be "
            f"detected — {', '.join(unc[:LISTED])}",
            count=len(unc),
            observations=", ".join(unc[:LISTED]),
        )
    weak = names("weak")
    if weak:
        sink.warning(
            "PREANALYSIS_WEAK",
            f"{len(weak)} observation(s) are weakly controlled (r < {WEAK_REDUNDANCY}): "
            f"{', '.join(weak[:LISTED])}",
            count=len(weak),
            threshold=WEAK_REDUNDANCY,
            observations=", ".join(weak[:LISTED]),
        )


def preanalyse(req: PreanalysisRequest) -> PreanalysisResult:
    """Precision and reliability of the planned network (σ0 = 1 a priori)."""
    coords = _validate(req)
    fixed = {p.name for p in req.points if p.fixed}
    sink = IssueSink()
    delta0, lambda0 = reliability_constants(req.alpha0, req.beta0)
    hz, removed = _horizontal(req, coords, fixed, sink)
    h = _heights(req, coords, fixed, sink)

    rel = [
        ObservationReliability(
            kind=o.kind,
            station=o.station,
            target=o.target,
            sigma=None,
            redundancy=0.0,
            mdb=None,
            external=None,
            max_shift=None,
            max_shift_point=None,
            status="excluded",
        )
        for o in req.observations
    ]
    nets = [net for net in (hz, h) if net is not None]
    for net in nets:
        for k, row in enumerate(net.rows):
            rel[row] = _reliability(net, k, delta0)
    _flag(rel, sink)
    n_obs = sum(len(net.obs) for net in nets)
    n_unk = sum(net.n_unknowns for net in nets)
    return PreanalysisResult(
        n_observations=n_obs,
        n_unknowns=n_unk,
        dof=n_obs - n_unk,
        alpha0=req.alpha0,
        beta0=req.beta0,
        delta0=delta0,
        lambda0=lambda0,
        k95=K95,
        points=_points(hz, h),
        relative=_relative(req.relative_pairs, coords, fixed, hz),
        observations=rel,
        excluded_points=removed,
        issues=sink.items,
    )


__all__ = ["observation_sigma", "preanalyse", "reliability_constants"]
