"""Cut/fill volumes between a TIN and a horizontal level or a second TIN (exact prisms).

On each triangle (or, for two surfaces, on each polygon of their overlay) the difference
d = z_surface − z_reference is a linear function. The polygon is split along d = 0 by a
half-plane clip and the volumes are the exact integrals

    cut  = ∫ max(d, 0) dA,     fill = ∫ max(−d, 0) dA,

evaluated with ∫ f dA = A·(f₀ + f₁ + f₂)/3 over a triangle fan (the prismoidal formula is
exact for linear f). This is the TIN-to-TIN / TIN-to-plane prism method used by surveying
software (e.g. "composite volume"); no grid, no sampling error.

Two surfaces are overlaid exactly: every triangle of the existing surface is intersected
with the candidate triangles of the design surface (convex–convex Sutherland–Hodgman), so
only the common area is evaluated; the parts covered by one surface only are reported.
"""

from __future__ import annotations

import math

import numpy as np

from ..models import Issue
from .geom import (
    F64,
    I64,
    GridIndex,
    clip_by_triangles,
    clip_halfplane,
    fan_integrals,
    triangle_boxes,
    typical_size,
)
from .tin import Tin, planes

CHUNK = 100_000  # overlay pairs per vectorised batch (bounds peak memory)
METHOD_LEVEL = "TIN prism (exact): each triangle is split at the reference level"
METHOD_SURFACES = (
    "TIN-to-TIN prism (exact): overlay polygons of both surfaces split at zero difference"
)


def split_integrals(poly: F64, cnt: I64, coef: F64) -> tuple[float, float, float, float, float]:
    """(cut, fill, cut_area, fill_area, area) of polygons with linear d = a·x + b·y + c."""
    a, b, c = coef[:, 0], coef[:, 1], coef[:, 2]

    def d_at(p: F64) -> F64:
        return a[:, None] * p[:, :, 0] + b[:, None] * p[:, :, 1] + c[:, None]

    area, _ = fan_integrals(poly, cnt, np.zeros(poly.shape[:2]))
    pos, pc = clip_halfplane(poly, cnt, a, b, c)
    pos_area, cut = fan_integrals(pos, pc, d_at(pos))
    neg, nc = clip_halfplane(poly, cnt, -a, -b, -c)
    neg_area, fill = fan_integrals(neg, nc, -d_at(neg))
    flat = (a == 0) & (b == 0) & (c == 0)  # zero difference: neither cut nor fill
    pos_area = np.where(flat, 0.0, pos_area)
    neg_area = np.where(flat, 0.0, neg_area)
    return (
        math.fsum(cut.tolist()),
        math.fsum(fill.tolist()),
        math.fsum(pos_area.tolist()),
        math.fsum(neg_area.tolist()),
        math.fsum(area.tolist()),
    )


def volume_to_level(tin: Tin, level: float) -> tuple[float, float, float, float, float]:
    poly = tin.xy[tin.tri]
    cnt = np.full(len(poly), 3, dtype=np.int64)
    coef = tin.planes().copy()
    coef[:, 2] -= level
    return split_integrals(poly, cnt, coef)


def volume_between(
    existing: Tin, design: Tin
) -> tuple[tuple[float, float, float, float, float], float, float, list[Issue]]:
    """Cut/fill of existing − design over their common area, plus both plan areas."""
    shift = np.array(design.origin) - np.array(existing.origin)
    dxy = design.xy + shift
    pe = planes(existing.xy, existing.z, existing.tri)
    pd = planes(dxy, design.z, design.tri)
    lo_e, hi_e = triangle_boxes(existing.xy, existing.tri)
    lo_d, hi_d = triangle_boxes(dxy, design.tri)
    cell = max(typical_size(lo_e, hi_e), typical_size(lo_d, hi_d))
    index = GridIndex(lo_d, hi_d, cell)
    ie_all, id_all = index.query(lo_e, hi_e)
    parts = []
    for s in range(0, len(ie_all), CHUNK):
        ie, idd = ie_all[s : s + CHUNK], id_all[s : s + CHUNK]
        poly = existing.xy[existing.tri[ie]].copy()
        cnt = np.full(len(ie), 3, dtype=np.int64)
        poly, cnt, rows = clip_by_triangles(poly, cnt, dxy[design.tri[idd]])
        parts.append(split_integrals(poly, cnt, pe[ie[rows]] - pd[idd[rows]]))
    sums = [math.fsum(p[i] for p in parts) for i in range(5)]
    result = (sums[0], sums[1], sums[2], sums[3], sums[4])
    area_e = existing.stats.area_2d if existing.stats else 0.0
    area_d = design.stats.area_2d if design.stats else 0.0
    issues: list[Issue] = []
    common = result[4]
    if common <= 0:
        raise ValueError("The two surfaces do not overlap")
    tol = max(1e-6 * max(area_e, area_d), 1e-4)
    if area_e - common > tol or area_d - common > tol:
        issues.append(
            Issue(
                severity="warning",
                code="SURF_VOLUME_PARTIAL",
                message="The surfaces overlap partly; only the common area was evaluated",
                params={
                    "common_area": round(common, 2),
                    "existing_only": round(max(area_e - common, 0.0), 2),
                    "design_only": round(max(area_d - common, 0.0), 2),
                },
            )
        )
    return result, area_e, area_d, issues
