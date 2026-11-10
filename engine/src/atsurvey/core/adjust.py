"""Least-squares network adjustment.

Contract
--------
``adjust_network`` is called after the traverses (whose coordinates serve as approximate
values) and before the detail points. It adjusts every *network point* — points that are not
control points and that are occupied stations or traverse points — using all reduced
directions, distances and height differences between network points and control points.
It updates ``known`` in place (x, y, z, sx, sy, sz, ellipse) and returns the adjustment
summary, or ``None`` when there is nothing to adjust (the reason is reported as an issue).

Model
-----
* Horizontal (Gauss–Newton, iterated): unknowns are (x, y) of every free point and one
  orientation unknown ω per setup. Direction r from i to j: ``r = α(i→j) − ω``. Grid
  distance: ``D = √(Δx² + Δy²)``; measured horizontal distances are reduced to the grid with
  the project's ReductionSettings (height factor per line, EGSA87 line scale).
* Heights (linear): ``h_j − h_i = Δh`` with the reduced trigonometric height differences.
* Datum: control points are fixed (minimum constraints are not used).
* Statistics: σ0, global χ² test, redundancy numbers, Baarda w-test (data snooping), point
  standard deviations and standard error ellipses.
* Optional robust estimation (``settings.robust``): iteratively re-weighted least squares on the
  standardised residuals with the Huber or the Danish weight function (off by default; with it
  off the computation is exactly the plain least-squares adjustment).
The design-matrix code (``_hz_linearise``, ``_h_design``) and the normal-equation helpers are
shared with the pre-analysis (core/preanalysis.py), so both use the identical functional model.
See docs/adjustment.md and docs/analysis.md.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np

from .geodesy import (
    egsa87_point_scale,
    elevation_factor,
    grid_azimuth,
    scale_for_line,
)
from .issues import IssueSink
from .models import (
    AdjustedObservation,
    AdjustmentResult,
    AdjustmentSettings,
    ErrorEllipse,
    GlobalTest,
    ObservationKind,
    ReductionSettings,
    RobustMethod,
    RobustSummary,
)
from .reduce import ObservationIndex, ReducedSetup
from .traverse import KnownPoint
from .units import CC_TO_RAD, circular_mean, wrap_2pi, wrap_pi

MAX_UNKNOWNS = 4000
CONVERGENCE_M = 5e-5  # 0.05 mm
MIN_REDUNDANCY = 0.01
K95_2D = 2.4477
ROBUST_TOLERANCE = 1e-3  # IRLS stops when no weight factor changes by more than this
ROBUST_MIN_WEIGHT = 1e-4  # floor of the weight factor (σ inflated at most 100×)
DOWNWEIGHTED = 0.99  # weight factors below this are reported as down-weighted


@dataclass(slots=True)
class _Obs:
    kind: ObservationKind
    setup: int  # ReducedSetup.index (orientation group) — directions only
    station: str
    target: str
    value: float  # direction (rad), grid distance (m) or Δh (m)
    sigma: float
    # filled after the adjustment
    adjusted: float = 0.0
    residual: float = 0.0
    redundancy: float = 0.0
    w: float | None = None
    flagged: bool = False
    weight: float = 1.0  # robust weight factor (multiplies 1/σ²)


@dataclass(slots=True)
class _Solution:
    """Result of one (horizontal or height) sub-adjustment."""

    obs: list[_Obs]
    n_unknowns: int
    vtpv: float
    q: np.ndarray  # cofactor matrix of the point unknowns (orientations removed)
    point_cols: dict[str, int]
    values: dict[str, tuple[float, ...]] = field(default_factory=dict)
    iterations: int = 1
    converged: bool = True


class _Singular(Exception):
    pass


# --------------------------------------------------------------------------- linear algebra


def _assemble(
    n: int, idx: np.ndarray, coef: np.ndarray, p: np.ndarray, rhs: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Normal equations from sparse rows padded to a fixed width (pad index = n)."""
    nbig = np.zeros((n + 1, n + 1))
    ubig = np.zeros(n + 1)
    w = p[:, None, None] * coef[:, :, None] * coef[:, None, :]
    np.add.at(nbig, (idx[:, :, None], idx[:, None, :]), w)
    np.add.at(ubig, idx, p[:, None] * coef * rhs[:, None])
    return nbig[:n, :n], ubig[:n]


