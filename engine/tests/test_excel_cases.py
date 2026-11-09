"""Agreement with the reference Excel workbooks (fixtures/excel/*.json)."""

import json
from pathlib import Path

import pytest

from atsurvey import ProjectInput, compute_project
from atsurvey.core.units import rad_to_cc

CASES = sorted((Path(__file__).parent / "fixtures" / "excel").glob("*.json"))


@pytest.mark.skipif(not CASES, reason="no Excel validation cases yet")
@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_matches_workbook(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    tol = {"xy_m": 1e-4, "z_m": 1e-4, "angular_cc": 0.1, "misclosure_m": 1e-4}
    tol.update(case.get("tolerance", {}))
    result = compute_project(ProjectInput.model_validate(case["input"]))
    points = {p.name: p for p in result.points}
    failures = []
    for name, (x, y, z) in case["expected"].get("points", {}).items():
        p = points.get(name)
        if p is None:
            failures.append(f"{name}: not computed")
            continue
        if abs(p.x - x) > tol["xy_m"] or abs(p.y - y) > tol["xy_m"]:
            failures.append(f"{name}: dX={p.x - x:+.4f} dY={p.y - y:+.4f}")
        if z is not None and (p.z is None or abs(p.z - z) > tol["z_m"]):
            failures.append(f"{name}: dZ={(p.z or 0) - z:+.4f}")
    trs = {t.name: t for t in result.traverses}
    for name, exp in case["expected"].get("traverses", {}).items():
        t = trs.get(name)
        if t is None:
            failures.append(f"traverse {name}: not computed")
            continue
        if "angular_cc" in exp and t.angular_misclosure is not None:
            got = rad_to_cc(t.angular_misclosure)
            if abs(got - exp["angular_cc"]) > tol["angular_cc"]:
                failures.append(f"{name}: wβ {got:+.1f} cc vs {exp['angular_cc']:+.1f}")
        for key in ("wx", "wy", "wz"):
            got = getattr(t, key)
            if key in exp and got is not None and abs(got - exp[key]) > tol["misclosure_m"]:
                failures.append(f"{name}: {key} {got:+.4f} vs {exp[key]:+.4f}")
    assert not failures, "\n".join(failures)
