"""/v1/dgm/* endpoints: Διάγραμμα Γεωμετρικών Μεταβολών (Hellenic Cadastre). See docs/dgm.md.

* ``POST /v1/dgm/kd``       multipart ΚΔ DXF → cadastral parcels with KAEK
* ``POST /v1/dgm/build``    DgmRequest → geometry, tables, issues
* ``POST /v1/dgm/validate`` multipart DXF + diagram kind → checklist (any CAD drawing)
* ``POST /v1/dgm/export``   DgmRequest → DXF 2004 (Pro, like every DXF export); the SHA-512
  of the file is returned in ``X-DXF-SHA512``
* ``POST /v1/dgm/hash-pdf`` SHA-512 → the unsigned PDF to be signed by the engineer (Pro)
* ``GET  /v1/dgm/sample``   synthetic cadastral parcels for trying the tool

Uploads are bounded (``MAX_DXF_BYTES`` and the server's upload limit); computations run in the
guarded worker pool with the compute timeout. Geometry problems are issues in a 200 response.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from atsurvey.core.dgm import build_dgm
from atsurvey.core.dgm.hashpdf import hash_pdf, sha512_hex
from atsurvey.core.dgm.kd_reader import read_kd
from atsurvey.core.dgm.models import DgmRequest, DgmResult, KdReadResult, ValidationReport
from atsurvey.core.dgm.samples import sample_parcels
from atsurvey.core.dgm.spec import DiagramKind, check_file_name, suggest_file_name
from atsurvey.core.dgm.validate import validate_dxf
from atsurvey.core.dgm.writer import write_dgm_dxf
from atsurvey.core.parcels_models import Parcel

from .. import auth
from ..audit import log_export
from ..auth import Caller, require_compute
from ..config import Settings, get_settings
from ..security import run_guarded

router = APIRouter(prefix="/v1", tags=["dgm"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

#: Uploaded DXF files above this are refused outright (the Cadastre's limit is 10 MB for DXF
#: and PDF together; larger files are still read up to here so the report can say so).
MAX_DXF_BYTES = 16 * 1024 * 1024


class DgmExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: DgmRequest
    filename: str | None = Field(default=None, max_length=64)
    workspace_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)


class HashPdfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha512: str = Field(min_length=128, max_length=128, pattern=r"^[0-9a-fA-F]{128}$")
    workspace_id: str | None = Field(default=None, max_length=64)


async def _run(s: Settings, fn: Callable[..., Any], *args: Any) -> Any:
    try:
        return await run_guarded(s, fn, *args, timeout=s.compute_timeout_s)
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:500]) from exc


async def _read_upload(file: UploadFile, s: Settings) -> bytes:
    limit = min(MAX_DXF_BYTES, s.max_upload_mb * 1024 * 1024)
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File too large (limit {limit // (1024 * 1024)} MB)")
    if not data:
        raise HTTPException(422, "Empty file")
    return data


async def _require_plan(caller: Caller, s: Settings, workspace_id: str | None, fmt: str) -> None:
    plan = await auth.plan_for(caller, s, workspace_id)
    if fmt not in auth.EXPORTS_BY_PLAN[plan]:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            {"code": "plan_required", "plan": plan, "format": fmt},
        )


def _attachment(data: bytes, filename: str, media: str, extra: dict[str, str]) -> Response:
    ascii_name = filename.encode("ascii", "ignore").decode() or "dgm.dxf"
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            ),
            **extra,
        },
    )


@router.get("/dgm/sample", response_model=list[Parcel])
async def sample(caller: ComputeCaller) -> list[Parcel]:
    """Three adjacent synthetic cadastral parcels (made-up KAEK and coordinates)."""
    return sample_parcels()


@router.post("/dgm/kd", response_model=KdReadResult)
async def kd(
    caller: ComputeCaller,
    s: SettingsDep,
    file: Annotated[UploadFile, File()],
    layer: Annotated[str | None, Form(max_length=255)] = None,
) -> KdReadResult:
    """Parcels and KAEK from a Κτηματογραφικό Διάγραμμα DXF (tolerant reader)."""
    data = await _read_upload(file, s)
    return await _run(s, read_kd, data, layer or None)


@router.post("/dgm/build", response_model=DgmResult)
async def build(req: DgmRequest, caller: ComputeCaller, s: SettingsDep) -> DgmResult:
    return await _run(s, build_dgm, req)


@router.post("/dgm/validate", response_model=ValidationReport)
async def validate(
    caller: ComputeCaller,
    s: SettingsDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[DiagramKind, Form()] = "deed",
) -> ValidationReport:
    """Pre-submission checks of any DXF; the Cadastre's own system is authoritative."""
    data = await _read_upload(file, s)
    name = (file.filename or "")[:255] or None
    return await _run(s, validate_dxf, data, name, kind)


def _export(req: DgmExportRequest) -> tuple[bytes, str, bool]:
    res = build_dgm(req.request)
    data = write_dgm_dxf(res, req.request.title)
    name = req.filename or ""
    if not name or check_file_name(name, res.kind):
        name = suggest_file_name(req.request.title.title or req.request.title.location, res.kind)
    return data, name, res.ok


@router.post(
    "/dgm/export",
    responses={200: {"content": {"application/dxf": {}}}},
    response_class=Response,
)
async def export(req: DgmExportRequest, caller: ComputeCaller, s: SettingsDep) -> Response:
    await _require_plan(caller, s, req.workspace_id, "dxf")
    data, name, ok = await _run(s, _export, req)
    await log_export(caller, s, req.project_id, "dgm_dxf")
    headers = {"X-DXF-SHA512": sha512_hex(data), "X-DGM-Valid": "true" if ok else "false"}
    return _attachment(data, name, "application/dxf", headers)


@router.post(
    "/dgm/hash-pdf",
    responses={200: {"content": {"application/pdf": {}}}},
    response_class=Response,
)
async def hash_pdf_route(req: HashPdfRequest, caller: ComputeCaller, s: SettingsDep) -> Response:
    """The unsigned PDF holding only the SHA-512; the engineer signs it (we never sign)."""
    await _require_plan(caller, s, req.workspace_id, "pdf")
    pdf = await _run(s, hash_pdf, req.sha512)
    return _attachment(pdf, "hash_sha512.pdf", "application/pdf", {})