def _solve(
    nmat: np.ndarray, u: np.ndarray, want_inverse: bool
) -> tuple[np.ndarray, np.ndarray | None]:
    """Solve N δ = u with a Jacobi-scaled Cholesky check for singularity (datum defects)."""
    d = np.sqrt(np.diag(nmat))
    if not np.all(np.isfinite(d)) or np.any(d <= 0):
        raise _Singular
    ns = nmat / np.outer(d, d)
    try:
        lchol = np.linalg.cholesky(ns)
    except np.linalg.LinAlgError as exc:
        raise _Singular from exc
    if float(np.min(np.diag(lchol))) ** 2 < 1e-12:
        raise _Singular
    delta = np.linalg.solve(ns, u / d) / d
    q = None
    if want_inverse:
        inv = np.linalg.inv(lchol)
        q = (inv.T @ inv) / np.outer(d, d)
    return delta, q


def _redundancy(q: np.ndarray, idx: np.ndarray, coef: np.ndarray, p: np.ndarray) -> np.ndarray:
    n = q.shape[0]
    qbig = np.zeros((n + 1, n + 1))
    qbig[:n, :n] = q
    sub = qbig[idx[:, :, None], idx[:, None, :]]
    aqa = np.einsum("ma,mab,mb->m", coef, sub, coef)
    return np.clip(1.0 - p * aqa, 0.0, 1.0)


def _chi2_ppf(prob: float, k: int) -> float:
    """χ² quantile (Wilson–Hilferty approximation; accurate to <1 % for k ≥ 3)."""
    z = NormalDist().inv_cdf(prob)
    c = 2.0 / (9.0 * k)
    return max(0.0, k * (1.0 - c + z * math.sqrt(c)) ** 3)


def _ellipse(qxx: float, qyy: float, qxy: float, s2: float) -> ErrorEllipse:
    half = (qxx + qyy) / 2.0
    rad = math.hypot((qxx - qyy) / 2.0, qxy)
    l1 = (half + rad) * s2
    l2 = max(half - rad, 0.0) * s2
    theta = 0.5 * math.atan2(2.0 * qxy, qyy - qxx)  # azimuth (from north) of the major axis
    theta = math.fmod(theta, math.pi)
    if theta < 0:
        theta += math.pi
    if theta >= math.pi:
        theta = 0.0
    return ErrorEllipse(a=math.sqrt(l1), b=math.sqrt(l2), theta=theta, k95=K95_2D)


# ---------------------------------------------------------------------- observation setup


def _grid_distance(
    hd: float, st: KnownPoint, tg: KnownPoint, dh: float | None, rs: ReductionSettings
) -> float:
    if st.z is not None and tg.z is not None:
        hm = (st.z + tg.z) / 2.0
    elif st.z is not None and dh is not None:
        hm = st.z + dh / 2.0
    elif st.z is not None:
        hm = st.z
    else:
        hm = rs.default_elevation
    k = scale_for_line(rs, st.x, tg.x, egsa87_point_scale((st.x + tg.x) / 2.0))
    return hd * elevation_factor(rs, hm) * k


def _prune(unknown: set[str], obs: list[_Obs]) -> tuple[set[str], list[_Obs], list[str]]:
    """Drop free points that cannot be determined (fewer than two effective observations)."""
    removed: list[str] = []
    while True:
        count = dict.fromkeys(unknown, 0)
        ndir: dict[int, int] = {}
        station_of: dict[int, str] = {}
        for o in obs:
            if o.kind == "direction":
                ndir[o.setup] = ndir.get(o.setup, 0) + 1
                station_of[o.setup] = o.station
                if o.target in count:
                    count[o.target] += 1
            else:  # distance
                for p in (o.station, o.target):
                    if p in count:
                        count[p] += 1
        for s, k in ndir.items():
            st = station_of[s]
            if st in count:
                count[st] += max(k - 1, 0)
        bad = {p for p, c in count.items() if c < 2}
        if not bad:
            return unknown, obs, removed
        removed.extend(sorted(bad))
        unknown = unknown - bad
        obs = [o for o in obs if o.station not in bad and o.target not in bad]


