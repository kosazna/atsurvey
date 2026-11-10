"""Terrain surfaces: TIN, contours, heights at points, cut/fill volumes, profiles.

Public entry points take the request models of ``models.py`` and return result models
(stateless: the TIN is rebuilt for every request, which is fast for ≤ 50 000 points).
Method notes and references: docs/surfaces.md.
"""

from __future__ import annotations

import math

import numpy as np

from ..models import Issue
from .contours import contours as _contours
from .models import (
    ContoursRequest,
    ContoursResult,
    HeightRow,
    HeightsRequest,
    HeightsResult,
    LevelVolumeRequest,
    ProfileRequest,
    ProfileResult,
    SurfaceRequest,
    SurfaceResult,
    SurfaceVolumeRequest,
    VolumeResult,
)
from .profiles import cross_sections, gap_issue, long_profile
from .sample import Sampler
from .tin import MAX_LISTED, Tin, build_surface
from .volumes import METHOD_LEVEL, METHOD_SURFACES, volume_between, volume_to_level

__all__ = [
    "Tin",
    "build_surface",
    "contour_lines",
    "heights",
    "profile",
    "surface",
    "volume_level",
    "volume_surfaces",
]


def surface(req: SurfaceRequest) -> SurfaceResult:
    return build_surface(req.surface).result()


def contour_lines(req: ContoursRequest, tin: Tin | None = None) -> ContoursResult:
    """Contours of ``req.surface`` (or of an already built ``tin`` of that surface)."""
    tin = tin or build_surface(req.surface)
    levels, lines, issues = _contours(tin, req.interval, req.base, req.index_every)
    return ContoursResult(
        surface=tin.result(),
        interval=req.interval,
        base=req.base,
        levels=levels,
        lines=lines,
        issues=issues,
    )


def heights(req: HeightsRequest) -> HeightsResult:
    tin = build_surface(req.surface)
    s = Sampler.of(tin)
    q = tin.local(np.array([p.x for p in req.points]), np.array([p.y for p in req.points]))
    z, _ = s.heights(q)
    rows = [
        HeightRow(
            name=p.name, x=p.x, y=p.y, z=None if math.isnan(h) else h, inside=not math.isnan(h)
        )
        for p, h in zip(req.points, z.tolist(), strict=True)
    ]
    outside = [r.name or f"{r.x:.3f} {r.y:.3f}" for r in rows if not r.inside]
    issues: list[Issue] = []
    if outside:
        issues.append(
            Issue(
                severity="warning",
                code="SURF_OUTSIDE",
                message=f"{len(outside)} point(s) are outside the surface",
                params={
                    "count": len(outside),
                    "points": outside[:MAX_LISTED] + (["…"] if len(outside) > MAX_LISTED else []),
                },
            )
        )
    return HeightsResult(surface=tin.result(), rows=rows, issues=issues)


def volume_level(req: LevelVolumeRequest) -> VolumeResult:
    tin = build_surface(req.surface)
    cut, fill, cut_a, fill_a, area = volume_to_level(tin, req.level)
    return VolumeResult(
        method=METHOD_LEVEL,
        reference="level",
        level=req.level,
        cut=cut,
        fill=fill,
        net=cut - fill,
        cut_area=cut_a,
        fill_area=fill_a,
        area=area,
        surfaces=[tin.result()],
        issues=[],
    )


def volume_surfaces(req: SurfaceVolumeRequest) -> VolumeResult:
    specs = [req.existing, req.design]
    if req.boundary is not None:
        specs = [s.model_copy(update={"boundary": req.boundary}) for s in specs]
    existing, design = (build_surface(s) for s in specs)
    (cut, fill, cut_a, fill_a, area), _, _, issues = volume_between(existing, design)
    return VolumeResult(
        method=METHOD_SURFACES,
        reference="surface",
        cut=cut,
        fill=fill,
        net=cut - fill,
        cut_area=cut_a,
        fill_area=fill_a,
        area=area,
        surfaces=[existing.result(), design.result()],
        issues=issues,
    )


def profile(req: ProfileRequest) -> ProfileResult:
    tin = build_surface(req.surface)
    s = Sampler.of(tin)
    verts = tin.local(
        np.array([p.x for p in req.alignment]), np.array([p.y for p in req.alignment])
    )
    length, stations, gaps = long_profile(s, verts)
    if length == 0:
        raise ValueError("The alignment has zero length")
    sections = (
        cross_sections(s, verts, req.section_interval, req.half_width)
        if req.section_interval is not None
        else []
    )
    issues = [gap_issue()] if gaps else []
    return ProfileResult(
        surface=tin.result(), length=length, stations=stations, sections=sections, issues=issues
    )
