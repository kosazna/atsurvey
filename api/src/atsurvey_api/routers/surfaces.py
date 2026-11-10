"""/v1/surfaces/* endpoints (stateless): TIN, contours, heights, volumes, profiles, files.

Inputs are bounded by the request models (≤ 50 000 points, ≤ 2 000 contour levels, …) and
computations run in the guarded worker pool with the compute timeout. DXF files follow the
same plan gating as /v1/export (Pro); CSV is open to every plan that may export CSV.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from atsurvey.core import surfaces
from atsurvey.core.surfaces.export import export_surface
from atsurvey.core.surfaces.models import (
    ContoursRequest,
    ContoursResult,
    HeightsRequest,
    HeightsResult,
    LevelVolumeRequest,
    ProfileRequest,
    ProfileResult,
    SurfaceExportRequest,
    SurfaceRequest,
    SurfaceResult,
    SurfaceVolumeRequest,
    VolumeResult,
)

from .. import auth
from ..audit import log_export
from ..auth import Caller, require_compute
from ..config import Settings, get_settings
from ..security import run_guarded

router = APIRouter(prefix="/v1", tags=["surfaces"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def _run[Req, Res](fn: Callable[[Req], Res], req: Req, s: Settings) -> Res:
    try:
        return await run_guarded(s, fn, req, timeout=s.compute_timeout_s)
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:500]) from exc


@router.post("/surfaces/tin", response_model=SurfaceResult)
async def tin(req: SurfaceRequest, caller: ComputeCaller, s: SettingsDep) -> SurfaceResult:
    return await _run(surfaces.surface, req, s)


@router.post("/surfaces/contours", response_model=ContoursResult)
async def contours(req: ContoursRequest, caller: ComputeCaller, s: SettingsDep) -> ContoursResult:
    return await _run(surfaces.contour_lines, req, s)


@router.post("/surfaces/heights", response_model=HeightsResult)
async def heights(req: HeightsRequest, caller: ComputeCaller, s: SettingsDep) -> HeightsResult:
    return await _run(surfaces.heights, req, s)


@router.post("/surfaces/volume/level", response_model=VolumeResult)
async def volume_level(
    req: LevelVolumeRequest, caller: ComputeCaller, s: SettingsDep
) -> VolumeResult:
    return await _run(surfaces.volume_level, req, s)


@router.post("/surfaces/volume/surfaces", response_model=VolumeResult)
async def volume_surfaces(
    req: SurfaceVolumeRequest, caller: ComputeCaller, s: SettingsDep
) -> VolumeResult:
    return await _run(surfaces.volume_surfaces, req, s)


@router.post("/surfaces/profile", response_model=ProfileResult)
async def profile(req: ProfileRequest, caller: ComputeCaller, s: SettingsDep) -> ProfileResult:
    return await _run(surfaces.profile, req, s)


@router.post(
    "/surfaces/export",
    responses={200: {"content": {"application/octet-stream": {}}}},
    response_class=Response,
)
async def export(req: SurfaceExportRequest, caller: ComputeCaller, s: SettingsDep) -> Response:
    plan = await auth.plan_for(caller, s, req.workspace_id)
    if req.format not in auth.EXPORTS_BY_PLAN[plan]:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            {"code": "plan_required", "plan": plan, "format": req.format},
        )
    data, filename, media = await _run(export_surface, req, s)
    await log_export(caller, s, req.project_id, f"surface_{req.format}")
    ascii_name = filename.encode("ascii", "ignore").decode() or "surface"
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            )
        },
    )