# ------------------------------------------------------------------------------ horizontal


def _hz_linearise(
    obs: list[_Obs],
    coords: dict[str, list[float]],
    omega: dict[int, float],
    point_cols: dict[str, int],
    ori_cols: dict[int, int],
    n: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Linearised horizontal model at ``coords``: design rows, misclosures and model values.

    Each row has at most 5 non-zero coefficients (x, y of target and station, orientation),
    stored as column indices ``idx`` (pad = n) and values ``coef``. Direction (Ghilani 2017,
    §16.4): ``∂r/∂x_t = Δy/D²``, ``∂r/∂y_t = −Δx/D²``, ``∂r/∂ω = −1``; distance (§16.3):
    ``∂D/∂x_t = Δx/D``, ``∂D/∂y_t = Δy/D``; the station takes the opposite signs.
    ``rhs`` = observed − model (directions wrapped to (−π, π]).
    """
    m = len(obs)
    idx = np.full((m, 5), n, dtype=np.int64)
    coef = np.zeros((m, 5))
    model = np.zeros(m)
    for r, o in enumerate(obs):
        xs, ys = coords[o.station]
        xt, yt = coords[o.target]
        dx, dy = xt - xs, yt - ys
        d2 = dx * dx + dy * dy
        d = math.sqrt(d2)
        k = 0
        if o.kind == "direction":
            model[r] = wrap_2pi(grid_azimuth(xs, ys, xt, yt) - omega[o.setup])
            parts = ((o.target, dy / d2, -dx / d2), (o.station, -dy / d2, dx / d2))
            idx[r, 4] = ori_cols[o.setup]
            coef[r, 4] = -1.0
        else:
            model[r] = d
            parts = ((o.target, dx / d, dy / d), (o.station, -dx / d, -dy / d))
        for name, cx, cy in parts:
            col = point_cols.get(name)
            if col is not None:
                idx[r, k], coef[r, k] = col, cx
                idx[r, k + 1], coef[r, k + 1] = col + 1, cy
            k += 2
    obs_v = np.array([o.value for o in obs])
    rhs = obs_v - model
    dirs = np.array([o.kind == "direction" for o in obs])
    rhs[dirs] = (rhs[dirs] + math.pi) % (2 * math.pi) - math.pi
    return idx, coef, rhs, model


def _hz_columns(
    obs: list[_Obs], unknown: list[str]
) -> tuple[dict[str, int], dict[int, int], int, int]:
    """Unknown layout: (x, y) per free point, then one orientation per setup with directions."""
    point_cols = {p: 2 * i for i, p in enumerate(unknown)}
    setups = sorted({o.setup for o in obs if o.kind == "direction"})
    n_pts = 2 * len(unknown)
    ori_cols = {s: n_pts + j for j, s in enumerate(setups)}
    return point_cols, ori_cols, n_pts, n_pts + len(setups)


def _horizontal(
    obs: list[_Obs],
    unknown: list[str],
    coords: dict[str, list[float]],
    settings: AdjustmentSettings,
    weights: np.ndarray | None = None,
) -> _Solution:
    point_cols, ori_cols, n_pts, n = _hz_columns(obs, unknown)

    # initial orientation unknowns
    omega: dict[int, float] = {}
    by_setup: dict[int, list[float]] = {}
    for o in obs:
        if o.kind == "direction":
            xs, ys = coords[o.station]
            xt, yt = coords[o.target]
            by_setup.setdefault(o.setup, []).append(
                wrap_2pi(grid_azimuth(xs, ys, xt, yt) - o.value)
            )
    for s, vals in by_setup.items():
        omega[s] = circular_mean(vals)

    p = np.array([1.0 / (o.sigma * o.sigma) for o in obs])
    if weights is not None:
        p = p * weights

    def linearise() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return _hz_linearise(obs, coords, omega, point_cols, ori_cols, n)

    converged = False
    iterations = 0
    for it in range(1, settings.max_iterations + 1):
        iterations = it
        idx, coef, rhs, _ = linearise()
        nmat, u = _assemble(n, idx, coef, p, rhs)
        delta, _ = _solve(nmat, u, want_inverse=False)
        if not np.all(np.isfinite(delta)):
            raise _Singular
        for name, col in point_cols.items():
            coords[name][0] += float(delta[col])
            coords[name][1] += float(delta[col + 1])
        for s, col in ori_cols.items():
            omega[s] = wrap_2pi(omega[s] + float(delta[col]))
        max_corr = float(np.max(np.abs(delta[:n_pts]))) if n_pts else 0.0
        if max_corr > 1e5:
            raise _Singular
        if max_corr < CONVERGENCE_M:
            converged = True
            break

    # statistics at the final point
    idx, coef, rhs, model = linearise()
    nmat, _ = _assemble(n, idx, coef, p, rhs)
    _, q = _solve(nmat, np.zeros(n), want_inverse=True)
    assert q is not None
    v = -rhs  # residual = adjusted − observed (rhs = observed − model)
    red = _redundancy(q, idx, coef, p)
    for r, o in enumerate(obs):
        o.adjusted = float(model[r])
        o.residual = float(v[r])
        o.redundancy = float(red[r])
    sol = _Solution(
        obs=obs,
        n_unknowns=n,
        vtpv=float(np.sum(p * v * v)),
        q=q[:n_pts, :n_pts],
        point_cols=point_cols,
        iterations=iterations,
        converged=converged,
    )
    sol.values = {name: (coords[name][0], coords[name][1]) for name in unknown}
    return sol


# ---------------------------------------------------------------------------------- heights


def _h_design(obs: list[_Obs], cols: dict[str, int], n: int) -> tuple[np.ndarray, np.ndarray]:
    """Design rows of ``h_j − h_i = Δh``: +1 for the target, −1 for the station (pad = n)."""
    m = len(obs)
    idx = np.full((m, 2), n, dtype=np.int64)
    coef = np.zeros((m, 2))
    for r, o in enumerate(obs):
        if o.target in cols:
            idx[r, 0], coef[r, 0] = cols[o.target], 1.0
        if o.station in cols:
            idx[r, 1], coef[r, 1] = cols[o.station], -1.0
    return idx, coef


def _heights(
    obs: list[_Obs],
    unknown: list[str],
    fixed_h: dict[str, float],
    approx: dict[str, float],
    weights: np.ndarray | None = None,
) -> _Solution:
    cols = {name: i for i, name in enumerate(unknown)}
    n = len(unknown)
    m = len(obs)
    rhs = np.zeros(m)
    p = np.array([1.0 / (o.sigma * o.sigma) for o in obs])
    if weights is not None:
        p = p * weights

    def h0(name: str) -> float:
        return fixed_h[name] if name in fixed_h else approx.get(name, 0.0)

    idx, coef = _h_design(obs, cols, n)
    for r, o in enumerate(obs):
        rhs[r] = o.value - (h0(o.target) - h0(o.station))
    nmat, u = _assemble(n, idx, coef, p, rhs)
    delta, q = _solve(nmat, u, want_inverse=True)
    assert q is not None
    h = {name: h0(name) + float(delta[cols[name]]) for name in unknown}

    def hh(name: str) -> float:
        return fixed_h[name] if name in fixed_h else h[name]

    v = np.zeros(m)
    for r, o in enumerate(obs):
        o.adjusted = hh(o.target) - hh(o.station)
        o.residual = o.adjusted - o.value
        v[r] = o.residual
    red = _redundancy(q, idx, coef, p)
    for r, o in enumerate(obs):
        o.redundancy = float(red[r])
    sol = _Solution(obs=obs, n_unknowns=n, vtpv=float(np.sum(p * v * v)), q=q, point_cols=cols)
    sol.values = {name: (h[name],) for name in unknown}
    return sol


# ---------------------------------------------------------------------- robust estimation


def robust_weight(u: float, method: RobustMethod, c: float) -> float:
    """Weight factor for a standardised residual ``u`` (IRLS, Huber 1964 / Danish method).

    * Huber: ``1`` for ``|u| ≤ c``, ``c/|u|`` beyond (Huber 1964; Koch 1999, §3.8).
    * Danish (Krarup, Juhl & Kubik 1980), smooth exponential form:
      ``1`` for ``|u| ≤ c``, ``exp(1 − (|u|/c)²)`` beyond (continuous at ``c``).
    Floored at ``ROBUST_MIN_WEIGHT`` so the normal matrix stays regular.
    """
    a = abs(u)
    if method == "off" or a <= c:
        return 1.0
    w = c / a if method == "huber" else math.exp(1.0 - (a / c) ** 2)
    return max(w, ROBUST_MIN_WEIGHT)


def _standardised(obs: list[_Obs]) -> list[float]:
    """``ū_i = v_i / (σ_i √r_i)`` with the a priori σ and the current redundancy numbers;
    observations without control (r < MIN_REDUNDANCY) get 0 (they cannot be judged)."""
    return [
        o.residual / (o.sigma * math.sqrt(o.redundancy)) if o.redundancy >= MIN_REDUNDANCY else 0.0
        for o in obs
    ]


def _irls(
    solve: Callable[[np.ndarray | None], _Solution], obs: list[_Obs], settings: AdjustmentSettings
) -> tuple[_Solution, int, bool]:
    """Iteratively re-weighted least squares. With ``robust = "off"`` this is exactly one plain
    solve. Otherwise: solve, compute standardised residuals, new weight factors
    ``w_i = ψ(ū_i)``, re-solve with ``p_i·w_i``; stop when no factor changes by more than
    ``ROBUST_TOLERANCE`` or after ``robust_max_iterations`` re-weightings.

    The Danish weight function is redescending, so it needs a robust start: a gross error
    smeared by the first least-squares solution would otherwise also switch off the good
    observations around it. It therefore starts from the converged Huber weights (Huber is
    convex, its solution unique) and continues with the Danish function (Koch 1999, §3.8.3;
    Wicki 1998). Returns the solution (weights stored on the observations), the number of
    re-weightings and whether the weights converged."""
    if settings.robust == "off":
        return solve(None), 0, True
    wts = np.ones(len(obs))
    sol = solve(wts)
    phase: RobustMethod = "huber"
    converged = False
    rounds = 0
    while rounds < settings.robust_max_iterations:
        rounds += 1
        u = _standardised(obs)
        new = np.array([robust_weight(x, phase, settings.robust_threshold) for x in u])
        if float(np.max(np.abs(new - wts), initial=0.0)) < ROBUST_TOLERANCE:
            if phase == settings.robust:
                converged = True
                break
            phase = settings.robust  # Huber settled: switch to the Danish function
            new = np.array([robust_weight(x, phase, settings.robust_threshold) for x in u])
        try:
            nxt = solve(new)
        except _Singular:
            break  # keep the last regular solution and its weights
        sol, wts = nxt, new
    for o, w in zip(obs, wts, strict=True):
        o.weight = float(w)
    return sol, rounds, converged


def _components(edges: list[tuple[str, str]]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(a: str) -> str:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return {k: find(k) for k in list(parent)}


# -------------------------------------------------------------------------------- entry point


def adjust_network(
    setups: list[ReducedSetup],
    index: ObservationIndex,
    known: dict[str, KnownPoint],
    fixed: set[str],
    rs: ReductionSettings,
    settings: AdjustmentSettings,
    sink: IssueSink,
) -> AdjustmentResult | None:
    candidates = (
        set(index.by_station) | {n for n, kp in known.items() if kp.kind == "traverse"}
    ) - fixed
    for name in sorted(candidates - set(known)):
        sink.info(
            "ADJUSTMENT_EXCLUDED_POINT",
            f"{name} was left out of the adjustment (no approximate coordinates)",
            point=name,
        )
    free = {name for name in candidates if name in known}
    net = free | {name for name in fixed if name in known}
    if not free:
        sink.info(
            "ADJUSTMENT_NO_REDUNDANCY",
            "Nothing to adjust: no free points in the network",
            dof=0,
        )
        return None

    sd_dir = settings.sigma_direction_cc * CC_TO_RAD
    c = settings.sigma_centering_mm / 1000.0
    hz_obs: list[_Obs] = []
    h_obs: list[_Obs] = []
    for s in setups:
        if s.station not in net:
            continue
        st = known[s.station]
        for name in s.order:
            t = s.targets[name]
            if name == s.station or name not in net:
                continue
            tg = known[name]
            d_approx = max(math.hypot(tg.x - st.x, tg.y - st.y), 1e-3)
            sig = math.sqrt(sd_dir * sd_dir + 2.0 * (c / d_approx) ** 2)
            hz_obs.append(_Obs("direction", s.index, s.station, name, t.direction, sig))
            if t.hd is not None and t.hd > 0:
                dg = _grid_distance(t.hd, st, tg, t.dh, rs)
                sd = math.hypot(
                    settings.sigma_distance_mm / 1000.0 + settings.sigma_distance_ppm * 1e-6 * dg, c
                )
                hz_obs.append(_Obs("distance", s.index, s.station, name, dg, sd))
            if t.dh is not None and t.hd is not None:
                sh = max(settings.sigma_height_mm * math.sqrt(t.hd / 1000.0), 1.0) / 1000.0
                h_obs.append(_Obs("height", s.index, s.station, name, t.dh, sh))

    # ---- horizontal network --------------------------------------------------------------
    free_h, hz_obs, removed = _prune(set(free), hz_obs)
    for name in removed:
        sink.info(
            "ADJUSTMENT_EXCLUDED_POINT",
            f"{name} was left out of the adjustment (not enough observations)",
            point=name,
        )
    fixed_in_hz = {o.station for o in hz_obs if o.station in fixed} | {
        o.target for o in hz_obs if o.target in fixed
    }
    hz_sol: _Solution | None = None
    robust_runs: list[tuple[int, bool]] = []
    if free_h:
        if len(fixed_in_hz) < 2:
            sink.error(
                "ADJUSTMENT_DATUM",
                f"Least squares needs at least 2 control points connected to the network "
                f"(found {len(fixed_in_hz)}); the traverse solution is kept",
                dimension="horizontal",
                fixed=len(fixed_in_hz),
            )
            return None
        n_unk = 2 * len(free_h) + len({o.setup for o in hz_obs if o.kind == "direction"})
        if n_unk > MAX_UNKNOWNS:
            sink.warning(
                "ADJUSTMENT_TOO_LARGE",
                f"Network too large for the adjustment ({n_unk} unknowns, limit {MAX_UNKNOWNS})",
                n=n_unk,
                limit=MAX_UNKNOWNS,
            )
            return None
        coords = {name: [known[name].x, known[name].y] for name in net}
        try:
            free_list = sorted(free_h)
            hz_sol, hz_rw, hz_rconv = _irls(
                lambda w: _horizontal(hz_obs, free_list, coords, settings, w), hz_obs, settings
            )
            robust_runs.append((hz_rw, hz_rconv))
        except _Singular:
            sink.error(
                "ADJUSTMENT_DATUM",
                "The network cannot be solved (datum defect or weak geometry); the traverse "
                "solution is kept",
                dimension="horizontal",
                fixed=len(fixed_in_hz),
            )
            return None
        if not hz_sol.converged:
            sink.warning(
                "ADJUSTMENT_NOT_CONVERGED",
                f"The adjustment did not converge in {hz_sol.iterations} iterations",
                iterations=hz_sol.iterations,
            )

    # ---- height network ------------------------------------------------------------------
    fixed_h = {n: known[n].z for n in fixed if n in known and known[n].z is not None}
    h_obs = [
        o
        for o in h_obs
        if (o.station in fixed_h or o.station in free) and (o.target in fixed_h or o.target in free)
    ]
    h_sol: _Solution | None = None
    if h_obs:
        comp = _components([(o.station, o.target) for o in h_obs])
        anchored = {comp[n] for n in fixed_h if n in comp}
        h_obs = [o for o in h_obs if comp[o.station] in anchored]
        if not anchored:
            sink.warning(
                "ADJUSTMENT_DATUM",
                "Heights not adjusted: no control point with a height is connected",
                dimension="height",
                fixed=0,
            )
        free_z = sorted({n for o in h_obs for n in (o.station, o.target) if n not in fixed_h})
        if free_z:
            approx = {n: known[n].z for n in free_z if known[n].z is not None}
            try:
                h_sol, h_rw, h_rconv = _irls(
                    lambda w: _heights(h_obs, free_z, fixed_h, approx, w),  # type: ignore[arg-type]
                    h_obs,
                    settings,
                )
                robust_runs.append((h_rw, h_rconv))
            except _Singular:
                sink.warning(
                    "ADJUSTMENT_DATUM",
                    "Heights could not be adjusted (singular height network)",
                    dimension="height",
                    fixed=len(anchored),
                )

    sols = [s for s in (hz_sol, h_sol) if s is not None]
    if not sols:
        sink.info("ADJUSTMENT_NO_REDUNDANCY", "Nothing to adjust", dof=0)
        return None

    # ---- statistics ----------------------------------------------------------------------
    all_obs = [o for s in sols for o in s.obs]
    n_obs = len(all_obs)
    n_unk = sum(s.n_unknowns for s in sols)
    dof = n_obs - n_unk
    vtpv = sum(s.vtpv for s in sols)
    w_crit = NormalDist().inv_cdf(1.0 - settings.alpha_w / 2.0)
    global_test: GlobalTest | None = None
    if dof > 0:
        sigma0 = math.sqrt(vtpv / dof)
        lower = _chi2_ppf(settings.alpha_global / 2.0, dof)
        upper = _chi2_ppf(1.0 - settings.alpha_global / 2.0, dof)
        global_test = GlobalTest(
            statistic=vtpv, lower=lower, upper=upper, passed=lower <= vtpv <= upper
        )
        if vtpv > upper:
            # observations fit worse than their stated precision: blunders or optimistic σ
            sink.warning(
                "ADJUSTMENT_GLOBAL_TEST",
                f"Global test failed: σ0 = {sigma0:.3f} with {dof} degrees of freedom "
                f"(a priori σ0 = 1); check the a priori precisions or look for blunders",
                sigma0=round(sigma0, 3),
                dof=dof,
            )
        elif vtpv < lower:
            # observations fit better than stated: the a priori σ are conservative, not an error
            sink.info(
                "ADJUSTMENT_SIGMA0_LOW",
                f"σ0 = {sigma0:.3f} is below the expected range ({dof} degrees of freedom): "
                f"the a priori precisions are conservative",
                sigma0=round(sigma0, 3),
                dof=dof,
            )
        for o in all_obs:
            if o.redundancy >= MIN_REDUNDANCY:
                o.w = o.residual / (o.sigma * math.sqrt(o.redundancy))
                o.flagged = abs(o.w) > w_crit
    else:
        sigma0 = 0.0
        sink.info(
            "ADJUSTMENT_NO_REDUNDANCY",
            "The network has no redundant observations; no statistical testing is possible",
            dof=dof,
        )

    ws = [abs(o.w) for o in all_obs if o.w is not None]
    max_w = max(ws) if ws else None
    flagged = [o for o in all_obs if o.flagged and o.w is not None]
    suspect_obs = max(flagged, key=lambda o: abs(o.w or 0.0)) if flagged else None
    if suspect_obs is not None:
        sink.warning(
            "ADJUSTMENT_BLUNDER",
            f"Suspected blunder: {suspect_obs.kind} {suspect_obs.station}→{suspect_obs.target} "
            f"(w = {suspect_obs.w:.2f}, critical {w_crit:.2f})",
            kind=suspect_obs.kind,
            station=suspect_obs.station,
            target=suspect_obs.target,
            w=round(suspect_obs.w or 0.0, 2),
            critical=round(w_crit, 2),
        )

    robust = _robust_summary(all_obs, robust_runs, settings, sink)

    # a posteriori variance only when the global test accepts it, otherwise a priori (σ0 = 1)
    s2 = sigma0 * sigma0 if global_test is not None and global_test.passed else 1.0

    # ---- write back ----------------------------------------------------------------------
    if hz_sol is not None:
        for name, (x, y) in hz_sol.values.items():
            col = hz_sol.point_cols[name]
            qxx = float(hz_sol.q[col, col])
            qyy = float(hz_sol.q[col + 1, col + 1])
            qxy = float(hz_sol.q[col, col + 1])
            kp = known[name]
            kp.x, kp.y = x, y
            kp.sx = math.sqrt(max(qxx, 0.0) * s2)
            kp.sy = math.sqrt(max(qyy, 0.0) * s2)
            kp.ellipse = _ellipse(qxx, qyy, qxy, s2)
    if h_sol is not None:
        for name, (z,) in h_sol.values.items():
            col = h_sol.point_cols[name]
            kp = known[name]
            kp.z = z
            kp.sz = math.sqrt(max(float(h_sol.q[col, col]), 0.0) * s2)

    def out(o: _Obs) -> AdjustedObservation:
        return AdjustedObservation(
            kind=o.kind,
            station=o.station,
            target=o.target,
            observed=o.value,
            adjusted=o.adjusted,
            residual=o.residual,
            sigma=o.sigma,
            redundancy=o.redundancy,
            w=o.w,
            flagged=o.flagged,
            weight=o.weight,
        )

    return AdjustmentResult(
        converged=all(s.converged for s in sols),
        iterations=max(s.iterations for s in sols),
        n_observations=n_obs,
        n_unknowns=n_unk,
        dof=dof,
        sigma0=sigma0,
        global_test=global_test,
        w_critical=w_crit,
        max_w=max_w,
        suspect=out(suspect_obs) if suspect_obs is not None else None,
        observations=[out(o) for o in all_obs],
        robust=robust,
    )


def _robust_summary(
    all_obs: list[_Obs],
    runs: list[tuple[int, bool]],
    settings: AdjustmentSettings,
    sink: IssueSink,
) -> RobustSummary | None:
    if settings.robust == "off":
        return None
    iterations = max((r[0] for r in runs), default=0)
    converged = all(r[1] for r in runs)
    down = sorted((o for o in all_obs if o.weight < DOWNWEIGHTED), key=lambda o: o.weight)
    if not converged:
        sink.warning(
            "ROBUST_NOT_CONVERGED",
            f"Robust estimation: the weights did not settle in {iterations} re-weightings",
            iterations=iterations,
        )
    if down:
        listed = ", ".join(f"{o.kind} {o.station}→{o.target}" for o in down[:5])
        sink.warning(
            "ROBUST_DOWNWEIGHTED",
            f"Robust estimation down-weighted {len(down)} observation(s): {listed}",
            count=len(down),
            observations=listed,
        )
    return RobustSummary(
        method=settings.robust,
        threshold=settings.robust_threshold,
        iterations=iterations,
        converged=converged,
        downweighted=len(down),
    )


__all__ = ["adjust_network", "robust_weight", "wrap_pi"]
