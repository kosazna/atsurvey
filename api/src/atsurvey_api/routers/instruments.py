"""Instrument checks and levelling network adjustment (stateless, no plan limits).

* ``POST /v1/leveling/network``      — least-squares levelling network (core/levelnet.py)
* ``POST /v1/instruments/two-face``  — total station collimation, index and trunnion errors
* ``POST /v1/instruments/two-peg``   — level collimation (two-peg) test
* ``POST /v1/instruments/edm-constant`` — EDM additive constant (and scale) from a baseline

Inputs are bounded by the pydantic models (list lengths, finite numbers); see docs/instruments.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from atsurvey.core.instruments import (
    EdmRequest,
    EdmResult,
    TwoFaceRequest,
    TwoFaceResult,
    TwoPegRequest,
    TwoPegResult,
    edm_constant,
    two_face_test,
    two_peg_test,
)
from atsurvey.core.levelnet import LevelNetRequest, LevelNetResult, adjust_level_network

from ..auth import Caller, require_compute

router = APIRouter(prefix="/v1", tags=["instruments"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]


def _run[Req, Res](fn: Callable[[Req], Res], req: Req) -> Res:
    try:
        return fn(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/leveling/network", response_model=LevelNetResult)
def leveling_network(req: LevelNetRequest, caller: ComputeCaller) -> LevelNetResult:
    return _run(adjust_level_network, req)


@router.post("/instruments/two-face", response_model=TwoFaceResult)
def two_face(req: TwoFaceRequest, caller: ComputeCaller) -> TwoFaceResult:
    return _run(two_face_test, req)


@router.post("/instruments/two-peg", response_model=TwoPegResult)
def two_peg(req: TwoPegRequest, caller: ComputeCaller) -> TwoPegResult:
    return _run(two_peg_test, req)


@router.post("/instruments/edm-constant", response_model=EdmResult)
def edm(req: EdmRequest, caller: ComputeCaller) -> EdmResult:
    return _run(edm_constant, req)
