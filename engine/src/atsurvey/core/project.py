"""Project-level orchestration: control → traverses (dependency order) → detail."""

from __future__ import annotations

import hashlib
import re

from .. import __version__
from .detail import compute_detail
from .geodesy import grid_distance
from .issues import IssueSink
from .models import ProjectInput, ProjectResult, ResultPoint, Summary, TraverseResult
from .reduce import ObservationIndex, reduce_setups
from .traverse import KnownPoint, compute_traverse, plan_traverse, traverse_name


def natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def input_hash(inp: ProjectInput) -> str:
    return hashlib.sha256(inp.model_dump_json().encode()).hexdigest()


def compute_project(inp: ProjectInput) -> ProjectResult:
    sink = IssueSink()
    rs = inp.settings.reduction
    tol = inp.settings.tolerances

    known: dict[str, KnownPoint] = {}
    for cp in inp.control_points:
        name = cp.name.strip()
        if name in known:
            sink.warning(
                "CONTROL_DUPLICATE",
                f"Control point {name} is defined more than once; the first definition is used",
                point=name,
            )
            continue
        known[name] = KnownPoint(name=name, x=cp.x, y=cp.y, z=cp.z, kind="control", code=cp.code)

    reduced = reduce_setups(inp.setups, rs, tol, sink)
    index = ObservationIndex(reduced)

    # ---- traverses, resolved in dependency order --------------------------------------
    pending = [t for t in inp.traverses if t.enabled]
    reserved: set[str] = set()
    for t in pending:
        reserved.update(p for p in t.route if p not in known)
    results: dict[int, TraverseResult] = {}
    traverse_points: list[KnownPoint] = []
    progress = True
    while pending and progress:
        progress = False
        for spec in list(pending):
            plan = plan_traverse(spec, known, sink)
            if plan is None:
                if len([p for p in spec.route if p.strip()]) < 3:
                    pending.remove(spec)
                continue
            pending.remove(spec)
            progress = True
            res, new_pts = compute_traverse(plan, index, known, rs, tol, sink)
            results[id(spec)] = res
            for p in new_pts:
                if p.name in known:
                    other = known[p.name]
                    d = grid_distance(other.x, other.y, p.x, p.y)
                    sink.warning(
                        "POINT_CONFLICT",
                        f"Point {p.name} computed by {plan.name} differs by {d * 1000:.0f} mm from "
                        f"its earlier determination ({other.source or other.kind}); the earlier "
                        f"value is kept",
                        traverse=spec.id or plan.name,
                        point=p.name,
                        diff_mm=round(d * 1000, 1),
                    )
                    continue
                known[p.name] = p
                traverse_points.append(p)
    for spec in pending:
        route = [p.strip() for p in spec.route if p.strip()]
        missing = [p for p in (route[:2] + route[-2:]) if p not in known]
        sink.error(
            "TRAVERSE_UNRESOLVED",
            f"Traverse {traverse_name(spec)} cannot start: neither end has two known points "
            f"(missing {', '.join(dict.fromkeys(missing))})",
            traverse=spec.id or traverse_name(spec),
            missing=list(dict.fromkeys(missing)),
        )
    ordered_results = [results[id(t)] for t in inp.traverses if id(t) in results]

    # ---- detail -------------------------------------------------------------------------
    shots, orientations, detail_points = [], [], []
    if inp.settings.compute_detail:
        shots, orientations, detail_points = compute_detail(reduced, known, reserved, rs, tol, sink)

    # ---- assemble -----------------------------------------------------------------------
    points: list[ResultPoint] = []
    for kp in known.values():
        if kp.kind == "control":
            points.append(_rp(kp))
    points.extend(_rp(kp) for kp in traverse_points)
    radiated = [kp for kp in known.values() if kp.kind == "detail"]
    seen = {p.name for p in points}
    detail_all = [kp for kp in radiated + detail_points if kp.name not in seen]
    unique_detail = {kp.name: kp for kp in detail_all}
    points.extend(
        _rp(kp) for kp in sorted(unique_detail.values(), key=lambda k: natural_key(k.name))
    )

    extent = None
    if points:
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        extent = (min(xs), min(ys), max(xs), max(ys))
    summary = Summary(
        n_control=sum(p.kind == "control" for p in points),
        n_traverse_points=sum(p.kind == "traverse" for p in points),
        n_detail_points=sum(p.kind == "detail" for p in points),
        n_traverses=len(ordered_results),
        n_traverses_ok=sum(r.status == "ok" for r in ordered_results),
        n_errors=sum(i.severity == "error" for i in sink.items),
        n_warnings=sum(i.severity == "warning" for i in sink.items),
        extent=extent,
    )
    return ProjectResult(
        engine_version=__version__,
        input_hash=input_hash(inp),
        points=points,
        traverses=ordered_results,
        detail=shots,
        orientations=orientations,
        issues=sink.items,
        summary=summary,
    )


def _rp(kp: KnownPoint) -> ResultPoint:
    return ResultPoint(
        name=kp.name,
        x=kp.x,
        y=kp.y,
        z=kp.z,
        kind=kp.kind,  # type: ignore[arg-type]
        code=kp.code,
        source=kp.source,
        n=len(kp.source.split(", ")) if kp.kind == "detail" and kp.source else 1,
    )
