"""/v1/parcels/* endpoints (stateless): parcel geometry, area comparison, subdivision, merge.

Geometry problems come back as ``issues`` (stable codes, Greek templates) in a 200 response;
malformed requests (bounds, missing fields, out-of-range side index) are 422.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from atsurvey.core.parcels import AREA_TOLERANCE_PRESETS, analyze_parcel, compare_areas
from atsurvey.core.parcels_coverage import check_coverage
from atsurvey.core.parcels_merge import merge_parcels
from atsurvey.core.parcels_models import (
    AreaCompareRequest,
    AreaCompareResult,
    AreaTolerancePreset,
    CoverageRequest,
    CoverageResult,
    MergeRequest,
    MergeResult,
    Parcel,
    ParcelGeometry,
    SubdivideRequest,
    SubdivisionResult,
)
from atsurvey.core.parcels_subdivide import subdivide

from ..auth import Caller, require_compute

router = APIRouter(prefix="/v1", tags=["parcels"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]


def _run[Req, Res](fn: Callable[[Req], Res], req: Req) -> Res:
    try:
        return fn(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/parcels/compute", response_model=ParcelGeometry)
def compute(req: Parcel, caller: ComputeCaller) -> ParcelGeometry:
    """Area (arcs included), perimeter, side and vertex tables, validation."""
    return _run(analyze_parcel, req)


@router.post("/parcels/compare", response_model=AreaCompareResult)
def compare(req: AreaCompareRequest, caller: ComputeCaller) -> AreaCompareResult:
    """Surveyed vs deed vs Cadastre area, against a user-chosen tolerance rule."""
    return _run(compare_areas, req)


@router.post("/parcels/subdivide", response_model=SubdivisionResult)
def subdivide_route(req: SubdivideRequest, caller: ComputeCaller) -> SubdivisionResult:
    """Κατάτμηση: parallel / perpendicular to a side or through a pivot, by areas or ratios."""
    return _run(subdivide, req)


@router.post("/parcels/merge", response_model=MergeResult)
def merge(req: MergeRequest, caller: ComputeCaller) -> MergeResult:
    """Συνένωση of adjacent parcels sharing boundary vertices."""
    return _run(merge_parcels, req)


@router.post("/parcels/coverage", response_model=CoverageResult)
def coverage(req: CoverageRequest, caller: ComputeCaller) -> CoverageResult:
    """Do the parts cover the outline exactly (no gaps, overlaps or slivers)?"""
    return _run(check_coverage, req)


@router.get("/parcels/tolerance-presets", response_model=list[AreaTolerancePreset])
def tolerance_presets() -> list[AreaTolerancePreset]:
    """Hellenic Cadastre area-tolerance rules (urban / rural U0, with source)."""
    return AREA_TOLERANCE_PRESETS
