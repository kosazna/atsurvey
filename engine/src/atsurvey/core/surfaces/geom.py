"""Vectorised plane geometry used by the surface tools.

* ``GridIndex``: uniform-grid bucket index of axis-aligned boxes (candidate pairs).
* ``clip_halfplane``: Sutherland–Hodgman clipping of many convex polygons at once
  (Sutherland & Hodgman 1974, "Reentrant polygon clipping", CACM 17(1)).
* ``fan_integrals``: exact area and integral of a linear function over convex polygons
  (∫f dA over a triangle = A·(f₀+f₁+f₂)/3, summed over a fan).
* ``points_in_polygon``: even–odd crossing test.
* ``orient``/``incircle``: exact-sign predicates (float filter, ``Fraction`` fallback),
  in the spirit of Shewchuk 1997, "Adaptive precision floating-point arithmetic and fast
  robust geometric predicates".
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
from numpy.typing import NDArray

F64 = NDArray[np.float64]
I64 = NDArray[np.int64]

MAX_INDEX_CELLS = 20_000_000  # bucket entries; protects memory on pathological inputs

# ----------------------------------------------------------------------------- predicates


def orient(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> int:
    """Sign of the signed area of (a, b, c): +1 counter-clockwise, −1 clockwise, 0 collinear."""
    lhs = (bx - ax) * (cy - ay)
    rhs = (by - ay) * (cx - ax)
    det = lhs - rhs
    bound = 3.3306690738754716e-16 * (abs(lhs) + abs(rhs))
    if det > bound:
        return 1
    if -det > bound:
        return -1
    fa = (Fraction(bx) - Fraction(ax)) * (Fraction(cy) - Fraction(ay)) - (
        Fraction(by) - Fraction(ay)
    ) * (Fraction(cx) - Fraction(ax))
    return (fa > 0) - (fa < 0)


def incircle(
    ax: float, ay: float, bx: float, by: float, cx: float, cy: float, dx: float, dy: float
) -> int:
    """+1 if d is strictly inside the circumcircle of the counter-clockwise triangle abc."""
    adx, ady, bdx, bdy, cdx, cdy = ax - dx, ay - dy, bx - dx, by - dy, cx - dx, cy - dy
    alift = adx * adx + ady * ady
    blift = bdx * bdx + bdy * bdy
    clift = cdx * cdx + cdy * cdy
    t1 = alift * (bdx * cdy - cdx * bdy)
    t2 = blift * (cdx * ady - adx * cdy)
    t3 = clift * (adx * bdy - bdx * ady)
    det = t1 + t2 + t3
    perm = (
        alift * (abs(bdx * cdy) + abs(cdx * bdy))
        + blift * (abs(cdx * ady) + abs(adx * cdy))
        + clift * (abs(adx * bdy) + abs(bdx * ady))
    )
    bound = 1e-14 * perm
    if det > bound:
        return 1
    if -det > bound:
        return -1
    fx = [Fraction(v) for v in (ax, ay, bx, by, cx, cy, dx, dy)]
    a_x, a_y = fx[0] - fx[6], fx[1] - fx[7]
    b_x, b_y = fx[2] - fx[6], fx[3] - fx[7]
    c_x, c_y = fx[4] - fx[6], fx[5] - fx[7]
    e = (
        (a_x * a_x + a_y * a_y) * (b_x * c_y - c_x * b_y)
        + (b_x * b_x + b_y * b_y) * (c_x * a_y - a_x * c_y)
        + (c_x * c_x + c_y * c_y) * (a_x * b_y - b_x * a_y)
    )
    return (e > 0) - (e < 0)


# ----------------------------------------------------------------------------- grid index


def expand_ranges(starts: I64, lengths: I64) -> I64:
    """Concatenate ``arange(s, s + n)`` for every (s, n) without a Python loop."""
    total = int(lengths.sum())
    if total == 0:
        return np.zeros(0, dtype=np.int64)
    offs = np.repeat(starts - np.cumsum(lengths) + lengths, lengths)
    return offs + np.arange(total, dtype=np.int64)


class GridIndex:
    """Buckets boxes ``[lo, hi]`` (n, 2) into square cells of side ``cell``."""

    def __init__(self, lo: F64, hi: F64, cell: float) -> None:
        self.cell = float(cell)
        self.origin = lo.min(axis=0) if len(lo) else np.zeros(2)
        self.lo = lo
        self.hi = hi
        ids, keys = self._cells(lo, hi)
        order = np.argsort(keys, kind="stable")
        self.keys = keys[order]
        self.ids = ids[order]

    def _cells(self, lo: F64, hi: F64) -> tuple[I64, I64]:
        i0 = np.floor((lo - self.origin) / self.cell).astype(np.int64)
        i1 = np.floor((hi - self.origin) / self.cell).astype(np.int64)
        nx = i1[:, 0] - i0[:, 0] + 1
        ny = i1[:, 1] - i0[:, 1] + 1
        counts = nx * ny
        total = int(counts.sum())
        if total > MAX_INDEX_CELLS:
            raise ValueError("Geometry too large for the spatial index (reduce the input size)")
        item = np.repeat(np.arange(len(lo), dtype=np.int64), counts)
        local = expand_ranges(np.zeros(len(lo), dtype=np.int64), counts)
        cx = i0[item, 0] + local // ny[item]
        cy = i0[item, 1] + local % ny[item]
        # Cantor-free key: cells are bounded by MAX_INDEX_CELLS so 2³¹ per axis is ample
        keys = (cx + (1 << 31)) * (1 << 32) + (cy + (1 << 31))
        return item, keys

    def query(self, lo: F64, hi: F64) -> tuple[I64, I64]:
        """All (query, item) pairs whose boxes overlap (each pair once)."""
        if len(lo) == 0 or len(self.ids) == 0:
            empty = np.zeros(0, dtype=np.int64)
            return empty, empty
        q, keys = self._cells(lo, hi)
        start = np.searchsorted(self.keys, keys, side="left")
        stop = np.searchsorted(self.keys, keys, side="right")
        n = stop - start
        qq = np.repeat(q, n)
        items = self.ids[expand_ranges(start, n)]
        if len(qq) == 0:
            return qq, items
        pair = np.unique(qq * (len(self.ids) + 1) + items)
        qq = pair // (len(self.ids) + 1)
        items = pair % (len(self.ids) + 1)
        ok = np.all(self.lo[items] <= hi[qq], axis=1) & np.all(self.hi[items] >= lo[qq], axis=1)
        return qq[ok], items[ok]


def triangle_boxes(xy: F64, tri: I64) -> tuple[F64, F64]:
    p = xy[tri]
    return p.min(axis=1), p.max(axis=1)


def typical_size(lo: F64, hi: F64) -> float:
    span = (hi - lo).max(axis=1)
    pos = span[span > 0]
    if len(pos) == 0:
        return 1.0
    return float(np.median(pos)) * 1.5


# ------------------------------------------------------------------------------ clipping


def clip_halfplane(poly: F64, cnt: I64, a: F64, b: F64, c: F64) -> tuple[F64, I64]:
    """Keep the part of each convex polygon where ``a·x + b·y + c ≥ 0``.

    ``poly`` is (N, K, 2) with ``cnt`` valid vertices per row. Returns the same layout.
    """
    n, k = poly.shape[0], poly.shape[1]
    if n == 0:
        return poly, cnt
    idx = np.arange(k)
    nxt = np.where(idx[None, :] + 1 < cnt[:, None], idx[None, :] + 1, 0)
    cur = poly
    nx = np.take_along_axis(poly, nxt[:, :, None].repeat(2, axis=2), axis=1)
    s0 = a[:, None] * cur[:, :, 0] + b[:, None] * cur[:, :, 1] + c[:, None]
    s1 = a[:, None] * nx[:, :, 0] + b[:, None] * nx[:, :, 1] + c[:, None]
    valid = idx[None, :] < cnt[:, None]
    in0 = s0 >= 0
    in1 = s1 >= 0
    keep = valid & in0
    cross = valid & (in0 != in1)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(cross, s0 / (s0 - s1), 0.0)
    ip = cur + t[:, :, None] * (nx - cur)
    out = np.empty((n, 2 * k, 2))
    out[:, 0::2] = cur
    out[:, 1::2] = ip
    mask = np.empty((n, 2 * k), dtype=bool)
    mask[:, 0::2] = keep
    mask[:, 1::2] = cross
    new_cnt = mask.sum(axis=1).astype(np.int64)
    kk = max(int(new_cnt.max()), 1)
    # compact the kept slots to the front (scatter by running count, no sort)
    pos = np.cumsum(mask, axis=1) - 1
    rows = np.broadcast_to(np.arange(n)[:, None], mask.shape)
    res = np.zeros((n, kk, 2))
    res[rows[mask], pos[mask]] = out[mask]
    # pad unused slots with the last valid vertex (zero-area fan triangles)
    pad = np.arange(kk)[None, :] >= new_cnt[:, None]
    if pad.any():
        fill = res[np.arange(n), np.clip(new_cnt - 1, 0, None)]
        res = np.where(pad[:, :, None], fill[:, None, :], res)
    return res, new_cnt


def clip_by_triangles(poly: F64, cnt: I64, tri_pts: F64) -> tuple[F64, I64, I64]:
    """Clip polygons by counter-clockwise triangles (N, 3, 2), row by row.

    Returns the non-empty pieces and the input row of each.
    """
    rows = np.arange(len(poly), dtype=np.int64)
    for i in range(3):
        p, q = tri_pts[:, i], tri_pts[:, (i + 1) % 3]
        # inside = left of p→q: (qx−px)(y−py) − (qy−py)(x−px) ≥ 0
        a = -(q[:, 1] - p[:, 1])
        b = q[:, 0] - p[:, 0]
        c = -(a * p[:, 0] + b * p[:, 1])
        poly, cnt = clip_halfplane(poly, cnt, a, b, c)
        ok = cnt >= 3
        poly, cnt, rows, tri_pts = poly[ok], cnt[ok], rows[ok], tri_pts[ok]
    return poly, cnt, rows


def fan_integrals(poly: F64, cnt: I64, f: F64) -> tuple[F64, F64]:
    """Area and ∫f dA for convex polygons, with ``f`` given at the vertices (N, K)."""
    n, k = poly.shape[0], poly.shape[1]
    area = np.zeros(n)
    integ = np.zeros(n)
    if n == 0 or k < 3:
        return area, integ
    p0 = poly[:, 0]
    for j in range(1, k - 1):
        ok = j + 1 < cnt
        u = poly[:, j] - p0
        v = poly[:, j + 1] - p0
        a = 0.5 * (u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0])
        a = np.where(ok, a, 0.0)
        area += a
        integ += np.where(ok, a * (f[:, 0] + f[:, j] + f[:, j + 1]) / 3.0, 0.0)
    return area, integ


# --------------------------------------------------------------------- point in polygon


def points_in_polygon(pts: F64, ring: F64) -> NDArray[np.bool_]:
    """Even–odd test of points (n, 2) against a closed ring (m, 2) (no repeated vertex)."""
    inside = np.zeros(len(pts), dtype=bool)
    px, py = pts[:, 0], pts[:, 1]
    m = len(ring)
    for i in range(m):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % m]
        if y1 == y2:
            continue
        crosses = (y1 > py) != (y2 > py)
        xint = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (px < xint)
    return inside


def ring_area(ring: F64) -> float:
    x, y = ring[:, 0] - ring[0, 0], ring[:, 1] - ring[0, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


# ---------------------------------------------------------------------------- chaining


def chain(starts: list[int], ends: list[int]) -> list[tuple[list[int], bool]]:
    """Chain directed segments (start→end node ids) into polylines.

    Returns (node sequence, closed). Open chains start at nodes without an incoming
    segment; what remains are loops. A node with several outgoing segments (pinch) is
    handled by consuming segments one at a time.
    """
    out_edges: dict[int, list[int]] = {}
    indeg: dict[int, int] = {}
    for i, (s, e) in enumerate(zip(starts, ends, strict=True)):
        out_edges.setdefault(s, []).append(i)
        indeg[e] = indeg.get(e, 0) + 1
    used = [False] * len(starts)
    result: list[tuple[list[int], bool]] = []

    def walk(seg: int) -> tuple[list[int], bool]:
        first = starts[seg]
        seq = [first]
        while True:
            used[seg] = True
            node = ends[seg]
            seq.append(node)
            nxt = next((j for j in out_edges.get(node, []) if not used[j]), None)
            if nxt is None:
                closed = node == first and len(seq) > 3
                if closed:
                    seq.pop()
                return seq, closed
            seg = nxt

    heads = [i for i, s in enumerate(starts) if indeg.get(s, 0) == 0]
    for i in heads:
        if not used[i]:
            result.append(walk(i))
    for i in range(len(starts)):
        if not used[i]:
            result.append(walk(i))
    return result
