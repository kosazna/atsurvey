"""Least-squares adjustment of a levelling network (συνόρθωση χωροσταθμικού δικτύου).

Model (parametric / Gauss–Markov, one height unknown per point; Niemeier, *Ausgleichungsrechnung*
§4.3 and §6; Ghilani, *Adjustment Computations* ch. 12 "Adjustment of level nets"):

    Δh_ij + v_ij = H_j − H_i,      σ_ij = σ_km·√L_ij  (weight 1/L)  or  σ_n·√n_ij  (weight 1/n)

* **Datum.** ``fixed``: the benchmarks are held fixed (hard constraints); every connected part of
  the network needs at least one. ``free``: no point is fixed; the minimal constraint
  Σ_{i∈S} H_i = Σ_{i∈S} H_i^ref keeps the mean height of the chosen points S (default: the
  benchmarks, else every point), so the adjusted network is not distorted by the benchmarks
  and the benchmark heights can be checked against it (stability check).
  The cofactor matrix of the heights is the upper-left block of the inverse of the bordered
  normal matrix [[N, Cᵀ], [C, 0]] (Koch, *Parameter Estimation*, §3.4).
* **Global test.** Ω = vᵀPv against χ²_f (two-sided, α = 5 %), a priori σ0 = 1.
* **Data snooping** (Baarda 1968): w_i = v_i / σ_vi with σ_vi² = σ_i² − σ²(Δh_adj,i);
  critical value N(1 − α0/2) (3.29 for α0 = 0.1 %). Only the largest |w| above the critical
  value is flagged: remove it and re-adjust before looking at the next one.
  Minimal detectable bias MDB_i = δ0·σ_i/√r_i (δ0 = 4.13 for α0 = 0.1 %, β = 20 %).
* **Loops (βρόχοι).** An independent cycle basis from a breadth-first spanning tree: one loop
  per line not in the tree (Deo, *Graph Theory*, §5.3). With fixed benchmarks a virtual datum
  node joined to every benchmark makes benchmark-to-benchmark connections part of the same
  basis, so the basis has exactly f = n − u conditions. Misclosure w = Σ ±Δh − (H_end − H_start),
  tolerance = base + c·√L_km (or c_n·√n), as in the levelling section.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._loops import Closure, Edge, Graph, components, loop_basis
from ._lsq import (
    MAX_CONDITION,
    MIN_REDUNDANCY,
    SingularSystem,
    baarda_delta0,
    chi2_ppf,
    inverse_spd,
    normal_quantile,
)
from .issues import IssueSink
from .models import Issue

MAX_LINES = 3000
MAX_POINTS = 1000


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Name = Field(min_length=1, max_length=64)


class LevelNetBenchmark(_M):
    name: str = Name
    h: float = Field(ge=-1000, le=10000, description="Known height, m")


class LevelNetLine(_M):
    frm: str = Name
    to: str = Name
    dh: float = Field(ge=-10000, le=10000, description="Measured H(to) − H(frm), m")
    length_km: float | None = Field(default=None, gt=0, le=1000, description="Line length, km")
    setups: int | None = Field(default=None, ge=1, le=100000, description="Number of setups")


class LevelNetRequest(_M):
    benchmarks: list[LevelNetBenchmark] = Field(default_factory=list, max_length=500)
    lines: list[LevelNetLine] = Field(min_length=1, max_length=MAX_LINES)
    weighting: Literal["length", "setups"] = "length"
    sigma_mm_per_sqrt_km: float = Field(default=2.0, gt=0, le=100)
    sigma_mm_per_setup: float = Field(
        default=0.5, gt=0, le=100, description="σ per √(number of setups), mm"
    )
    datum: Literal["fixed", "free"] = "fixed"
    free_points: list[str] | None = Field(
        default=None,
        max_length=MAX_POINTS,
        description="Points whose mean height is kept in a free network "
        "(default: the benchmarks, else every point)",
    )
    alpha_global: float = Field(default=0.05, gt=0, lt=0.5)
    alpha_w: float = Field(default=0.001, gt=0, lt=0.5)
    tolerance_base_mm: float = Field(default=0.0, ge=0, le=1000)
    tolerance_mm_per_sqrt_km: float = Field(default=12.0, ge=0, le=1000)
    tolerance_mm_per_sqrt_setup: float | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def _check(self) -> LevelNetRequest:
        names = [b.name.strip() for b in self.benchmarks]
        if len(set(names)) != len(names):
            raise ValueError("Benchmark names must be unique")
        for i, ln in enumerate(self.lines):
            if ln.frm.strip() == ln.to.strip():
                raise ValueError(f"Line {i + 1} starts and ends on the same point ({ln.frm})")
            if self.weighting == "length" and ln.length_km is None:
                raise ValueError(f"Line {i + 1} ({ln.frm}→{ln.to}) needs a length for 1/L weights")
            if self.weighting == "setups" and ln.setups is None:
                raise ValueError(f"Line {i + 1} ({ln.frm}→{ln.to}) needs the number of setups")
        return self


class LevelNetPoint(_M):
    name: str
    h: float
    sigma_h: float = Field(description="Standard deviation of the height, m (0 for fixed)")
    kind: Literal["fixed", "adjusted"]
    known_h: float | None = Field(default=None, description="Benchmark height, if any")
    known_diff: float | None = Field(
        default=None, description="Free network: adjusted − known height of a benchmark, m"
    )


class LevelNetLineResult(_M):
    index: int = Field(description="0-based index in the request")
    frm: str
    to: str
    dh: float
    dh_adjusted: float
    residual: float = Field(description="v = adjusted − measured, m")
    sigma: float = Field(description="A priori σ of the line, m")
    redundancy: float
    w: float | None = Field(description="Baarda w statistic (None if not controlled)")
    mdb: float | None = Field(description="Minimal detectable bias, m")
    flagged: bool = False


class LevelNetLoop(_M):
    kind: Literal["loop", "connection"]
    points: list[str] = Field(description="Traversal order; a loop returns to its first point")
    lines: list[int] = Field(description="0-based line indices in traversal order")
    signs: list[int] = Field(description="+1 when the line is run frm→to, −1 reversed")
    misclosure: float = Field(description="Σ±Δh − (H_end − H_start), m")
    length_km: float | None
    setups: int | None
    tolerance: float | None
    within_tolerance: bool | None


class LevelNetGlobalTest(_M):
    statistic: float
    lower: float
    upper: float
    passed: bool


class LevelNetResult(_M):
    datum: Literal["fixed", "free"]
    points: list[LevelNetPoint]
    lines: list[LevelNetLineResult]
    loops: list[LevelNetLoop]
    n_observations: int
    n_unknowns: int
    dof: int
    sigma0: float | None = Field(description="A posteriori σ0 (a priori σ0 = 1)")
    variance_factor: float = Field(description="Factor applied to σH (s0² if the test passed)")
    global_test: LevelNetGlobalTest | None
    w_critical: float
    suspect_line: int | None = Field(description="0-based index of the flagged line")
    excluded_points: list[str] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)


# ---------------------------------------------------------------------------- adjustment


def _line_sigma(req: LevelNetRequest, ln: LevelNetLine) -> float:
    if req.weighting == "length":
        return req.sigma_mm_per_sqrt_km * math.sqrt(ln.length_km or 0.0) / 1000.0
    return req.sigma_mm_per_setup * math.sqrt(ln.setups or 0) / 1000.0


def _loop_tolerance(
    req: LevelNetRequest, length_km: float | None, setups: int | None
) -> float | None:
    if length_km is not None:
        return (req.tolerance_base_mm + req.tolerance_mm_per_sqrt_km * math.sqrt(length_km)) / 1e3
    if setups is not None and req.tolerance_mm_per_sqrt_setup is not None:
        return (req.tolerance_base_mm + req.tolerance_mm_per_sqrt_setup * math.sqrt(setups)) / 1e3
    return None


def _line_weight(req: LevelNetRequest, e: Edge) -> float:
    """Path length used to prefer short loops: km, setups, or 1 per line."""
    ln = req.lines[e.id]
    value = ln.length_km if req.weighting == "length" else ln.setups
    return float(value) if value else 1.0


def _closure_to_loop(req: LevelNetRequest, c: Closure, bench: dict[str, float]) -> LevelNetLoop:
    """Loop (returns to its start) or benchmark connection (ends on another benchmark)."""
    steps, start, kind = c.steps, c.start, c.kind
    misclosure = math.fsum(sign * e.dh for e, sign, _ in steps)
    if kind == "connection":
        misclosure = math.fsum(
            [*(sign * e.dh for e, sign, _ in steps), bench[start], -bench[steps[-1][2]]]
        )
    lines = [e.id for e, _, _ in steps]
    lens = [req.lines[i].length_km for i in lines]
    sets = [req.lines[i].setups for i in lines]
    length = (
        math.fsum(x for x in lens if x is not None) if all(x is not None for x in lens) else None
    )
    n_set = sum(x for x in sets if x is not None) if all(x is not None for x in sets) else None
    tol = _loop_tolerance(req, length, n_set)
    return LevelNetLoop(
        kind=kind,
        points=[start, *(n for _, _, n in steps)],
        lines=lines,
        signs=[s for _, s, _ in steps],
        misclosure=misclosure,
        length_km=length,
        setups=n_set,
        tolerance=tol,
        within_tolerance=None if tol is None else abs(misclosure) <= tol,
    )


def _approximate_heights(g: Graph, roots: dict[str, float]) -> dict[str, float]:
    """Heights carried along a BFS tree from the given root heights (exact for a tree)."""
    h = dict(roots)
    queue = deque(roots)
    while queue:
        n = queue.popleft()
        for e in g.adj.get(n, []):
            other, sign = (e.b, 1.0) if e.a == n else (e.a, -1.0)
            if other not in h:
                h[other] = h[n] + sign * e.dh
                queue.append(other)
    return h


@dataclass
class _Solution:
    h: dict[str, float]
    q: np.ndarray
    col: dict[str, int]


def _solve(
    req: LevelNetRequest,
    edges: list[Edge],
    unknowns: list[str],
    h0: dict[str, float],
    constraint: dict[str, float] | None,
) -> _Solution:
    """Normal equations in the corrections to ``h0``; optional minimal (mean) constraint."""
    col = {n: i for i, n in enumerate(unknowns)}
    u = len(unknowns)
    nmat = np.zeros((u, u))
    rhs = np.zeros(u)
    for e in edges:
        ln = req.lines[e.id]
        p = 1.0 / _line_sigma(req, ln) ** 2
        lred = e.dh - (h0[e.b] - h0[e.a])
        ia, ib = col.get(e.a), col.get(e.b)
        if ia is not None:
            nmat[ia, ia] += p
            rhs[ia] -= p * lred
        if ib is not None:
            nmat[ib, ib] += p
            rhs[ib] += p * lred
        if ia is not None and ib is not None:
            nmat[ia, ib] -= p
            nmat[ib, ia] -= p
    if constraint is None:
        q = inverse_spd(nmat)
        dx = q @ rhs
    else:
        cvec = np.zeros(u)
        for n in constraint:
            cvec[col[n]] = 1.0
        target = math.fsum(constraint[n] - h0[n] for n in constraint)
        big = np.zeros((u + 1, u + 1))
        big[:u, :u] = nmat
        big[u, :u] = cvec
        big[:u, u] = cvec
        scale = math.sqrt(float(np.mean(np.diag(nmat))))
        d = np.full(u + 1, scale)
        d[u] = 1.0
        scaled = big / np.outer(d, d)
        if np.linalg.cond(scaled) > MAX_CONDITION:
            raise SingularSystem("singular free network")
        inv = np.linalg.inv(scaled) / np.outer(d, d)
        q = inv[:u, :u]
        dx = inv[:u, :u] @ rhs + inv[:u, u] * target
    h = {n: h0[n] + float(dx[col[n]]) for n in unknowns}
    return _Solution(h=h, q=q, col=col)


def adjust_level_network(req: LevelNetRequest) -> LevelNetResult:
    sink = IssueSink()
    lines = [ln.model_copy(update={"frm": ln.frm.strip(), "to": ln.to.strip()}) for ln in req.lines]
    req = req.model_copy(update={"lines": lines})
    bench = {b.name.strip(): b.h for b in req.benchmarks}
    req = req.model_copy(
        update={"benchmarks": [LevelNetBenchmark(name=n, h=h) for n, h in bench.items()]}
    )

    edges = [Edge(i, ln.frm, ln.to, ln.dh) for i, ln in enumerate(lines)]
    nodes: list[str] = list(dict.fromkeys(n for ln in lines for n in (ln.frm, ln.to)))
    if len(nodes) > MAX_POINTS:
        raise ValueError(f"The network has {len(nodes)} points; the limit is {MAX_POINTS}")
    on_net = set(nodes)
    unused = [b for b in bench if b not in on_net]
    if unused:
        sink.info(
            "LEVNET_UNUSED_BENCHMARK",
            f"Benchmarks not connected to any line: {', '.join(unused)}",
            points=unused,
        )
    comps = components(nodes, edges)

    excluded: list[str] = []
    if req.datum == "fixed":
        kept = [c for c in comps if any(n in bench for n in c)]
        for c in comps:
            if not any(n in bench for n in c):
                excluded.extend(c)
        if excluded:
            sink.error(
                "LEVNET_NO_DATUM",
                "No benchmark in a part of the network; these points cannot be adjusted: "
                + ", ".join(excluded),
                points=excluded,
            )
    else:
        kept = [max(comps, key=len)]
        if len(comps) > 1:
            excluded = [n for c in comps if c is not kept[0] for n in c]
            sink.error(
                "LEVNET_DISCONNECTED",
                f"The network is in {len(comps)} separate parts; a free network must be "
                f"connected. Not adjusted: {', '.join(excluded)}",
                parts=len(comps),
                points=excluded,
            )
    if req.datum == "fixed" and len(kept) > 1:
        sink.info(
            "LEVNET_PARTS",
            f"The network is in {len(kept)} separate parts, each tied to its own benchmarks",
            parts=len(kept),
        )

    kept_nodes = [n for c in kept for n in c]
    kept_set = set(kept_nodes)
    kept_edges = [e for e in edges if e.a in kept_set]
    w_crit = normal_quantile(1.0 - req.alpha_w / 2.0)
    if not kept_edges:
        return LevelNetResult(
            datum=req.datum,
            points=[],
            lines=[],
            loops=[],
            n_observations=0,
            n_unknowns=0,
            dof=0,
            sigma0=None,
            variance_factor=1.0,
            global_test=None,
            w_critical=w_crit,
            suspect_line=None,
            excluded_points=excluded,
            issues=sink.items,
        )

    g = Graph()
    for e in kept_edges:
        g.add(e)
    constraint: dict[str, float] | None = None
    if req.datum == "fixed":
        roots = {n: bench[n] for n in kept_nodes if n in bench}
        unknowns = [n for n in kept_nodes if n not in bench]
    else:
        net_bench = [n for n in kept_nodes if n in bench]
        root = net_bench[0] if net_bench else kept_nodes[0]
        roots = {root: bench.get(root, 0.0)}
        unknowns = list(kept_nodes)
    h0 = _approximate_heights(g, roots)
    if req.datum == "free":
        chosen = [p.strip() for p in (req.free_points or []) if p.strip()]
        missing = [p for p in chosen if p not in kept_set]
        if missing:
            raise ValueError(f"Datum points not in the network: {', '.join(missing)}")
        if not chosen:
            chosen = [n for n in kept_nodes if n in bench] or list(kept_nodes)
        constraint = {n: bench.get(n, h0[n]) for n in dict.fromkeys(chosen)}

    try:
        sol = _solve(req, kept_edges, unknowns, h0, constraint) if unknowns else None
    except SingularSystem as exc:
        raise ValueError("The network cannot be adjusted (singular normal equations)") from exc
    heights = {**{n: bench[n] for n in kept_nodes if n in bench}, **(sol.h if sol else {})}

    # ---- residuals, redundancy, statistics -----------------------------------------------
    n_obs = len(kept_edges)
    n_unk = len(unknowns)
    dof = n_obs - n_unk + (1 if constraint is not None else 0)
    delta0 = baarda_delta0(req.alpha_w)

    def qdiff(a: str, b: str) -> float:
        if sol is None:
            return 0.0
        ia, ib = sol.col.get(a), sol.col.get(b)
        qa = float(sol.q[ia, ia]) if ia is not None else 0.0
        qb = float(sol.q[ib, ib]) if ib is not None else 0.0
        qab = float(sol.q[ia, ib]) if ia is not None and ib is not None else 0.0
        return qa + qb - 2.0 * qab

    rows: list[LevelNetLineResult] = []
    vtpv_terms: list[float] = []
    for e in kept_edges:
        sigma = _line_sigma(req, lines[e.id])
        adj = heights[e.b] - heights[e.a]
        v = adj - e.dh
        qvv = max(sigma * sigma - qdiff(e.a, e.b), 0.0)
        r = min(max(qvv / (sigma * sigma), 0.0), 1.0)
        controlled = r >= MIN_REDUNDANCY and dof > 0
        vtpv_terms.append(v * v / (sigma * sigma))
        rows.append(
            LevelNetLineResult(
                index=e.id,
                frm=e.a,
                to=e.b,
                dh=e.dh,
                dh_adjusted=adj,
                residual=v,
                sigma=sigma,
                redundancy=r,
                w=v / math.sqrt(qvv) if controlled else None,
                mdb=delta0 * sigma / math.sqrt(r) if controlled else None,
            )
        )
    vtpv = math.fsum(vtpv_terms)
    global_test = None
    sigma0 = None
    if dof > 0:
        sigma0 = math.sqrt(vtpv / dof)
        lower = chi2_ppf(req.alpha_global / 2.0, dof)
        upper = chi2_ppf(1.0 - req.alpha_global / 2.0, dof)
        global_test = LevelNetGlobalTest(
            statistic=vtpv, lower=lower, upper=upper, passed=lower <= vtpv <= upper
        )
        if vtpv > upper:
            sink.warning(
                "LEVNET_GLOBAL_TEST",
                f"Global test failed: σ0 = {sigma0:.3f} with {dof} degrees of freedom; "
                "check the a priori σ or look for a blunder",
                sigma0=round(sigma0, 3),
                dof=dof,
            )
        elif vtpv < lower:
            sink.info(
                "LEVNET_SIGMA0_LOW",
                f"σ0 = {sigma0:.3f} is below the expected range ({dof} degrees of freedom): "
                "the a priori σ are conservative",
                sigma0=round(sigma0, 3),
                dof=dof,
            )
    else:
        sink.info(
            "LEVNET_NO_REDUNDANCY",
            "The network has no redundant lines; it cannot be checked statistically",
            dof=dof,
        )
    flagged = [r for r in rows if r.w is not None and abs(r.w) > w_crit]
    suspect = max(flagged, key=lambda r: abs(r.w or 0.0)) if flagged else None
    if suspect is not None:
        suspect.flagged = True
        sink.warning(
            "LEVNET_BLUNDER",
            f"Suspected blunder in line {suspect.index + 1} {suspect.frm}→{suspect.to} "
            f"(w = {suspect.w:.2f}, critical {w_crit:.2f})",
            line=suspect.index + 1,
            frm=suspect.frm,
            to=suspect.to,
            w=round(suspect.w or 0.0, 2),
            critical=round(w_crit, 2),
        )
    var_factor = (
        sigma0 * sigma0 if sigma0 is not None and global_test and global_test.passed else 1.0
    )

    # ---- loops -----------------------------------------------------------------------------
    # independent loops (short ones first) and benchmark connections (fixed datum only)
    fixed_bms = list(roots) if req.datum == "fixed" else []
    loops = [
        _closure_to_loop(req, c, bench)
        for c in loop_basis(g, kept_edges, fixed_bms, lambda e: _line_weight(req, e), len(lines))
    ]
    for lp in loops:
        if lp.within_tolerance is False:
            tol_mm = (lp.tolerance or 0.0) * 1000
            sink.warning(
                "LEVNET_LOOP_TOLERANCE",
                f"{'Loop' if lp.kind == 'loop' else 'Connection'} {' → '.join(lp.points)}: "
                f"misclosure {lp.misclosure * 1000:.1f} mm exceeds {tol_mm:.1f} mm",
                points=" → ".join(lp.points),
                misclosure_mm=round(lp.misclosure * 1000, 1),
                tolerance_mm=round(tol_mm, 1),
            )

    # ---- points ----------------------------------------------------------------------------
    order = [n for n in kept_nodes if n in bench] + [n for n in kept_nodes if n not in bench]
    points: list[LevelNetPoint] = []
    for n in order:
        fixed = req.datum == "fixed" and n in bench
        q = 0.0
        if sol is not None and n in sol.col:
            q = max(float(sol.q[sol.col[n], sol.col[n]]), 0.0)
        points.append(
            LevelNetPoint(
                name=n,
                h=heights[n],
                sigma_h=0.0 if fixed else math.sqrt(q * var_factor),
                kind="fixed" if fixed else "adjusted",
                known_h=bench.get(n),
                known_diff=heights[n] - bench[n] if (not fixed and n in bench) else None,
            )
        )
    rows.sort(key=lambda r: r.index)
    return LevelNetResult(
        datum=req.datum,
        points=points,
        lines=rows,
        loops=loops,
        n_observations=n_obs,
        n_unknowns=n_unk,
        dof=dof,
        sigma0=sigma0,
        variance_factor=var_factor,
        global_test=global_test,
        w_critical=w_crit,
        suspect_line=suspect.index if suspect else None,
        excluded_points=excluded,
        issues=sink.items,
    )
