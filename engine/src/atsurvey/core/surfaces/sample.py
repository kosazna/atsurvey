"""Point location and line sampling on a TIN (linear interpolation in triangles).

Height at a point: the triangle containing it is found through a grid index and the height
is that of the triangle's plane, z = a·x + b·y + c, i.e. barycentric (linear) interpolation.
On a shared edge or vertex every adjacent triangle gives the same height (C⁰ surface).

A line segment is clipped against each candidate triangle with the Cyrus–Beck parametric
test (Cyrus & Beck 1978, "Generalized two- and three-dimensional clipping", Computers &
Graphics 3(1)); the entry/exit parameters are exactly the crossings of TIN edges.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .geom import F64, I64, GridIndex, triangle_boxes, typical_size
from .tin import Tin

INSIDE_EPS = 1e-9  # barycentric tolerance (dimensionless) for points on edges
T_EPS = 1e-12  # parametric tolerance along a segment


@dataclass(frozen=True)
class Sampler:
    tin: Tin
    index: GridIndex
    planes: F64

    @staticmethod
    def of(tin: Tin) -> Sampler:
        lo, hi = triangle_boxes(tin.xy, tin.tri)
        return Sampler(tin=tin, index=GridIndex(lo, hi, typical_size(lo, hi)), planes=tin.planes())

    def locate(self, q: F64) -> I64:
        """Triangle index containing each local point (−1 outside)."""
        out = np.full(len(q), -1, dtype=np.int64)
        qi, ti = self.index.query(q, q)
        if len(qi) == 0:
            return out
        p = self.tin.xy[self.tin.tri[ti]]
        x = q[qi]
        w = np.empty((len(qi), 3))
        for k in range(3):
            a = p[:, (k + 1) % 3] - x
            b = p[:, (k + 2) % 3] - x
            w[:, k] = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
        w /= w.sum(axis=1, keepdims=True)
        score = w.min(axis=1)
        order = np.lexsort((-score, qi))
        qi, ti, score = qi[order], ti[order], score[order]
        first = np.ones(len(qi), dtype=bool)
        first[1:] = qi[1:] != qi[:-1]
        ok = first & (score >= -INSIDE_EPS)
        out[qi[ok]] = ti[ok]
        return out

    def heights(self, q: F64) -> tuple[F64, I64]:
        t = self.locate(q)
        z = np.full(len(q), np.nan)
        ok = t >= 0
        pl = self.planes[t[ok]]
        z[ok] = pl[:, 0] * q[ok, 0] + pl[:, 1] * q[ok, 1] + pl[:, 2]
        return z, t

    def segment(self, p0: F64, p1: F64) -> list[list[tuple[float, float]]]:
        """Runs of (t, z) along p0→p1 (t ∈ [0, 1]) where the segment lies on the surface."""
        d = p1 - p0
        length = float(np.hypot(d[0], d[1]))
        if length == 0:
            return []
        k = max(1, math.ceil(length / self.index.cell))
        tt = np.linspace(0.0, 1.0, k + 1)
        pts = p0[None, :] + tt[:, None] * d[None, :]
        lo = np.minimum(pts[:-1], pts[1:])
        hi = np.maximum(pts[:-1], pts[1:])
        _, cand = self.index.query(lo, hi)
        cand = np.unique(cand)
        if len(cand) == 0:
            return []
        tri = self.tin.xy[self.tin.tri[cand]]
        t_in = np.zeros(len(cand))
        t_out = np.ones(len(cand))
        empty = np.zeros(len(cand), dtype=bool)
        for e in range(3):
            a, b = tri[:, e], tri[:, (e + 1) % 3]
            ex, ey = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
            s0 = ex * (p0[1] - a[:, 1]) - ey * (p0[0] - a[:, 0])
            s1 = ex * (p1[1] - a[:, 1]) - ey * (p1[0] - a[:, 0])
            empty |= (s0 < 0) & (s1 < 0)
            with np.errstate(divide="ignore", invalid="ignore"):
                tc = s0 / (s0 - s1)
            entering = (s0 < 0) & (s1 >= 0)
            leaving = (s0 >= 0) & (s1 < 0)
            t_in = np.where(entering, np.maximum(t_in, tc), t_in)
            t_out = np.where(leaving, np.minimum(t_out, tc), t_out)
        ok = ~empty & (t_out - t_in > T_EPS)
        if not ok.any():
            return []
        t_in, t_out, tid = t_in[ok], t_out[ok], cand[ok]
        order = np.argsort(t_in, kind="stable")
        t_in, t_out, tid = t_in[order], t_out[order], tid[order]
        pl = self.planes[tid]

        def zf(i: int, t: float) -> float:
            x = p0[0] + t * d[0]
            y = p0[1] + t * d[1]
            return float(pl[i, 0] * x + pl[i, 1] * y + pl[i, 2])

        runs: list[list[tuple[float, float]]] = []
        end = -1.0
        for i in range(len(tid)):
            a, b = float(t_in[i]), float(t_out[i])
            if not runs or a > end + T_EPS * 10:
                runs.append([(a, zf(i, a))])
            elif a > runs[-1][-1][0] + T_EPS:
                runs[-1].append((a, zf(i, a)))
            if b > end:
                runs[-1].append((b, zf(i, b)))
                end = b
        return [sorted(dict.fromkeys(r), key=lambda s: s[0]) for r in runs]
