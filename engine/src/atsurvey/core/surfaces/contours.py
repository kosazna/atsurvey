"""Contours (ισοϋψείς) by marching triangles on the TIN, chained into polylines.

For a level L every triangle edge with one end ``z ≥ L`` and the other ``z < L`` is crossed
at the linearly interpolated point. Classifying ``z = L`` as "above" is the standard
symbolic perturbation (the level is lowered by an infinitesimal amount): a triangle is then
crossed by exactly 0 or 2 edges, contours never branch, and a vertex lying exactly on a
level needs no special case. Flat areas exactly at a level produce no line (the contour is
drawn at their lower border).

A crossing is identified by (level, TIN edge), so neighbouring triangles share it exactly
and chaining is topological, not by coordinates. Lines are oriented with higher ground on
the left (hills are counter-clockwise). No smoothing is applied: the lines are the exact
contours of the piecewise-linear TIN.
"""

from __future__ import annotations

import math

import numpy as np

from ..models import Issue
from .geom import expand_ranges
from .models import MAX_CONTOUR_LEVELS, MAX_CONTOUR_VERTICES, ContourLine
from .tin import Tin, edges_of


def level_range(zmin: float, zmax: float, base: float, interval: float) -> tuple[int, int]:
    """Smallest and largest k with zmin < base + k·interval ≤ zmax."""
    k0 = math.floor((zmin - base) / interval)
    while base + k0 * interval <= zmin:
        k0 += 1
    while base + (k0 - 1) * interval > zmin:
        k0 -= 1
    k1 = math.floor((zmax - base) / interval)
    while base + k1 * interval > zmax:
        k1 -= 1
    while base + (k1 + 1) * interval <= zmax:
        k1 += 1
    return k0, k1


def _chain_simple(nxt: list[int], has_in: list[bool]) -> list[tuple[list[int], bool]]:
    """Chains of a successor map where every node has at most one in and one out edge."""
    seen = bytearray(len(nxt))
    out: list[tuple[list[int], bool]] = []
    for start in range(len(nxt)):
        if has_in[start] or seen[start]:
            continue
        seq = [start]
        seen[start] = 1
        v = nxt[start]
        while v >= 0 and not seen[v]:
            seq.append(v)
            seen[v] = 1
            v = nxt[v]
        out.append((seq, False))
    for start in range(len(nxt)):
        if seen[start] or nxt[start] < 0:
            continue
        seq = [start]
        seen[start] = 1
        v = nxt[start]
        while v >= 0 and not seen[v]:
            seq.append(v)
            seen[v] = 1
            v = nxt[v]
        out.append((seq, v == start))
    return out


def contours(
    tin: Tin, interval: float, base: float, index_every: int
) -> tuple[list[float], list[ContourLine], list[Issue]]:
    issues: list[Issue] = []
    z, tri = tin.z, tin.tri
    zt = z[tri]
    zlo, zhi = zt.min(axis=1), zt.max(axis=1)
    g0, g1 = level_range(float(zlo.min()), float(zhi.max()), base, interval)
    n_levels = g1 - g0 + 1
    if n_levels > MAX_CONTOUR_LEVELS:
        raise ValueError(
            f"Too many contour levels ({n_levels} > {MAX_CONTOUR_LEVELS}): increase the interval"
        )
    if n_levels <= 0:
        issues.append(
            Issue(
                severity="info",
                code="SURF_CONTOURS_NONE",
                message="No contour level falls within the height range of the surface",
                params={},
            )
        )
        return [], [], issues
    # per triangle level range (same rule, vectorised, then corrected exactly)
    k0 = np.floor((zlo - base) / interval).astype(np.int64)
    k0 += (base + k0 * interval <= zlo).astype(np.int64)
    k0 -= (base + (k0 - 1) * interval > zlo).astype(np.int64)
    k1 = np.floor((zhi - base) / interval).astype(np.int64)
    k1 -= (base + k1 * interval > zhi).astype(np.int64)
    k1 += (base + (k1 + 1) * interval <= zhi).astype(np.int64)
    n = np.clip(k1 - k0 + 1, 0, None)
    total = int(n.sum())
    if total > MAX_CONTOUR_VERTICES:
        raise ValueError("Too many contour vertices: increase the interval or reduce the area")
    t_idx = np.repeat(np.arange(len(tri), dtype=np.int64), n)
    k = k0[t_idx] + expand_ranges(np.zeros(len(tri), dtype=np.int64), n)
    level = base + k * interval
    above = zt[t_idx] >= level[:, None]
    count = above.sum(axis=1)
    lone_above = count == 1
    # the isolated vertex: the only one above, or the only one below
    iso = np.where(lone_above, np.argmax(above, axis=1), np.argmin(above, axis=1))
    uniq, eid = edges_of(tri)
    e1 = eid[t_idx, (iso + 2) % 3]  # edge iso–iso+1
    e2 = eid[t_idx, (iso + 1) % 3]  # edge iso+2–iso
    start = np.where(lone_above, e1, e2)
    end = np.where(lone_above, e2, e1)
    kr = k - g0
    n_edges = len(uniq)
    keys = np.concatenate([kr * n_edges + start, kr * n_edges + end])
    nodes, inv = np.unique(keys, return_inverse=True)
    s_id, e_id = inv[: len(start)], inv[len(start) :]
    # crossing point of every node, from the edge in canonical (sorted) order
    node_k = nodes // n_edges
    node_e = nodes % n_edges
    a, b = uniq[node_e, 0], uniq[node_e, 1]
    lev = base + (node_k + g0) * interval
    t = (lev - z[a]) / (z[b] - z[a])
    xy = tin.xy[a] + t[:, None] * (tin.xy[b] - tin.xy[a])
    nxt = np.full(len(nodes), -1, dtype=np.int64)
    nxt[s_id] = e_id
    has_in = np.zeros(len(nodes), dtype=bool)
    has_in[e_id] = True
    ox, oy = tin.origin
    lines: list[ContourLine] = []
    gx = (xy[:, 0] + ox).tolist()
    gy = (xy[:, 1] + oy).tolist()
    nk = node_k.tolist()
    for seq, closed in _chain_simple(nxt.tolist(), has_in.tolist()):
        pts: list[tuple[float, float]] = []
        for v in seq:
            p = (gx[v], gy[v])
            if not pts or abs(p[0] - pts[-1][0]) > 1e-9 or abs(p[1] - pts[-1][1]) > 1e-9:
                pts.append(p)
        if closed and len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        if len(pts) < 2 or (closed and len(pts) < 3):
            continue
        kk = nk[seq[0]] + g0
        lines.append(
            ContourLine(
                z=base + kk * interval,
                index=index_every > 0 and kk % index_every == 0,
                closed=closed,
                points=pts,
            )
        )
    levels = [base + kk * interval for kk in range(g0, g1 + 1)]
    return levels, lines, issues
