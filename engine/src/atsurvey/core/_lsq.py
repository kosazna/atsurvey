"""Small least-squares and statistics helpers shared by ``levelnet`` and ``instruments``.

Kept private (and independent of ``adjust.py``) so the levelling network and the instrument
checks do not depend on the traverse adjustment internals.

* Gauss–Markov model ``l + v = A x`` with weights ``P = diag(1/σ²)`` and a priori σ0 = 1
  (Niemeier, *Ausgleichungsrechnung*, 2nd ed., ch. 4; Ghilani, *Adjustment Computations*,
  6th ed., ch. 10–11).
* χ² quantiles by bisection on the regularized lower incomplete gamma function P(k/2, x/2)
  (series / continued fraction as in Press et al., *Numerical Recipes*, §6.2). Exact to ~1e-10,
  unlike the Wilson–Hilferty approximation, so small degrees of freedom (1–3), which are common
  in instrument checks and small levelling networks, are tested correctly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

#: Below this redundancy number an observation is uncontrolled: no w-test, no MDB.
MIN_REDUNDANCY = 1e-3
#: Condition number above which a normal matrix is treated as singular (datum defect, rank loss).
MAX_CONDITION = 1e12


class SingularSystem(ValueError):
    """The normal equations are singular: missing datum or an undetermined parameter."""


def _gamma_p(a: float, x: float) -> float:
    """Regularized lower incomplete gamma function P(a, x)."""
    if x <= 0.0:
        return 0.0
    gln = math.lgamma(a)
    if x < a + 1.0:
        term = total = 1.0 / a
        ap = a
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return total * math.exp(-x + a * math.log(x) - gln)
    # continued fraction for Q(a, x) (modified Lentz)
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return 1.0 - math.exp(-x + a * math.log(x) - gln) * h


def chi2_cdf(x: float, k: int) -> float:
    return _gamma_p(k / 2.0, x / 2.0)


def chi2_ppf(prob: float, k: int) -> float:
    """χ² quantile with ``k`` degrees of freedom (bisection, |error| < 1e-9·k)."""
    if not 0.0 < prob < 1.0 or k < 1:
        raise ValueError("chi2_ppf needs 0 < prob < 1 and k ≥ 1")
    lo, hi = 0.0, k + 50.0 * math.sqrt(2.0 * k) + 100.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if chi2_cdf(mid, k) < prob:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12 * max(1.0, hi):
            break
    return (lo + hi) / 2.0


def normal_quantile(prob: float) -> float:
    return NormalDist().inv_cdf(prob)


def baarda_delta0(alpha0: float, beta: float = 0.2) -> float:
    """Non-centrality δ0 of the w-test (Baarda 1968): 4.13 for α0 = 0.001, β = 0.2."""
    return normal_quantile(1.0 - alpha0 / 2.0) + normal_quantile(1.0 - beta)


def inverse_spd(nmat: np.ndarray) -> np.ndarray:
    """Inverse of a symmetric positive-definite matrix with Jacobi scaling.

    Raises ``SingularSystem`` when the matrix is (numerically) singular.
    """
    d = np.sqrt(np.diag(nmat))
    if not np.all(np.isfinite(d)) or np.any(d <= 0):
        raise SingularSystem("singular normal matrix")
    ns = nmat / np.outer(d, d)
    try:
        lchol = np.linalg.cholesky(ns)
    except np.linalg.LinAlgError as exc:
        raise SingularSystem("singular normal matrix") from exc
    if float(np.min(np.diag(lchol))) ** 2 < 1.0 / MAX_CONDITION:
        raise SingularSystem("singular normal matrix")
    inv = np.linalg.inv(lchol)
    return (inv.T @ inv) / np.outer(d, d)


@dataclass(frozen=True)
class LsqFit:
    """Result of a weighted least-squares fit ``l + v = A x``."""

    x: np.ndarray
    qxx: np.ndarray
    v: np.ndarray  # residuals (adjusted − observed)
    redundancy: np.ndarray  # r_i = (Qvv P)_ii
    vtpv: float
    dof: int

    @property
    def s0(self) -> float | None:
        """A posteriori σ0 (unitless when σ are the true a priori precisions)."""
        return math.sqrt(self.vtpv / self.dof) if self.dof > 0 else None

    def sigma_x(self, scale: float) -> np.ndarray:
        """Standard deviations of the parameters for a given σ (σ0 or s0)."""
        return np.sqrt(np.clip(np.diag(self.qxx), 0.0, None)) * scale


def lsq(a: np.ndarray, l_obs: np.ndarray, sigma: np.ndarray | None = None) -> LsqFit:
    """Weighted linear least squares with full cofactor matrix of the parameters.

    ``sigma`` are the a priori standard deviations of the observations (equal weights when
    omitted). Raises ``SingularSystem`` when a parameter is not determined.
    """
    m, u = a.shape
    if m < u:
        raise SingularSystem("fewer observations than unknowns")
    p = np.ones(m) if sigma is None else 1.0 / np.square(sigma)
    nmat = a.T @ (a * p[:, None])
    qxx = inverse_spd(nmat)
    x = qxx @ (a.T @ (p * l_obs))
    v = a @ x - l_obs
    aqa = np.einsum("ij,jk,ik->i", a, qxx, a)
    r = np.clip(1.0 - p * aqa, 0.0, 1.0)
    vtpv = math.fsum(float(t) for t in p * v * v)
    return LsqFit(x=x, qxx=qxx, v=v, redundancy=r, vtpv=vtpv, dof=m - u)
