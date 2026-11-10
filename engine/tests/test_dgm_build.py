"""ΔΓΜ builder: subdivision, merge and correction on a synthetic cadastral diagram.

Truths: the sample ΚΔ (core/dgm/samples.py) has known vertices; areas are checked against an
independent shoelace in exact rational arithmetic (fractions.Fraction) and the invariants
Σ PST_KAEK = Σ DGM_PROP_FINAL and final = cadastral − ΣA + ΣΔ.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from atsurvey.core.dgm import DgmRequest, build_dgm
from atsurvey.core.dgm.models import DgmResult
from atsurvey.core.dgm.samples import KAEK_A, KAEK_B, KAEK_C, POINTS, sample_parcels
from atsurvey.core.messages import EL, localize

P = POINTS


def lerp(a, b, t):
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def v(name, xy):
    return {"name": name, "x": xy[0], "y": xy[1]}


def exact_area(coords) -> Fraction:
    n = len(coords)
    s = sum(
        Fraction(coords[i][0]) * Fraction(coords[(i + 1) % n][1])
        - Fraction(coords[(i + 1) % n][0]) * Fraction(coords[i][1])
        for i in range(n)
    )
    return Fraction(abs(s)) / 2


def codes(res: DgmResult, severity: str | None = None) -> list[str]:
    return [i.code for i in res.issues if severity is None or i.severity == severity]


def layer(res: DgmResult, name: str):
    return [p for p in res.polygons if p.layer == name]


def assert_localized(res: DgmResult) -> None:
    for i in res.issues:
        if i.code.startswith("DGM_"):
            assert i.code in EL
            assert localize(i, "el") != i.message, i.code


# ------------------------------------------------------------------------- subdivision

N_S_LINE = [v("T1", (476215.0, 4205103.0)), v("T2", (476215.5, 4205137.0))]


def subdivision(**kw) -> DgmResult:
    ps = sample_parcels()
    args = {
        "mode": "subdivision",
        "parcels": [ps[0]],
        "partition_lines": [{"vertices": N_S_LINE}],
        "topo_prop": [ps[0]],
    }
    args.update(kw)
    return build_dgm(DgmRequest.model_validate(args))


def test_subdivision_parts_tile_the_cadastral_parcel_exactly():
    res = subdivision()
    assert res.ok, codes(res)
    parts = layer(res, "DGM_PROP_FINAL")
    assert len(parts) == 2
    pst = [(P[n][0], P[n][1]) for n in ("1", "2", "3", "4")]
    total = sum(exact_area([(q.x, q.y) for q in p.vertices]) for p in parts)
    # the cut points are float64 roundings: the parts sum to the parcel within float noise
    assert float(total) == pytest.approx(float(exact_area(pst)), abs=1e-6)
    assert res.total_after == pytest.approx(res.total_before, abs=1e-6)
    # original cadastral vertices keep their exact coordinates
    names = {q.name: (q.x, q.y) for p in parts for q in p.vertices}
    for n in ("1", "2", "3", "4"):
        assert names[n] == P[n]
    # the two new points are shared bit-for-bit and lie on the parcel sides 1-2 and 4-3
    new = [pt for pt in res.points if pt.new]
    assert len(new) == 2
    shared = [set((q.x, q.y) for q in p.vertices) for p in parts]
    for pt in new:
        assert all((pt.x, pt.y) in s for s in shared)
    assert "DGM_LINE_EXTENDED" in codes(res)
    assert_localized(res)


def test_line_xm_is_clipped_to_the_parcel_and_ends_on_the_new_points():
    line = [v("T1", (476215.0, 4205090.0)), v("T2", (476215.5, 4205150.0))]  # crosses beyond
    res = subdivision(partition_lines=[{"vertices": line}])
    assert res.ok
    (xm,) = [ln for ln in res.lines if ln.layer == "LINE_XM"]
    new = {(pt.x, pt.y) for pt in res.points if pt.new}
    assert {(xm.vertices[0].x, xm.vertices[0].y), (xm.vertices[-1].x, xm.vertices[-1].y)} == new
    assert "DGM_LINE_EXTENDED" not in codes(res)


def test_partition_line_is_respected_regardless_of_area():
    # same line, different requested labels: areas come from the line only
    res = subdivision(part_labels=["Α", "Β"])
    a, b = layer(res, "DGM_PROP_FINAL")
    assert {a.label, b.label} == {"Α", "Β"}
    assert a.area + b.area == pytest.approx(res.total_before, abs=1e-6)


def test_three_parts_with_a_t_shaped_partition():
    l1 = [v("A1", (476215.0, 4205103.0)), v("A2", (476215.5, 4205137.0))]
    # second line from the first line eastwards: ends on l1 (inside the parcel), extended east
    mid = lerp((476215.0, 4205103.0), (476215.5, 4205137.0), 0.5)
    l2 = [v("B1", mid), v("B2", (476225.0, 4205120.0))]
    res = subdivision(partition_lines=[{"vertices": l1}, {"vertices": l2}])
    assert res.ok, codes(res)
    parts = layer(res, "DGM_PROP_FINAL")
    assert len(parts) == 3
    assert sum(p.area for p in parts) == pytest.approx(res.total_before, abs=1e-6)


def test_line_that_does_not_divide_is_an_error():
    res = subdivision(
        partition_lines=[
            {"vertices": [v("X", (476300.0, 4205300.0)), v("Y", (476310.0, 4205310.0))]}
        ],
        extend_lines=False,
    )
    assert not res.ok
    assert "DGM_LINE_NO_SPLIT" in codes(res, "error")


def test_dangling_partition_line_warns():
    line = [v("T1", (476215.0, 4205090.0)), v("T2", (476215.5, 4205150.0))]
    stub = [v("S1", (476220.0, 4205120.0)), v("S2", (476225.0, 4205121.0))]  # inside, no cut
    res = subdivision(partition_lines=[{"vertices": line}, {"vertices": stub}], extend_lines=False)
    assert res.ok
    assert "DGM_LINE_DANGLING" in codes(res, "warning")


def test_subdivision_compares_parts_with_the_survey_and_the_tolerance():
    survey_parts = [
        {
            "label": "1",
            "vertices": [
                v("1", P["1"]),
                v("x", (476215.0, 4205100.85)),
                v("y", (476215.5, 4205139.9)),
                v("4", P["4"]),
            ],
        },
    ]
    res = subdivision(topo_prop_new=survey_parts, tolerance={"kind": "cadastre", "u0": 0.5})
    survey = [c for c in res.comparisons if c.against == "survey" and c.kaek is None]
    assert len(survey) == 1
    c = survey[0]
    assert c.tolerance == pytest.approx(0.5 * c.perimeter * (1 + 0.5 / math.sqrt(c.cadastre_area)))
    assert c.within is True


# ------------------------------------------------------------------------------- merge


def test_merge_unites_two_parcels_and_draws_the_abolished_boundary():
    ps = sample_parcels()
    res = build_dgm(DgmRequest(mode="merge", parcels=ps[:2], topo_prop=[ps[0]]))
    assert res.ok, codes(res)
    (merged,) = layer(res, "DGM_PROP_FINAL")
    assert merged.area == pytest.approx(sum(p.area for p in layer(res, "PST_KAEK")), abs=1e-9)
    assert {q.name for q in merged.vertices} == {"1", "2", "3", "4", "7", "9"}
    (xm,) = [ln for ln in res.lines if ln.layer == "LINE_XM"]
    assert {q.name for q in xm.vertices} == {"2", "3"}


def test_merge_of_non_adjacent_parcels_fails():
    ps = sample_parcels()
    far = ps[1].model_copy(
        update={"vertices": [q.model_copy(update={"x": q.x + 500}) for q in ps[1].vertices]}
    )
    res = build_dgm(DgmRequest(mode="merge", parcels=[ps[0], far]))
    assert not res.ok
    assert "PARCEL_MERGE_NOT_ADJACENT" in codes(res)


# ---------------------------------------------------------------------------- correction


def correction_request(**kw) -> DgmRequest:
    ps = sample_parcels()
    p2n, p3n = lerp(P["2"], P["9"], 0.1), lerp(P["3"], P["7"], 0.1)
    p1a, p1b = lerp(P["1"], P["2"], 0.3), lerp(P["1"], P["4"], 0.3)
    finals = [
        {
            "kaek": KAEK_A,
            "vertices": [
                v("a", p1a),
                v("2", P["2"]),
                v("2n", p2n),
                v("3n", p3n),
                v("3", P["3"]),
                v("4", P["4"]),
                v("b", p1b),
            ],
        },
        {"kaek": KAEK_B, "vertices": [v("2n", p2n), v("9", P["9"]), v("7", P["7"]), v("3n", p3n)]},
        # C unchanged: its south side 3→7 now carries 3n (healed automatically)
        {
            "kaek": KAEK_C,
            "vertices": [
                v("4", P["4"]),
                v("3", P["3"]),
                v("7", P["7"]),
                v("8", P["8"]),
                v("5", P["5"]),
            ],
        },
        {"kaek": None, "label": "ΝΕΟ", "vertices": [v("1", P["1"]), v("a", p1a), v("b", p1b)]},
    ]
    args = {
        "mode": "correction",
        "parcels": ps,
        "subjects": [KAEK_A],
        "finals": finals,
        "topo_prop": [ps[0]],
    }
    args.update(kw)
    return DgmRequest.model_validate(args)


def test_correction_change_table_and_invariants():
    res = build_dgm(correction_request())
    assert res.ok, codes(res)
    assert res.total_after == pytest.approx(res.total_before, abs=1e-6)
    a = [c for c in res.changes if c.kind == "A"]
    d = [c for c in res.changes if c.kind == "D"]
    assert [c.part for c in a] == ["A1"] and [c.part for c in d] == ["Δ1"]
    assert a[0].from_kaek == KAEK_A and a[0].to_kaek == "ΝΕΟ"
    assert d[0].from_kaek == KAEK_B and d[0].to_kaek == KAEK_A
    assert a[0].description[0] == a[0].description[-1]
    # truths: A1 is the triangle 1-a-b; Δ1 the strip 2-2n-3n-3 (exact rational shoelace)
    tri = [P["1"], lerp(P["1"], P["2"], 0.3), lerp(P["1"], P["4"], 0.3)]
    strip = [P["2"], lerp(P["2"], P["9"], 0.1), lerp(P["3"], P["7"], 0.1), P["3"]]
    assert a[0].area == pytest.approx(float(exact_area(tri)), abs=1e-6)
    assert d[0].area == pytest.approx(float(exact_area(strip)), abs=1e-6)
    pst_a = next(p for p in layer(res, "PST_KAEK") if p.kaek == KAEK_A)
    fin_a = next(p for p in layer(res, "DGM_PROP_FINAL") if p.kaek == KAEK_A)
    assert fin_a.area == pytest.approx(pst_a.area - a[0].area + d[0].area, abs=1e-6)
    # the AREA layers mirror the change table
    assert [p.label for p in layer(res, "AREA_A")] == ["A1"]
    assert [p.label for p in layer(res, "AREA_D")] == ["Δ1"]
    # C got the shared vertex 3n inserted (T-junction healed)
    fin_c = next(p for p in layer(res, "DGM_PROP_FINAL") if p.kaek == KAEK_C)
    assert "3n" in [q.name for q in fin_c.vertices]
    assert "DGM_TJUNCTION_FIXED" in codes(res)
    assert_localized(res)


def test_correction_areas_table_and_tolerance_against_the_cadastral_perimeter():
    res = build_dgm(correction_request(tolerance={"kind": "cadastre", "u0": 0.5}))
    rows = {r.kaek: r for r in res.areas}
    assert rows[KAEK_C].difference == pytest.approx(0.0, abs=1e-6)
    new = [r for r in res.areas if r.kaek is None]
    assert len(new) == 1 and new[0].before is None
    finals = {c.kaek: c for c in res.comparisons if c.against == "final"}
    pst_b = next(p for p in layer(res, "PST_KAEK") if p.kaek == KAEK_B)
    assert finals[KAEK_B].perimeter == pytest.approx(pst_b.perimeter)
    assert finals[KAEK_B].within is False  # B loses ~125 m², tolerance ~72 m²
    assert "DGM_AREA_TOLERANCE" in codes(res, "warning")


def test_correction_snaps_final_vertices_to_the_cadastre():
    req = correction_request(snap_tolerance=0.005)
    moved = req.finals[1].vertices[1].model_copy(update={"x": P["9"][0] + 0.003})
    req.finals[1].vertices[1] = moved
    res = build_dgm(req)
    assert res.ok, codes(res)
    fin_b = next(p for p in layer(res, "DGM_PROP_FINAL") if p.kaek == KAEK_B)
    assert any((q.x, q.y) == P["9"] for q in fin_b.vertices)
    assert "DGM_SNAPPED" in codes(res, "info")


def test_correction_total_area_mismatch_is_an_error():
    req = correction_request()
    req.finals.pop()  # the new parcel is missing: totals differ by the triangle
    res = build_dgm(req)
    assert not res.ok
    assert "DGM_TOTAL_AREA" in codes(res, "error")


def test_correction_requires_known_subjects_and_finals():
    res = build_dgm(correction_request(subjects=["999999999999"]))
    assert "DGM_SUBJECT_UNKNOWN" in codes(res, "error")
    res = build_dgm(correction_request(finals=[]))
    assert "DGM_FINALS_REQUIRED" in codes(res, "error")
    req = correction_request()
    req.finals[0].kaek = "123456789012"
    assert "DGM_FINAL_UNKNOWN_KAEK" in codes(build_dgm(req), "error")


def test_unchanged_finals_report_no_change():
    ps = sample_parcels()
    finals = [{"kaek": p.kaek, "vertices": [q.model_dump() for q in p.vertices]} for p in ps]
    res = build_dgm(
        DgmRequest.model_validate(
            {
                "mode": "correction",
                "parcels": ps,
                "subjects": [KAEK_A],
                "finals": finals,
                "topo_prop": [ps[0]],
            }
        )
    )
    assert "DGM_NO_CHANGE" in codes(res, "error")


# --------------------------------------------------------------------------- inputs


def test_missing_and_repeated_kaek_are_errors():
    ps = sample_parcels()
    ps[1].kaek = None
    ps[2].kaek = KAEK_A
    res = build_dgm(DgmRequest(mode="merge", parcels=ps))
    assert {"DGM_KAEK_MISSING", "DGM_KAEK_REPEATED"} <= set(codes(res, "error"))


def test_invalid_cadastral_polygon_is_reported():
    ps = sample_parcels()
    bow = ps[0].model_copy(update={"vertices": [ps[0].vertices[k] for k in (0, 2, 1, 3)]})
    res = build_dgm(
        DgmRequest.model_validate(
            {"mode": "subdivision", "parcels": [bow], "partition_lines": [{"vertices": N_S_LINE}]}
        )
    )
    assert "DGM_PARCEL_INVALID" in codes(res, "error")
    assert "PARCEL_SELF_INTERSECTION" in codes(res)


def test_request_bounds_are_enforced():
    ps = sample_parcels()
    with pytest.raises(ValueError):
        DgmRequest(mode="merge", parcels=ps * 20)
    with pytest.raises(ValueError):
        DgmRequest(mode="merge", parcels=ps, snap_tolerance=1.0)


def test_deed_keeps_only_the_changed_parcels_in_pst_kaek():
    # the whole ΚΔ is loaded: neighbours go to the free context layer, so that
    # union(DGM_PROP_FINAL) == union(PST_KAEK) holds ([S5] ΣΤ.10 case 3)
    res = subdivision(parcels=sample_parcels(), subject=KAEK_A)
    assert res.ok, codes(res)
    assert [p.kaek for p in layer(res, "PST_KAEK")] == [KAEK_A]
    assert {p.kaek for p in layer(res, "ATS_NEIGHBOURS")} == {KAEK_B, KAEK_C}
    assert [a.kaek for a in res.areas if a.kaek] == [KAEK_A]  # + the two parts (no KAEK yet)
    assert len(res.areas) == 3
    res = build_dgm(DgmRequest(mode="merge", parcels=sample_parcels(), merge=[KAEK_A, KAEK_B]))
    assert res.ok, codes(res)
    assert {p.kaek for p in layer(res, "ATS_NEIGHBOURS")} == {KAEK_C}
