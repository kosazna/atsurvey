"""Pre-submission validator for any DXF (made by ATSurvey or in CAD).

Implements the checks the Cadastre's system runs ([S1] §4.3, §4.5, §5; [S5] ΣΤ): file name and
size, DXF version, layer names, required layers per diagram kind with the ⇔ rules, entity
types per layer (Table I), forbidden entities (MTEXT, blocks, hatches, xrefs, images), 2D only,
KAEK text inside its PST_KAEK polygon, duplicates, overlaps, gaps, missing shared vertices and
the PST_KAEK ↔ DGM_PROP_FINAL outline. Every problem carries the layer, the entity handle and
a coordinate pair. The Cadastre's own system is authoritative: this is a pre-check.
"""

from __future__ import annotations

import hashlib

from ..issues import IssueSink
from ..models import Issue
from .dxf_load import MAX_ENTITIES, DxfLoadError, load_dxf
from .models import CheckResult, LayerSummary, PreviewShape, ValidationReport
from .spec import (
    ACCEPTED_VERSIONS,
    BY_NAME,
    MAX_FILE_BYTES,
    PREFERRED_VERSIONS,
    RECOMMENDED_FILE_BYTES,
    DiagramKind,
    check_file_name,
)
from .structure import scan_doc
from .topology import check_drawing

#: Order of the checklist shown to the user
CHECK_ORDER = (
    "file",
    "dxf_version",
    "layer_names",
    "layers_required",
    "layers_kind",
    "entity_types",
    "forbidden",
    "elevation",
    "kaek_text",
    "polygons_valid",
    "duplicates",
    "overlaps",
    "gaps",
    "shared_vertices",
    "outline",
)
MAX_PREVIEW_SHAPES = 3000
MAX_PREVIEW_COORDS = 100_000


def validate_dxf(data: bytes, filename: str | None, kind: DiagramKind) -> ValidationReport:
    sha = hashlib.sha512(data).hexdigest()
    checks: dict[str, list[Issue]] = {"file": _file_checks(data, filename, kind)}
    version: str | None = None
    layers: list[LayerSummary] = []
    preview: list[PreviewShape] = []
    truncated = False
    try:
        loaded = load_dxf(data)
    except DxfLoadError as exc:
        sink = IssueSink()
        sink.error("DGM_DXF_UNREADABLE", str(exc), reason=str(exc))
        checks["dxf_version"] = sink.items
        return _report(kind, filename, data, sha, None, checks, [], [], False)
    doc = loaded.doc
    version = str(doc.dxfversion)
    checks["dxf_version"] = _version_checks(doc, loaded.recovered)
    if len(doc.modelspace()) > MAX_ENTITIES:
        sink = IssueSink()
        sink.error(
            "DGM_TOO_MANY_ENTITIES", f"More than {MAX_ENTITIES} entities", limit=MAX_ENTITIES
        )
        checks["dxf_version"].extend(sink.items)
        return _report(kind, filename, data, sha, version, checks, [], [], False)
    scan = scan_doc(doc, kind)
    for key, sink in scan.checks.items():
        checks.setdefault(key, []).extend(sink.items)
    for key, issues in check_drawing(scan.drawing, kind).items():
        checks.setdefault(key, []).extend(issues)
    layers = [
        LayerSummary(
            name=name, table_no=BY_NAME[name].no if name in BY_NAME else None, counts=dict(c)
        )
        for name, c in sorted(
            scan.counts.items(),
            key=lambda kv: (BY_NAME[kv[0]].no if kv[0] in BY_NAME else 99, kv[0]),
        )
    ]
    preview, truncated = _preview(scan.drawing.shapes)
    return _report(kind, filename, data, sha, version, checks, layers, preview, truncated)


def _report(
    kind: DiagramKind,
    filename: str | None,
    data: bytes,
    sha: str,
    version: str | None,
    checks: dict[str, list[Issue]],
    layers: list[LayerSummary],
    preview: list[PreviewShape],
    truncated: bool,
) -> ValidationReport:
    results: list[CheckResult] = []
    skip_after_load = "polygons_valid" not in checks
    for cid in CHECK_ORDER:
        if cid == "outline" and kind == "topo":
            continue
        issues = checks.get(cid)
        if issues is None:
            status = "skip" if skip_after_load else "pass"
            results.append(CheckResult(id=cid, status=status, issues=[]))  # type: ignore[arg-type]
            continue
        sev = {i.severity for i in issues}
        status = "fail" if "error" in sev else "warn" if "warning" in sev else "pass"
        results.append(CheckResult(id=cid, status=status, issues=issues))  # type: ignore[arg-type]
    ok = all(r.status != "fail" for r in results) and not skip_after_load
    return ValidationReport(
        kind=kind,
        filename=filename,
        size=len(data),
        sha512=sha,
        dxf_version=version,
        ok=ok,
        checks=results,
        layers=layers,
        preview=preview,
        preview_truncated=truncated,
    )


def _file_checks(data: bytes, filename: str | None, kind: DiagramKind) -> list[Issue]:
    sink = IssueSink()
    if filename:
        for code, params in check_file_name(filename, kind):
            if code.endswith("_WARN"):
                sink.warning(code, f"File name {filename}: {code}", **params)
            else:
                sink.error(code, f"File name {filename}: {code}", **params)
    size_mb = round(len(data) / (1024 * 1024), 2)
    if len(data) > MAX_FILE_BYTES:
        sink.error(
            "DGM_FILE_TOO_LARGE",
            f"{size_mb} MB: DXF and PDF together must not exceed 10 MB",
            mb=size_mb,
        )
    elif len(data) > RECOMMENDED_FILE_BYTES:
        sink.warning("DGM_FILE_LARGE", f"{size_mb} MB: under 6 MB is recommended", mb=size_mb)
    return sink.items


def _version_checks(doc, recovered: int) -> list[Issue]:
    sink = IssueSink()
    v = str(doc.dxfversion)
    if v not in ACCEPTED_VERSIONS:
        sink.error("DGM_DXF_VERSION", f"DXF version {v} is not accepted (2000–2014)", version=v)
    elif v not in PREFERRED_VERSIONS:
        sink.warning(
            "DGM_DXF_VERSION_OLD",
            f"DXF {ACCEPTED_VERSIONS[v]}: the specification asks for 2004–2014",
            version=ACCEPTED_VERSIONS[v],
        )
    units = doc.header.get("$INSUNITS", 0)
    if units != 6:
        sink.warning(
            "DGM_UNITS", f"$INSUNITS = {units}; the drawing must be in metres (6)", units=units
        )
    if recovered:
        sink.warning(
            "DGM_DXF_RECOVERED", f"{recovered} structural errors were recovered", count=recovered
        )
    return sink.items


def _preview(shapes) -> tuple[list[PreviewShape], bool]:
    out: list[PreviewShape] = []
    n = 0
    for s in shapes:
        if s.form not in ("polygon", "polyline"):
            continue
        if len(out) >= MAX_PREVIEW_SHAPES or n + len(s.coords) > MAX_PREVIEW_COORDS:
            return out, True
        out.append(PreviewShape(layer=s.layer, closed=s.form == "polygon", coords=list(s.coords)))
        n += len(s.coords)
    return out, False
