"""ATSurvey engine API.

Stateless by design: the browser loads a project from Supabase, sends it here to be
parsed / computed / exported, and stores results back through Supabase (RLS applies).
That keeps recomputation instant while editing and keeps database credentials off this
server; the engine stays server-side so paid features cannot be bypassed.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from atsurvey import ProjectInput, ProjectResult, TraverseSpec, __version__, compute_project
from atsurvey.core.suggest import suggest_traverses
from atsurvey.core.units import AngleUnit
from atsurvey.exports import ExportFormat, ExportOptions, export
from atsurvey.formats import PARSER_VERSION, ParseError, ParseResult, parse_file
from atsurvey.formats.base import FormatName

from .audit import log_export
from .auth import EXPORTS_BY_PLAN, Caller, get_caller, plan_for, require_compute
from .config import Settings, get_settings
from .routers import analysis, cogo, coords, instruments, parcels, setout, surfaces
from .security import (
    BodySizeLimitMiddleware,
    JsonNumberSafetyMiddleware,
    RateLimiter,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    run_guarded,
    run_killable,
)

log = logging.getLogger("atsurvey.api")
settings = get_settings()  # validated at import: unsafe production config refuses to start
_production = settings.environment == "production"

app = FastAPI(
    title="ATSurvey Engine API",
    version=__version__,
    description="Parse total-station raw data, compute traverses and detail points, export results.",
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
)
app.state.rate_limiter = RateLimiter(settings)
# Added inner → outer: security headers and CORS also wrap 413/429 responses.
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(JsonNumberSafetyMiddleware)
app.add_middleware(BodySizeLimitMiddleware, settings=settings)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "X-Input-Hash", "Retry-After"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(cogo.router)
app.include_router(parcels.router)
app.include_router(surfaces.router)
app.include_router(setout.router)
app.include_router(coords.router)
app.include_router(analysis.router)
app.include_router(instruments.router)

SettingsDep = Annotated[Settings, Depends(get_settings)]
ComputeCaller = Annotated[Caller, Depends(require_compute)]


def _check_size(inp: ProjectInput, s: Settings) -> None:
    """Bound every dimension that drives computation time."""
    n = sum(len(x.observations) for x in inp.setups)
    limits = (
        ("observations", n, s.max_observations),
        ("setups", len(inp.setups), s.max_setups),
        ("control points", len(inp.control_points), s.max_control_points),
        ("traverses", len(inp.traverses), s.max_traverses),
        ("route points", max((len(t.route) for t in inp.traverses), default=0), s.max_route_points),
    )
    for label, value, limit in limits:
        if value > limit:
            raise HTTPException(413, f"Too many {label} ({value} > {limit})")


async def _run(fn, *args, timeout: float):
    return await run_guarded(get_settings(), fn, *args, timeout=timeout)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine_version": __version__, "parser_version": PARSER_VERSION}


class Me(BaseModel):
    user_id: str | None
    plan: Literal["anonymous", "free", "pro"]
    export_formats: list[str]


@app.get("/v1/me", response_model=Me)
async def me(
    caller: Annotated[Caller, Depends(get_caller)], s: SettingsDep, workspace_id: str | None = None
) -> Me:
    plan = await plan_for(caller, s, workspace_id)
    return Me(user_id=caller.user_id, plan=plan, export_formats=EXPORTS_BY_PLAN[plan])


@app.post("/v1/parse", response_model=ParseResult)
async def parse(
    caller: ComputeCaller,
    s: SettingsDep,
    file: Annotated[UploadFile, File()],
    angle_unit: Annotated[AngleUnit | None, Form()] = None,
    format: Annotated[FormatName | None, Form()] = None,
) -> ParseResult:
    limit = s.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "File too large")
    try:
        return await _run(
            lambda: parse_file(data, file.filename, fmt=format, angle_unit=angle_unit),
            timeout=s.compute_timeout_s,
        )
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/v1/compute", response_model=ProjectResult)
async def compute(inp: ProjectInput, caller: ComputeCaller, s: SettingsDep) -> ProjectResult:
    _check_size(inp, s)
    return await _run(compute_project, inp, timeout=s.compute_timeout_s)


class Suggestions(BaseModel):
    suggestions: list[TraverseSpec]


@app.post("/v1/suggest-traverses", response_model=Suggestions)
async def suggest(inp: ProjectInput, caller: ComputeCaller, s: SettingsDep) -> Suggestions:
    _check_size(inp, s)
    # route enumeration is input-dependent: run in a child process that is killed on timeout
    found = await run_killable(s, suggest_traverses, inp, timeout=s.suggest_timeout_s)
    return Suggestions(suggestions=found)


class ExportRequest(BaseModel):
    format: ExportFormat
    project_name: str = Field(default="project", max_length=200)
    input: ProjectInput
    options: ExportOptions = Field(default_factory=ExportOptions)
    workspace_id: str | None = None
    #: stored project being exported: recorded in its workspace audit log (signed-in callers)
    project_id: str | None = Field(default=None, max_length=64)


@app.post(
    "/v1/export",
    responses={200: {"content": {"application/octet-stream": {}}}},
    response_class=Response,
)
async def export_file(req: ExportRequest, caller: ComputeCaller, s: SettingsDep) -> Response:
    _check_size(req.input, s)
    plan = await plan_for(caller, s, req.workspace_id)
    if req.format not in EXPORTS_BY_PLAN[plan]:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            {"code": "plan_required", "plan": plan, "format": req.format},
        )
    result = await _run(compute_project, req.input, timeout=s.compute_timeout_s)
    data, filename, media = await _run(
        export,
        req.format,
        req.project_name,
        req.input,
        result,
        req.options,
        timeout=s.compute_timeout_s,
    )
    await log_export(caller, s, req.project_id, req.format)
    ascii_name = filename.encode("ascii", "ignore").decode() or "export"
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            ),
            "X-Input-Hash": result.input_hash,
        },
    )


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError) -> JSONResponse:
    # engine ValueErrors describe bad input (degenerate geometry, units); keep them short
    return JSONResponse(status_code=422, content={"detail": str(exc)[:500]})


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    # never leak stack traces or internals; details go to the server log only
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})
