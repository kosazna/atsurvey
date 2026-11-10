"""Triangulated irregular network (TIN) from surveyed points.

Pipeline (``build_surface``):

1. keep points with a height; merge points closer than ``duplicate_tolerance`` in plan
   (the first one is kept, the height spread is reported);
2. Delaunay triangulation (Qhull through ``scipy.spatial.Delaunay``; Barber, Dobkin &
   Huhdanpaa 1996, "The Quickhull algorithm for convex hulls", ACM TOMS 22(4));
3. breaklines enforced as edges by Sloan's edge-flipping algorithm (``cdt.py``);
4. optional trimming of long border triangles: triangles on the current border whose
   border edge is longer than ``max_edge`` are peeled repeatedly (in the spirit of the
   χ-shape of Duckham et al. 2008, Pattern Recognition 41(10));
5. optional exact clipping to a boundary polygon: border triangles are intersected with
   the triangles of the (constrained) triangulation of the polygon and re-triangulated;
   new vertices take their height from the plane of the triangle they lie in, so the
   clipped surface is the same piecewise-linear surface, restricted to the polygon.

Computations run in local coordinates (relative to the mean of the points) so that
ΕΓΣΑ87 magnitudes do not cost precision.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import Delaunay, QhullError, cKDTree  # pyright: ignore[reportAttributeAccessIssue]

from ..models import Issue
from .cdt import constrain
from .geom import (
    F64,
    I64,
    GridIndex,
    chain,
    clip_by_triangles,
    points_in_polygon,
    ring_area,
    triangle_boxes,
    typical_size,
)
from .models import DuplicateGroup, SurfaceResult, SurfaceSpec, SurfaceStats

DUPLICATE_DZ_WARN = 0.01  # m: merged points whose heights differ more are a warning
WELD_TOLERANCE = 1e-6  # m: vertices created by clipping closer than this are one vertex
MIN_TRIANGLE_AREA = 1e-10  # m²: slivers produced by clipping are dropped
MAX_LISTED = 20


@dataclass(frozen=True)
class Tin:
    origin: tuple[float, float]
    xy: F64  # (n, 2) local coordinates
    z: F64  # (n,)
    tri: I64  # (m, 3) counter-clockwise
    names: list[str | None]
    issues: list[Issue] = field(default_factory=list)
    stats: SurfaceStats | None = None
    outline: list[list[tuple[float, float]]] = field(default_factory=list)
    duplicates: list[DuplicateGroup] = field(default_factory=list)

    def local(self, x: F64, y: F64) -> F64:
        return np.column_stack([x - self.origin[0], y - self.origin[1]])

    def planes(self) -> F64:
        """(m, 3) coefficients (a, b, c) of z = a·x + b·y + c per triangle (local x, y)."""
        return planes(self.xy, self.z, self.tri)

    def result(self) -> SurfaceResult:
        assert self.stats is not None
        return SurfaceResult(
            stats=self.stats, outline=self.outline, duplicates=self.duplicates, issues=self.issues
        )


def planes(xy: F64, z: F64, tri: I64) -> F64:
    p = xy[tri]
    h = z[tri]
    u = p[:, 1] - p[:, 0]
    v = p[:, 2] - p[:, 0]
    du = h[:, 1] - h[:, 0]
    dv = h[:, 2] - h[:, 0]
    det = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    a = (du * v[:, 1] - dv * u[:, 1]) / det
    b = (dv * u[:, 0] - du * v[:, 0]) / det
    c = h[:, 0] - a * p[:, 0, 0] - b * p[:, 0, 1]
    return np.column_stack([a, b, c])


def signed_areas(xy: F64, tri: I64) -> F64:
    p = xy[tri]
    u = p[:, 1] - p[:, 0]
    v = p[:, 2] - p[:, 0]
    return 0.5 * (u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0])


def _issue(severity: str, code: str, message: str, **params: object) -> Issue:
    return Issue(severity=severity, code=code, message=message, params=params)  # type: ignore[arg-type]


def _listed(names: list[str | None]) -> list[str]:
    return [n or "—" for n in names[:MAX_LISTED]] + (["…"] if len(names) > MAX_LISTED else [])


# ------------------------------------------------------------------------- input points


@dataclass
class _Points:
    xy: F64
    z: F64
    names: list[str | None]
    name_to_index: dict[str, int]
    issues: list[Issue]
    without_z: int
    merged: int
    duplicates: list[DuplicateGroup]
    origin: tuple[float, float]


def _prepare_points(spec: SurfaceSpec) -> _Points:
    issues: list[Issue] = []
    with_z = [p for p in spec.points if p.z is not None]
    missing = [p.name for p in spec.points if p.z is None]
    if missing:
        issues.append(
            _issue(
                "info",
                "SURF_NO_Z",
                f"{len(missing)} point(s) without a height were left out",
                count=len(missing),
                points=_listed(missing),
            )
        )
    if len(with_z) < 3:
        raise ValueError("At least 3 points with a height are needed for a surface")
    gx = np.array([p.x for p in with_z])
    gy = np.array([p.y for p in with_z])
    origin = (math.fsum(gx) / len(gx), math.fsum(gy) / len(gy))
    xy = np.column_stack([gx - origin[0], gy - origin[1]])
    z = np.array([p.z for p in with_z], dtype=float)
    names = [p.name for p in with_z]

    keep = np.ones(len(xy), dtype=bool)
    groups: list[DuplicateGroup] = []
    rep = np.arange(len(xy))
    tol = spec.duplicate_tolerance
    pairs = cKDTree(xy).query_pairs(max(tol, 0.0), output_type="ndarray") if tol >= 0 else None
    if pairs is not None and len(pairs):
        n = len(xy)
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
        _, label = connected_components(g, directed=False)
        first: dict[int, int] = {}
        members: dict[int, list[int]] = {}
        for i, lab in enumerate(label.tolist()):
            first.setdefault(lab, i)
            members.setdefault(lab, []).append(i)
        for lab, idx in members.items():
            if len(idx) < 2:
                continue
            k = first[lab]
            for i in idx[1:]:
                keep[i] = False
                rep[i] = k
            dz = float(z[idx].max() - z[idx].min())
            groups.append(DuplicateGroup(kept=names[k], merged=[names[i] for i in idx[1:]], dz=dz))
    merged = int((~keep).sum())
    if merged:
        issues.append(
            _issue(
                "info",
                "SURF_DUPLICATE",
                f"{merged} coincident point(s) were merged",
                count=merged,
                tolerance=tol,
            )
        )
        for g_ in groups:
            if g_.dz > DUPLICATE_DZ_WARN:
                issues.append(
                    _issue(
                        "warning",
                        "SURF_DUPLICATE_Z",
                        f"Coincident points with different heights: {g_.kept} kept",
                        kept=g_.kept or "—",
                        merged=_listed(g_.merged),
                        dz=round(g_.dz, 3),
                    )
                )
    new_index = np.cumsum(keep) - 1
    name_to_index: dict[str, int] = {}
    for i, nm in enumerate(names):
        if nm is not None and nm not in name_to_index:
            name_to_index[nm] = int(new_index[rep[i]])
    return _Points(
        xy=xy[keep],
        z=z[keep],
        names=[n for n, k in zip(names, keep.tolist(), strict=True) if k],
        name_to_index=name_to_index,
        issues=issues,
        without_z=len(missing),
        merged=merged,
        duplicates=groups[:200],
        origin=origin,
    )


# ---------------------------------------------------------------------- triangulation


def delaunay(xy: F64) -> tuple[I64, list[int]]:
    """Counter-clockwise Delaunay triangles and the indices Qhull left out (coplanar)."""
    if len(xy) < 3:
        raise ValueError("At least 3 distinct points are needed for a surface")
    centred = xy - xy.mean(axis=0)
    sv = np.linalg.svd(centred, compute_uv=False)
    if sv[0] == 0 or sv[-1] / sv[0] < 1e-9:
        raise ValueError("The points are collinear: no surface can be formed")
    try:
        d = Delaunay(xy)
    except QhullError as exc:  # pragma: no cover - guarded by the collinearity test
        raise ValueError("The points cannot be triangulated (collinear or coincident)") from exc
    tri = d.simplices.astype(np.int64)
    neg = signed_areas(xy, tri) < 0
    tri[neg] = tri[neg][:, [0, 2, 1]]
    skipped = sorted({int(c[0]) for c in d.coplanar}) if len(d.coplanar) else []
    return tri, skipped


def edges_of(tri: I64) -> tuple[I64, I64]:
    """Unique undirected edges (e, 2) and, per triangle, the id of the edge opposite vertex k."""
    e = np.concatenate([tri[:, [1, 2]], tri[:, [2, 0]], tri[:, [0, 1]]])
    e.sort(axis=1)
    uniq, inv = np.unique(e, axis=0, return_inverse=True)
    m = len(tri)
    return uniq, inv.reshape(3, m).T


def border_edges(tri: I64) -> I64:
    """Directed border edges (a→b with the surface on the left)."""
    d = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    key = np.sort(d, axis=1)
    _, inv, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return d[counts[inv.ravel()] == 1]


def _trim(xy: F64, tri: I64, max_edge: float) -> tuple[I64, int]:
    removed = 0
    for _ in range(100_000):
        if len(tri) == 0:
            break
        d = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
        key = np.sort(d, axis=1)
        _, inv, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        border = (counts[inv.ravel()] == 1).reshape(3, -1).T
        length = np.linalg.norm(xy[d[:, 1]] - xy[d[:, 0]], axis=1).reshape(3, -1).T
        drop = np.any(border & (length > max_edge), axis=1)
        if not drop.any():
            break
        removed += int(drop.sum())
        tri = tri[~drop]
    return tri, removed


# ---------------------------------------------------------------------------- clipping


def polygon_triangles(ring: F64) -> I64:
    """Triangles (CCW) of a simple polygon: constrained Delaunay of its vertices."""
    tri, _ = delaunay(ring)
    n = len(ring)
    segs = [(i, (i + 1) % n) for i in range(n)]
    tri, _, rejected = constrain(ring, tri, segs)
    if rejected:
        raise ValueError("The boundary polygon intersects itself")
    cen = ring[tri].mean(axis=1)
    return tri[points_in_polygon(cen, ring)]


def _clean_ring(ring: F64) -> F64:
    keep = [0]
    for i in range(1, len(ring)):
        if np.linalg.norm(ring[i] - ring[keep[-1]]) > WELD_TOLERANCE:
            keep.append(i)
    r = ring[keep]
    if len(r) > 1 and np.linalg.norm(r[-1] - r[0]) <= WELD_TOLERANCE:
        r = r[:-1]
    if len(r) < 3 or abs(ring_area(r)) < MIN_TRIANGLE_AREA:
        raise ValueError("The boundary polygon has no area")
    if ring_area(r) < 0:
        r = r[::-1]
    return r


def clip_to_polygon(xy: F64, z: F64, tri: I64, ring: F64) -> tuple[F64, F64, I64, list[int]]:
    """Restrict a TIN to a polygon. Returns new (xy, z, tri) and the map old→new vertex."""
    ring = _clean_ring(ring)
    ptri = polygon_triangles(ring)
    lo, hi = triangle_boxes(xy, tri)
    cell = typical_size(lo, hi)
    index = GridIndex(lo, hi, cell)
    # border pieces of the polygon, subdivided so that each box stays small
    seg_lo, seg_hi = [], []
    n = len(ring)
    for i in range(n):
        p, q = ring[i], ring[(i + 1) % n]
        k = max(1, math.ceil(float(np.linalg.norm(q - p)) / cell))
        t = np.linspace(0.0, 1.0, k + 1)
        pts = p[None, :] + t[:, None] * (q - p)[None, :]
        seg_lo.append(np.minimum(pts[:-1], pts[1:]))
        seg_hi.append(np.maximum(pts[:-1], pts[1:]))
    _, near = index.query(np.concatenate(seg_lo), np.concatenate(seg_hi))
    crossing = np.zeros(len(tri), dtype=bool)
    crossing[near] = True
    cen = xy[tri].mean(axis=1)
    inside = ~crossing & points_in_polygon(cen, ring)

    # exact pieces of the crossing triangles
    ctri = np.nonzero(crossing)[0]
    plo, phi = triangle_boxes(ring, ptri)
    pindex = GridIndex(plo, phi, max(cell, typical_size(plo, phi)))
    qi, pj = pindex.query(lo[ctri], hi[ctri])
    src = ctri[qi]
    poly = xy[tri[src]].copy()
    cnt = np.full(len(src), 3, dtype=np.int64)
    poly, cnt, rows = clip_by_triangles(poly, cnt, ring[ptri[pj]])
    src = src[rows]
    pl = planes(xy, z, tri[src])

    new_xy = [xy]
    new_z = [z]
    new_tri = [tri[inside]]
    base = len(xy)
    k = poly.shape[1]
    if len(src) and k >= 3:
        flat = poly.reshape(-1, 2)
        zz = (pl[:, 0:1] * poly[:, :, 0] + pl[:, 1:2] * poly[:, :, 1] + pl[:, 2:3]).reshape(-1)
        new_xy.append(flat)
        new_z.append(zz)
        ids = base + np.arange(len(src) * k).reshape(len(src), k)
        fans = []
        for j in range(1, k - 1):
            ok = j + 1 < cnt
            fans.append(np.column_stack([ids[ok, 0], ids[ok, j], ids[ok, j + 1]]))
        new_tri.append(np.concatenate(fans))
    all_xy = np.concatenate(new_xy)
    all_z = np.concatenate(new_z)
    all_tri = np.concatenate(new_tri)
    return _weld(all_xy, all_z, all_tri, base)


def _weld(xy: F64, z: F64, tri: I64, n_orig: int) -> tuple[F64, F64, I64, list[int]]:
    """Merge coincident vertices (clipping creates the same point in neighbouring pieces),
    drop slivers and unused vertices. Original vertices win over created ones."""
    pairs = cKDTree(xy).query_pairs(WELD_TOLERANCE, output_type="ndarray")
    rep = np.arange(len(xy))
    if len(pairs):
        n = len(xy)
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
        _, label = connected_components(g, directed=False)
        first = np.full(label.max() + 1, len(xy))
        np.minimum.at(first, label, np.arange(len(xy)))
        rep = first[label]
    tri = rep[tri]
    ok = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri = tri[ok]
    tri = tri[signed_areas(xy, tri) > MIN_TRIANGLE_AREA]
    used = np.zeros(len(xy), dtype=bool)
    used[tri.ravel()] = True
    remap = np.cumsum(used) - 1
    old_to_new = [int(remap[i]) if used[i] else -1 for i in range(n_orig)]
    return xy[used], z[used], remap[tri], old_to_new


# ------------------------------------------------------------------------------- build


def _breakline_segments(
    spec: SurfaceSpec, pts: _Points, issues: list[Issue]
) -> list[tuple[int, int]]:
    segs: list[tuple[int, int]] = []
    missing: list[str] = []
    for bl in spec.breaklines:
        idx: list[int | None] = [pts.name_to_index.get(n) for n in bl.points]
        missing += [n for n, i in zip(bl.points, idx, strict=True) if i is None]
        seq = idx + ([idx[0]] if bl.closed and len(idx) > 2 else [])
        for a, b in itertools.pairwise(seq):
            if a is not None and b is not None and a != b:
                segs.append((a, b))
    if missing:
        issues.append(
            _issue(
                "warning",
                "SURF_BREAKLINE_POINT",
                "Breakline vertices that are not surface points (or have no height) were skipped",
                points=_listed(list(dict.fromkeys(missing))),
            )
        )
    return segs


def _outline(xy: F64, tri: I64, origin: tuple[float, float]) -> list[list[tuple[float, float]]]:
    be = border_edges(tri)
    rings = chain(be[:, 0].tolist(), be[:, 1].tolist())
    out = []
    for seq, _closed in rings:
        out.append([(float(xy[i, 0] + origin[0]), float(xy[i, 1] + origin[1])) for i in seq])
    return out


def build_surface(spec: SurfaceSpec) -> Tin:
    pts = _prepare_points(spec)
    issues = list(pts.issues)
    tri, skipped = delaunay(pts.xy)
    if skipped:
        issues.append(
            _issue(
                "warning",
                "SURF_POINT_UNUSED",
                "Points could not be used by the triangulation (numerically coincident)",
                points=_listed([pts.names[i] for i in skipped]),
            )
        )
    segs = _breakline_segments(spec, pts, issues)
    enforced = 0
    if segs:
        tri, done, rejected = constrain(pts.xy, tri, segs)
        enforced = len(done)
        if rejected:
            issues.append(
                _issue(
                    "warning",
                    "SURF_BREAKLINE_CROSSING",
                    "Breakline segments that cross another breakline were skipped",
                    segments=_listed([f"{pts.names[a]}–{pts.names[b]}" for a, b in rejected]),
                )
            )
    trimmed = 0
    if spec.max_edge is not None:
        tri, trimmed = _trim(pts.xy, tri, spec.max_edge)
        if trimmed:
            issues.append(
                _issue(
                    "info",
                    "SURF_TRIMMED",
                    f"{trimmed} border triangle(s) with edges longer than {spec.max_edge} m removed",
                    count=trimmed,
                    max_edge=spec.max_edge,
                )
            )
        if len(tri) == 0:
            raise ValueError("Every triangle was trimmed: increase the maximum edge length")
    xy, z, names = pts.xy, pts.z, pts.names
    if spec.boundary is not None:
        ring = np.array([[p.x - pts.origin[0], p.y - pts.origin[1]] for p in spec.boundary])
        xy, z, tri, old_to_new = clip_to_polygon(xy, z, tri, ring)
        if len(tri) == 0:
            raise ValueError("The boundary polygon does not overlap the surface")
        new_names: list[str | None] = [None] * len(xy)
        for i, j in enumerate(old_to_new):
            if j >= 0:
                new_names[j] = names[i]
        names = new_names
        poly_area = abs(ring_area(_clean_ring(ring)))
        covered = float(signed_areas(xy, tri).sum())
        uncovered = poly_area - covered
        if uncovered > max(1e-6 * poly_area, 1e-4):
            issues.append(
                _issue(
                    "warning",
                    "SURF_BOUNDARY_PARTIAL",
                    f"{uncovered:.2f} m² of the boundary polygon is outside the surface",
                    uncovered_area=round(uncovered, 2),
                )
            )
    return _finish(xy, z, tri, names, pts, issues, enforced, trimmed)


def _finish(
    xy: F64,
    z: F64,
    tri: I64,
    names: list[str | None],
    pts: _Points,
    issues: list[Issue],
    enforced: int,
    trimmed: int,
) -> Tin:
    used = np.unique(tri)
    area2 = signed_areas(xy, tri)
    p = np.concatenate([xy, z[:, None]], axis=1)[tri]
    n3 = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    area3 = 0.5 * np.linalg.norm(n3, axis=1)
    stats = SurfaceStats(
        points_in=pts.without_z + len(pts.xy) + pts.merged,
        points_without_z=pts.without_z,
        duplicates_merged=pts.merged,
        vertices=len(used),
        triangles=len(tri),
        z_min=float(z[used].min()),
        z_max=float(z[used].max()),
        area_2d=math.fsum(area2.tolist()),
        area_3d=math.fsum(area3.tolist()),
        breakline_segments=enforced,
        trimmed_triangles=trimmed,
    )
    return Tin(
        origin=pts.origin,
        xy=xy,
        z=z,
        tri=tri,
        names=names,
        issues=issues,
        stats=stats,
        outline=_outline(xy, tri, pts.origin),
        duplicates=pts.duplicates,
    )
