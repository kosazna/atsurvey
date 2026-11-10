"""Instrument checks (έλεγχοι οργάνων): total station two-face test, level two-peg test and
EDM additive constant from a pillar baseline. All angles in radians; distances in metres.

References
----------
* Deumlich F., Staiger R., *Instrumentenkunde der Vermessungstechnik*, 9th ed., Wichmann 2002,
  §5.3 (Achsfehler des Theodolits), §6.4 (Prüfung des Nivelliers), §7.6 (Additionskonstante).
* Kahmen H., *Angewandte Geodäsie: Vermessungskunde*, 20th ed., de Gruyter 2006, §4.4, §5.4, §8.
* Leica Geosystems, *Surveying instruments – check and adjust* (white paper, 2014).
* ISO 17123-2 (levels), ISO 17123-3 (theodolites), ISO 17123-4 (EDM): field procedures.

Two-face test (Kahmen §4.4.3; Deumlich §5.3.2)
    A face-I horizontal reading contains c/sin z + a·cot z (collimation c, trunnion-axis tilt a),
    a face-II reading the same with opposite sign. With δ = ½·(Hz_I − Hz_II ± π):
        δ_j = c / sin z_j + a · cot z_j            (least squares over the targets)
    Zenith index error: i_j = ½·(V_I + V_II − 2π), i = mean (V_I − i is the corrected zenith).
    a is separable from c only if the targets span a range of cot z (steep and flat sights).

Two-peg test (general two-setup form; Förstner method by default, Deumlich §6.4.2)
    A reading at sight length s contains ε·s (ε = tangent of the collimation angle, positive
    when the line of sight points upward). Two setups with different sight-length imbalance:
        (a1 − b1) − ε (sA1 − sB1) = (a2 − b2) − ε (sA2 − sB2)
        ε = [(a1 − b1) − (a2 − b2)] / [(sA1 − sB1) − (sA2 − sB2)]
    Förstner: A and B 45 m apart, setups at 15 m from A and 15 m from B (sight lengths 15/30 and
    30/15). Kukkamäki (middle, then 20 m beyond B: 10/10 and 40/20) and Näbauer are special cases.

EDM additive constant (Deumlich §7.6; ISO 17123-4 annex "baseline method")
    Collinear pillars P0…Pk−1, every combination measured. With unknown pillar positions x_j
    (x_0 = 0) and additive constant k0:  d_ij + k0 = x_j − x_i. A scale error is not separable
    from unknown positions; it is estimated only with certified pillar positions X:
        d_ij + k0 + m·d_ij = X_j − X_i.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._lsq import LsqFit, SingularSystem, lsq
from .issues import IssueSink
from .models import Issue
from .units import wrap_pi

#: Two-face test: a needs cot z to span at least this range (≈ ±10 gon around the horizon).
MIN_COT_SPREAD = 0.15
#: Two-face test: |i| or |δ| beyond this (≈ 0.64 gon) means the readings are not a face pair.
MAX_FACE_ERROR = 0.01
#: Zenith angles closer than this to the zenith/nadir make c/sin z unstable (≈ 5 gon).
MIN_ZENITH = math.radians(4.5)
#: Two-peg test: minimum difference of the sight-length imbalances of the two setups, m.
MIN_IMBALANCE = 5.0
RHO_ARCSEC = 180.0 * 3600.0 / math.pi
RAD_TO_CC = 200.0 * 10000.0 / math.pi


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Angle = Field(ge=-4 * math.pi, le=4 * math.pi)
Name = Field(min_length=1, max_length=64)


class ReportFields(_M):
    """Echoed back unchanged; printed on the report."""

    model: str | None = Field(default=None, max_length=120)
    serial: str | None = Field(default=None, max_length=120)


# ------------------------------------------------------------------------- two-face test


class TwoFaceTarget(_M):
    name: str = Name
    hz1: float = Field(ge=-4 * math.pi, le=4 * math.pi, description="Face I horizontal, rad")
    hz2: float = Field(ge=-4 * math.pi, le=4 * math.pi, description="Face II horizontal, rad")
    v1: float = Field(gt=0, lt=2 * math.pi, description="Face I zenith angle, rad")
    v2: float = Field(gt=0, lt=2 * math.pi, description="Face II zenith angle, rad")


class TwoFaceRequest(_M):
    targets: list[TwoFaceTarget] = Field(min_length=1, max_length=200)
    trunnion: Literal["auto", "always", "never"] = "auto"


class TwoFaceRow(_M):
    name: str
    zenith: float = Field(description="Index-corrected zenith angle, rad")
    hz: float = Field(description="Mean direction (face I frame), rad")
    delta: float = Field(description="½(Hz_I − Hz_II ± π), rad")
    index: float = Field(description="½(V_I + V_II − 2π), rad")
    residual_hz: float = Field(description="Fitted − observed δ, rad")
    residual_v: float = Field(description="i − i_j, rad")


class TwoFaceResult(_M):
    collimation: float = Field(description="c, rad")
    sigma_collimation: float | None
    trunnion: float | None = Field(description="a, rad (None when not estimated)")
    sigma_trunnion: float | None
    index: float = Field(description="Vertical index error i, rad")
    sigma_index: float | None
    s0_hz: float | None = Field(description="σ of one δ, rad")
    s0_v: float | None = Field(description="σ of one i_j, rad")
    dof_hz: int
    dof_v: int
    trunnion_estimated: bool
    rows: list[TwoFaceRow]
    issues: list[Issue] = Field(default_factory=list)


def _sigmas(fit: LsqFit) -> list[float | None]:
    s0 = fit.s0
    return [None] * len(fit.x) if s0 is None else [float(s) for s in fit.sigma_x(s0)]


def two_face_test(req: TwoFaceRequest) -> TwoFaceResult:
    sink = IssueSink()
    deltas, idx, zen, hz = [], [], [], []
    for t in req.targets:
        d = wrap_pi(t.hz1 - t.hz2 + math.pi) / 2.0
        i = (t.v1 + t.v2 - 2.0 * math.pi) / 2.0
        z = (t.v1 - t.v2 + 2.0 * math.pi) / 2.0
        if not MIN_ZENITH <= z <= math.pi - MIN_ZENITH:
            raise ValueError(f"Target {t.name}: the sight is too steep for the two-face test")
        if abs(d) > MAX_FACE_ERROR or abs(i) > MAX_FACE_ERROR:
            sink.warning(
                "INSTR_FACE_MISMATCH",
                f"Target {t.name}: face I and II readings differ too much "
                "(check the face II readings or the target)",
                target=t.name,
            )
        deltas.append(d)
        idx.append(i)
        zen.append(z)
        hz.append(t.hz1 - d)

    sin_z = np.sin(np.array(zen))
    cot_z = np.cos(np.array(zen)) / sin_z
    spread = float(np.max(cot_z) - np.min(cot_z))
    want_a = req.trunnion == "always" or (req.trunnion == "auto" and spread >= MIN_COT_SPREAD)
    if want_a and len(zen) < 2:
        want_a = False
    if req.trunnion == "auto" and not want_a:
        sink.info(
            "INSTR_TRUNNION_UNRESOLVED",
            "The targets do not span enough elevation to separate the trunnion-axis error; "
            "only the collimation error was estimated",
            spread=round(spread, 3),
        )
    a_mat = np.column_stack([1.0 / sin_z, cot_z]) if want_a else (1.0 / sin_z)[:, None]
    try:
        fit = lsq(a_mat, np.array(deltas))
    except SingularSystem as exc:
        raise ValueError(
            "The trunnion-axis error cannot be separated from the collimation error with "
            "these targets; aim at targets with different elevations"
        ) from exc
    sig = _sigmas(fit)

    i_mean = math.fsum(idx) / len(idx)
    dof_v = len(idx) - 1
    res_v = [i_mean - i for i in idx]
    s0_v = math.sqrt(math.fsum(r * r for r in res_v) / dof_v) if dof_v > 0 else None
    rows = [
        TwoFaceRow(
            name=t.name,
            zenith=zen[j],
            hz=hz[j] % (2.0 * math.pi),
            delta=deltas[j],
            index=idx[j],
            residual_hz=float(fit.v[j]),
            residual_v=res_v[j],
        )
        for j, t in enumerate(req.targets)
    ]
    return TwoFaceResult(
        collimation=float(fit.x[0]),
        sigma_collimation=sig[0],
        trunnion=float(fit.x[1]) if want_a else None,
        sigma_trunnion=sig[1] if want_a else None,
        index=i_mean,
        sigma_index=s0_v / math.sqrt(len(idx)) if s0_v is not None else None,
        s0_hz=fit.s0,
        s0_v=s0_v,
        dof_hz=fit.dof,
        dof_v=dof_v,
        trunnion_estimated=want_a,
        rows=rows,
        issues=sink.items,
    )


# ------------------------------------------------------------------------- two-peg test


class PegSetup(_M):
    a: float = Field(ge=-10, le=10, description="Staff reading on A, m")
    b: float = Field(ge=-10, le=10, description="Staff reading on B, m")
    dist_a: float = Field(ge=0, le=200, description="Sight length to A, m")
    dist_b: float = Field(ge=0, le=200, description="Sight length to B, m")


class TwoPegRequest(_M):
    method: Literal["forstner", "kukkamaki", "middle_end", "custom"] = "forstner"
    setup1: PegSetup
    setup2: PegSetup
    tolerance_mm_per_30m: float = Field(default=3.0, gt=0, le=100)

    @model_validator(mode="after")
    def _check(self) -> TwoPegRequest:
        imb = (self.setup1.dist_a - self.setup1.dist_b) - (self.setup2.dist_a - self.setup2.dist_b)
        if abs(imb) < MIN_IMBALANCE:
            raise ValueError(
                "The two setups must have different sight lengths to A and B "
                f"(imbalance difference {imb:.1f} m, at least {MIN_IMBALANCE:.0f} m needed)"
            )
        return self


class TwoPegResult(_M):
    epsilon: float = Field(description="Line-of-sight inclination (tan), + upward")
    angle: float = Field(description="Collimation angle, rad")
    error_mm_per_30m: float
    error_arcsec: float
    error_cc: float
    dh_true: float = Field(description="H_B − H_A free of collimation error, m")
    dh_setup1: float
    dh_setup2: float
    corrected_a2: float = Field(description="Reading on A at setup 2 for a level line of sight")
    corrected_b2: float = Field(description="Reading on B at setup 2 for a level line of sight")
    tolerance_mm_per_30m: float
    within_tolerance: bool


def two_peg_test(req: TwoPegRequest) -> TwoPegResult:
    s1, s2 = req.setup1, req.setup2
    dh1 = s1.a - s1.b
    dh2 = s2.a - s2.b
    eps = (dh1 - dh2) / ((s1.dist_a - s1.dist_b) - (s2.dist_a - s2.dist_b))
    angle = math.atan(eps)
    err30 = eps * 30.0 * 1000.0
    return TwoPegResult(
        epsilon=eps,
        angle=angle,
        error_mm_per_30m=err30,
        error_arcsec=angle * RHO_ARCSEC,
        error_cc=angle * RAD_TO_CC,
        dh_true=(s1.a - eps * s1.dist_a) - (s1.b - eps * s1.dist_b),
        dh_setup1=dh1,
        dh_setup2=dh2,
        corrected_a2=s2.a - eps * s2.dist_a,
        corrected_b2=s2.b - eps * s2.dist_b,
        tolerance_mm_per_30m=req.tolerance_mm_per_30m,
        within_tolerance=abs(err30) <= req.tolerance_mm_per_30m,
    )


# ------------------------------------------------------------------------- EDM constant


class EdmObservation(_M):
    frm: str = Name
    to: str = Name
    distance: float = Field(gt=0, le=5000, description="Reduced horizontal distance, m")


class EdmRequest(_M):
    pillars: list[str] = Field(min_length=3, max_length=12, description="In order along the line")
    observations: list[EdmObservation] = Field(min_length=3, max_length=500)
    positions: list[float] | None = Field(
        default=None,
        description="Certified distances of the pillars from the first one, m (enables scale)",
    )

    @model_validator(mode="after")
    def _check(self) -> EdmRequest:
        names = [p.strip() for p in self.pillars]
        if len(set(names)) != len(names) or not all(names):
            raise ValueError("Pillar names must be unique and not empty")
        known = set(names)
        for k, o in enumerate(self.observations):
            if o.frm.strip() not in known or o.to.strip() not in known:
                raise ValueError(f"Observation {k + 1}: unknown pillar ({o.frm} → {o.to})")
            if o.frm.strip() == o.to.strip():
                raise ValueError(f"Observation {k + 1}: same pillar at both ends")
        if self.positions is not None:
            if len(self.positions) != len(names):
                raise ValueError("Give one certified position per pillar")
            if any(not math.isfinite(x) or abs(x) > 5000 for x in self.positions):
                raise ValueError("Certified positions must be finite (|x| ≤ 5000 m)")
            if any(b <= a for a, b in zip(self.positions, self.positions[1:], strict=False)):
                raise ValueError("Certified positions must increase along the line")
        return self


class EdmRow(_M):
    frm: str
    to: str
    distance: float
    adjusted: float = Field(description="Pillar-to-pillar distance from the positions, m")
    residual: float = Field(description="v of the measured distance: d + v + k0 (+ m·d) = adjusted")


class EdmResult(_M):
    constant: float = Field(description="Additive constant k0, m (add to measured distances)")
    sigma_constant: float | None
    scale_ppm: float | None = Field(description="Scale correction, ppm (certified baseline only)")
    sigma_scale_ppm: float | None
    s0: float | None = Field(description="σ of one distance, m")
    dof: int
    positions: list[float] = Field(description="Pillar positions from the first pillar, m")
    sigma_positions: list[float | None]
    rows: list[EdmRow]
    issues: list[Issue] = Field(default_factory=list)


def edm_constant(req: EdmRequest) -> EdmResult:
    sink = IssueSink()
    names = [p.strip() for p in req.pillars]
    pos = {n: k for k, n in enumerate(names)}
    obs = []
    for o in req.observations:
        i, j = pos[o.frm.strip()], pos[o.to.strip()]
        obs.append((min(i, j), max(i, j), o.distance))
    m = len(obs)
    dist = np.array([d for _, _, d in obs])

    xs = [x - req.positions[0] for x in req.positions] if req.positions is not None else []
    certified = bool(xs)
    if certified:
        a_mat = np.column_stack([np.ones(m), dist])
        l_obs = np.array([xs[j] - xs[i] - d for i, j, d in obs])
    else:
        a_mat = np.zeros((m, len(names)))  # columns: x_1 … x_{k−1}, k0
        for r, (i, j, _) in enumerate(obs):
            if i > 0:
                a_mat[r, i - 1] = -1.0
            a_mat[r, j - 1] = 1.0
            a_mat[r, -1] = -1.0
        l_obs = dist
    try:
        fit = lsq(a_mat, l_obs)
    except SingularSystem as exc:
        raise ValueError(
            "The additive constant is not determined: measure every combination of pillars "
            "(not only consecutive ones)"
        ) from exc
    sig = _sigmas(fit)
    if fit.dof == 0:
        sink.info(
            "INSTR_EDM_NO_REDUNDANCY",
            "No redundant distances: the constant has no precision estimate "
            "(use four pillars or repeat the measurements)",
        )

    if certified:
        k0, scale = float(fit.x[0]), float(fit.x[1])
        positions = xs
        sigma_pos: list[float | None] = [0.0] * len(names)
        residuals = [float(-v) for v in fit.v]
    else:
        k0, scale = float(fit.x[-1]), None
        positions = [0.0, *(float(x) for x in fit.x[:-1])]
        sigma_pos = [0.0, *sig[:-1]]
        residuals = [float(v) for v in fit.v]
    rows = [
        EdmRow(
            frm=names[i],
            to=names[j],
            distance=d,
            adjusted=positions[j] - positions[i],
            residual=residuals[r],
        )
        for r, (i, j, d) in enumerate(obs)
    ]
    k_sig = sig[0] if certified else sig[-1]
    return EdmResult(
        constant=k0,
        sigma_constant=k_sig,
        scale_ppm=scale * 1e6 if scale is not None else None,
        sigma_scale_ppm=sig[1] * 1e6 if certified and sig[1] is not None else None,
        s0=fit.s0,
        dof=fit.dof,
        positions=positions,
        sigma_positions=sigma_pos,
        rows=rows,
        issues=sink.items,
    )
