"""/v1/coords/* endpoints (stateless): coordinate conversion and point information.

Failures with a stable code (e.g. ``COORD_HEPOS_UNAVAILABLE``) return 422 with
``{"detail": {"code", "message", "params"}}`` so the web app can show the Greek message;
other invalid input returns 422 with a plain message. See docs/coords.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from atsurvey.core.coords import (
    ConvertRequest,
    ConvertResult,
    CoordsError,
    PointInfoRequest,
    PointInfoResult,
    convert,
    point_info,
)

from ..auth import Caller, require_compute

router = APIRouter(prefix="/v1", tags=["coords"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]


def _run[Req, Res](fn: Callable[[Req], Res], req: Req) -> Res:
    try:
        return fn(req)
    except CoordsError as exc:
        detail = {"code": exc.code, "message": str(exc), "params": exc.params}
        raise HTTPException(422, detail) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/coords/convert", response_model=ConvertResult)
def convert_route(req: ConvertRequest, caller: ComputeCaller) -> ConvertResult:
    """Batch conversion (≤ 10 000 points) between ΕΓΣΑ87, φλ, UTM, TM3 and Hatt."""
    return _run(convert, req)


@router.post("/coords/point-info", response_model=PointInfoResult)
def point_info_route(req: PointInfoRequest, caller: ComputeCaller) -> PointInfoResult:
    """φ, λ, scale factor, meridian convergence and zones of one point."""
    return _run(point_info, req)
