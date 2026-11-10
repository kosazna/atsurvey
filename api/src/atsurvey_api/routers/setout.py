"""/v1/setout/* endpoints: batch setting out, as-staked check and road alignments (stateless,
open to the same callers as /v1/compute). Degenerate input → 422 with an explanation.
See docs/setout.md."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from atsurvey.core import alignment, setout
from atsurvey.core.alignment_models import (
    AlignmentRequest,
    AlignmentResult,
    AlignmentStakeoutRequest,
    AlignmentStakeoutResult,
    LocateRequest,
    LocateResult,
)
from atsurvey.core.setout import CheckRequest, CheckResult, SetoutRequest, SetoutResult

from ..auth import Caller, require_compute

router = APIRouter(prefix="/v1", tags=["setout"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]


def _run[Req, Res](fn: Callable[[Req], Res], req: Req) -> Res:
    try:
        return fn(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/setout/points", response_model=SetoutResult)
def setout_points(req: SetoutRequest, caller: ComputeCaller) -> SetoutResult:
    """Directions and distances to set out design points from one station (χάραξη)."""
    return _run(setout.setout_points, req)


@router.post("/setout/check", response_model=CheckResult)
def setout_check(req: CheckRequest, caller: ComputeCaller) -> CheckResult:
    """As-staked check: measured against design points, matched by name."""
    return _run(setout.check_staked, req)


@router.post("/setout/alignment", response_model=AlignmentResult)
def setout_alignment(req: AlignmentRequest, caller: ComputeCaller) -> AlignmentResult:
    """Horizontal alignment from the tangent polygon (and optional vertical profile)."""
    return _run(alignment.alignment, req)


@router.post("/setout/alignment/locate", response_model=LocateResult)
def setout_locate(req: LocateRequest, caller: ComputeCaller) -> LocateResult:
    """(chainage, offset) → coordinates and coordinates → (chainage, offset)."""
    return _run(alignment.locate, req)


@router.post("/setout/alignment/stakeout", response_model=AlignmentStakeoutResult)
def setout_alignment_stakeout(
    req: AlignmentStakeoutRequest, caller: ComputeCaller
) -> AlignmentStakeoutResult:
    """Stakeout list every Δ metres plus the main points, at the requested offsets."""
    return _run(alignment.stakeout, req)
