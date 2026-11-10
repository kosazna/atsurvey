"""COGO tools and geometric levelling: /v1/cogo/*, /v1/leveling (stateless, no plan limits)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from atsurvey.core import cogo
from atsurvey.core.cogo_models import (
    AreaRequest,
    AreaResult,
    IntersectionAnglesRequest,
    IntersectionDistancesRequest,
    IntersectionLinesRequest,
    IntersectionResult,
    InverseRequest,
    InverseResult,
    LevelingRequest,
    LevelingResult,
    OffsetRequest,
    OffsetResult,
    PolarRequest,
    PolarResult,
    ResectionRequest,
    ResectionResult,
    StakeoutRequest,
    StakeoutResult,
    TransformRequest,
    TransformResult,
)
from atsurvey.core.leveling import level
from atsurvey.core.specs import TolerancePreset, tolerance_presets

from ..auth import Caller, require_compute

router = APIRouter(prefix="/v1", tags=["cogo"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]


def _run[Req, Res](fn: Callable[[Req], Res], req: Req) -> Res:
    try:
        return fn(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cogo/inverse", response_model=InverseResult)
def inverse(req: InverseRequest, caller: ComputeCaller) -> InverseResult:
    return _run(cogo.inverse, req)


@router.post("/cogo/polar", response_model=PolarResult)
def polar(req: PolarRequest, caller: ComputeCaller) -> PolarResult:
    return _run(cogo.polar, req)


@router.post("/cogo/intersection/angles", response_model=IntersectionResult)
def intersection_angles(
    req: IntersectionAnglesRequest, caller: ComputeCaller
) -> IntersectionResult:
    return _run(cogo.intersection_angles, req)


@router.post("/cogo/intersection/distances", response_model=IntersectionResult)
def intersection_distances(
    req: IntersectionDistancesRequest, caller: ComputeCaller
) -> IntersectionResult:
    return _run(cogo.intersection_distances, req)


@router.post("/cogo/intersection/lines", response_model=IntersectionResult)
def intersection_lines(req: IntersectionLinesRequest, caller: ComputeCaller) -> IntersectionResult:
    return _run(cogo.intersection_lines, req)


@router.post("/cogo/resection", response_model=ResectionResult)
def resection(req: ResectionRequest, caller: ComputeCaller) -> ResectionResult:
    return _run(cogo.resection, req)


@router.post("/cogo/area", response_model=AreaResult)
def area(req: AreaRequest, caller: ComputeCaller) -> AreaResult:
    return _run(cogo.area, req)


@router.post("/cogo/transform", response_model=TransformResult)
def transform(req: TransformRequest, caller: ComputeCaller) -> TransformResult:
    return _run(cogo.transform, req)


@router.post("/cogo/offset", response_model=OffsetResult)
def offset(req: OffsetRequest, caller: ComputeCaller) -> OffsetResult:
    return _run(cogo.offset, req)


@router.post("/leveling", response_model=LevelingResult)
def leveling(req: LevelingRequest, caller: ComputeCaller) -> LevelingResult:
    return _run(level, req)


@router.post("/cogo/stakeout", response_model=StakeoutResult)
def stakeout(req: StakeoutRequest, caller: ComputeCaller) -> StakeoutResult:
    return _run(cogo.stakeout, req)


@router.get("/presets/tolerances", response_model=list[TolerancePreset])
def tolerance_presets_route() -> list[TolerancePreset]:
    """Tolerance presets (Greek specification: scale × class × terrain)."""
    return tolerance_presets()
