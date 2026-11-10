"""Parcel geometry and area comparison: closed-form truths (rectangles, triangles, circles)."""

from __future__ import annotations

import math

import pytest

from atsurvey.core.parcels import (
    AREA_TOLERANCE_PRESETS,
    analyze_parcel,
    area_tolerance,
    cadastre_tolerance,
    compare_areas,
    signed_area,
)
from atsurvey.core.parcels_models import (
    ArcSpec,
    AreaCompareRequest,
    AreaToleranceRule,
    Parcel,
    ParcelVertex,
)

E0, N0 = 476_000.0, 4_205_000.0  # ΕΓΣΑ87 magnitudes


def parcel(pts, arcs=None, **kw) -> Parcel:
    arcs = arcs or {}
    return Parcel(
        vertices=[ParcelVertex(name=n, x=x, y=y, arc=arcs.get(n)) for n, x, y in pts],
        **kw,
    )


RECT = [("A", 0, 0), ("B", 100, 0), ("C", 100, 50), ("D", 0, 50)]


def codes(issues) -> list[str]:
    return [i.code for i in issues]


# ------------------------------------------------------------------------------- geometry


def test_rectangle_area_perimeter_centroid_and_tables():
    g = analyze_parcel(parcel(RECT, label="Αγρός", kaek="050011234001"))
    assert g.valid and g.issues == []
    assert g.area == pytest.approx(5000.0, abs=1e-12)
    assert g.perimeter == pytest.approx(300.0, abs=1e-12)
    assert g.orientation == "counterclockwise"
    assert (g.centroid.x, g.centroid.y) == pytest.approx((50.0, 25.0))
    assert [(s.frm, s.to) for s in g.sides] == [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    assert [s.length for s in g.sides] == pytest.approx([100, 50, 100, 50])
    # azimuths clockwise from north: east = π/2, north = 0, west = 3π/2, south = π
    assert [s.azimuth for s in g.sides] == pytest.approx(
        [math.pi / 2, 0.0, 3 * math.pi / 2, math.pi]
    )
    assert g.kaek == "050011234001" and g.label == "Αγρός"


def test_triangle_at_egsa87_magnitudes_is_exact():
    pts = [("1", E0, N0), ("2", E0 + 30, N0), ("3", E0, N0 + 40)]
    g = analyze_parcel(parcel(pts))
    assert g.area == pytest.approx(600.0, abs=1e-9)
    assert g.perimeter == pytest.approx(120.0, abs=1e-9)
    assert g.centroid.x == pytest.approx(E0 + 10, abs=1e-9)


def test_clockwise_orientation_and_closing_vertex():
    pts = [*RECT[::-1], RECT[-1]]  # D C B A D: clockwise, closing vertex repeated
    g = analyze_parcel(parcel(pts))
    assert g.orientation == "clockwise"
    assert len(g.vertices) == 4
    assert g.area == pytest.approx(5000.0)
    assert g.issues == []


def test_duplicate_consecutive_vertex_is_removed_with_warning():
    pts = [RECT[0], ("A2", 0, 0), *RECT[1:]]
    g = analyze_parcel(parcel(pts))
    assert codes(g.issues) == ["PARCEL_DUPLICATE_VERTEX"]
    assert g.issues[0].params == {"point": "A2", "other": "A"}
    assert g.area == pytest.approx(5000.0) and g.valid


def test_duplicate_name_with_different_coordinates_warns():
    pts = [("A", 0, 0), ("B", 10, 0), ("A", 10, 10)]
    g = analyze_parcel(parcel(pts))
    assert "PARCEL_DUPLICATE_NAME" in codes(g.issues)


def test_too_few_vertices():
    g = analyze_parcel(parcel([("A", 0, 0), ("B", 1, 0)]))
    assert not g.valid and g.area is None
    assert codes(g.issues) == ["PARCEL_TOO_FEW_VERTICES"]


def test_zero_area_collinear():
    g = analyze_parcel(parcel([("A", 0, 0), ("B", 1, 0), ("C", 2, 0)]))
    assert not g.valid
    assert codes(g.issues)[-1] in ("PARCEL_ZERO_AREA", "PARCEL_SELF_INTERSECTION")


def test_bow_tie_is_self_intersecting():
    g = analyze_parcel(parcel([("A", 0, 0), ("B", 10, 10), ("C", 10, 0), ("D", 0, 10)]))
    assert not g.valid and g.area is None
    assert codes(g.issues) == ["PARCEL_SELF_INTERSECTION"]
    assert {g.issues[0].params["side_a"], g.issues[0].params["side_b"]} == {"A–B", "C–D"}


def test_vertex_touching_another_side_is_self_intersecting():
    pts = [("A", 0, 0), ("B", 10, 0), ("C", 10, 10), ("D", 5, 0.0), ("E", 0, 10)]
    g = analyze_parcel(parcel(pts))
    assert codes(g.issues) == ["PARCEL_SELF_INTERSECTION"]


def test_spike_folding_back_is_self_intersecting():
    pts = [("A", 0, 0), ("B", 10, 0), ("C", 20, 0), ("D", 15, 0), ("E", 0, 10)]
    g = analyze_parcel(parcel(pts))
    assert "PARCEL_SELF_INTERSECTION" in codes(g.issues)


def test_signed_area_helper():
    ring = [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0)]
    assert signed_area(ring) == pytest.approx(1.0)
    assert signed_area(ring[::-1]) == pytest.approx(-1.0)
    assert signed_area(ring[:2]) == 0.0


# ----------------------------------------------------------------------------------- arcs


@pytest.mark.parametrize(
    ("radius", "e0", "n0", "rel"),
    [
        (1.0, 0.0, 0.0, 1e-14),
        (12.5, 0.0, 0.0, 1e-14),
        (250.0, 0.0, 0.0, 1e-14),
        # at ΕΓΣΑ87 magnitudes the input coordinates themselves carry ~1e-10 m of rounding
        (12.5, E0, N0, 1e-9),
        (250.0, E0, N0, 1e-9),
    ],
)
def test_square_with_four_outward_arcs_is_a_circle(radius, e0, n0, rel):
    c = radius / math.sqrt(2)
    pts = [
        ("A", e0 + c, n0 - c),
        ("B", e0 + c, n0 + c),
        ("C", e0 - c, n0 + c),
        ("D", e0 - c, n0 - c),
    ]
    # counter-clockwise ring: outward = right of travel
    arc = ArcSpec(radius=radius, side="right")
    g = analyze_parcel(parcel(pts, arcs={n: arc for n, *_ in pts}))
    assert g.valid and g.has_arcs
    assert g.area == pytest.approx(math.pi * radius**2, rel=rel)
    assert g.perimeter == pytest.approx(2 * math.pi * radius, rel=rel)
    assert (g.centroid.x, g.centroid.y) == pytest.approx((e0, n0), abs=1e-8)
    side = g.sides[0]
    assert side.central_angle == pytest.approx(math.pi / 2)
    assert side.arc_length == pytest.approx(math.pi * radius / 2)


def test_half_disc_area_and_centroid():
    r = 10.0
    arc = ArcSpec(radius=r, side="right")
    g = analyze_parcel(parcel([("A", -r, 0), ("B", r, 0), ("C", 0, r)], arcs={"B": arc, "C": arc}))
    assert g.area == pytest.approx(math.pi * r * r / 2, rel=1e-13)
    assert g.centroid.y == pytest.approx(4 * r / (3 * math.pi), rel=1e-12)
    assert g.centroid.x == pytest.approx(0.0, abs=1e-12)


def test_inward_arc_removes_the_segment():
    r = 50.0
    # 100 × 100 square, side A→B replaced by an arc bulging into the parcel (left of travel)
    pts = [("A", 0, 0), ("B", 100, 0), ("C", 100, 100), ("D", 0, 100)]
    g = analyze_parcel(parcel(pts, arcs={"A": ArcSpec(radius=r, side="left")}))
    assert g.area == pytest.approx(10_000 - math.pi * r * r / 2, rel=1e-13)


def test_semicircle_on_a_diameter_chord():
    r = 5.0
    arc = ArcSpec(radius=r, side="left")
    pts = [("A", 0, 0), ("B", 0, -10), ("C", -10, -10), ("D", -10, 0)]  # 10 × 10, clockwise
    g = analyze_parcel(parcel(pts, arcs={"D": arc}))  # D→A (east) bulges north: outwards
    assert g.area == pytest.approx(100 + math.pi * r * r / 2, rel=1e-14)
    assert g.sides[3].central_angle == pytest.approx(math.pi, rel=1e-15)


def test_major_arc_pacman():
    r = 20.0
    arc = ArcSpec(radius=r, side="left", large=True)
    g = analyze_parcel(parcel([("O", 0, 0), ("A", r, 0), ("B", 0, r)], arcs={"A": arc}))
    assert g.valid
    assert g.area == pytest.approx(0.75 * math.pi * r * r, rel=1e-13)
    assert g.perimeter == pytest.approx(2 * r + 1.5 * math.pi * r, rel=1e-13)
    assert g.orientation == "clockwise"


def test_arc_radius_smaller_than_half_chord():
    pts = [("A", 0, 0), ("B", 100, 0), ("C", 100, 100)]
    g = analyze_parcel(parcel(pts, arcs={"A": ArcSpec(radius=40, side="right")}))
    assert not g.valid
    assert codes(g.issues) == ["PARCEL_ARC_RADIUS"]


# ------------------------------------------------------------------------ area comparison


def test_compare_differences_and_percentages_without_rule():
    r = compare_areas(
        AreaCompareRequest(surveyed_area=1010.0, deed_area=1000.0, cadastre_area=995.0)
    )
    rows = {row.kind: row for row in r.rows}
    assert rows["surveyed_vs_deed"].difference == pytest.approx(10.0)
    assert rows["surveyed_vs_deed"].difference_percent == pytest.approx(1.0)
    assert rows["surveyed_vs_cadastre"].difference == pytest.approx(15.0)
    assert rows["cadastre_vs_deed"].difference == pytest.approx(-5.0)
    assert all(row.within is None and row.tolerance is None for row in r.rows)
    assert r.issues == []


@pytest.mark.parametrize(
    ("rule", "expected_t"),
    [
        (AreaToleranceRule(kind="fixed", value=12.0, source="σύμβαση"), 12.0),
        (AreaToleranceRule(kind="percent", value=2.0), 20.0),
        (AreaToleranceRule(kind="formula", a=1.0, b=0.5), 1.0 + 0.5 * math.sqrt(1000.0)),
    ],
)
def test_tolerance_rules(rule, expected_t):
    assert area_tolerance(rule, 1000.0) == pytest.approx(expected_t)
    r = compare_areas(AreaCompareRequest(surveyed_area=1015.0, deed_area=1000.0, tolerance=rule))
    row = r.rows[0]
    assert row.tolerance == pytest.approx(expected_t)
    assert row.within is (expected_t >= 15.0)
    assert ("PARCEL_AREA_OUTSIDE_TOLERANCE" in codes(r.issues)) is (expected_t < 15.0)


def test_incomplete_rule_is_rejected():
    with pytest.raises(ValueError):
        area_tolerance(AreaToleranceRule(kind="formula", a=1.0), 100.0)
    with pytest.raises(ValueError):
        area_tolerance(AreaToleranceRule(kind="fixed"), 100.0)


def test_compare_from_parcel_and_requires_an_area():
    r = compare_areas(AreaCompareRequest(parcel=parcel(RECT), deed_area=5000.0))
    assert r.surveyed_area == pytest.approx(5000.0)
    assert r.rows[0].difference == pytest.approx(0.0, abs=1e-9)
    with pytest.raises(ValueError):
        compare_areas(AreaCompareRequest(deed_area=10.0))


def test_compare_with_invalid_parcel_reports_issues():
    bad = parcel([("A", 0, 0), ("B", 10, 10), ("C", 10, 0), ("D", 0, 10)])
    r = compare_areas(AreaCompareRequest(parcel=bad, deed_area=10.0))
    assert r.rows == [] and codes(r.issues) == ["PARCEL_SELF_INTERSECTION"]


def test_cadastre_presets_carry_u0_source_and_confirmation_flag():
    by_id = {p.id: p for p in AREA_TOLERANCE_PRESETS}
    assert by_id["cadastre_urban"].rule.u0 == 0.5
    assert not by_id["cadastre_urban"].to_be_confirmed
    assert by_id["cadastre_rural"].rule.u0 == 2.0 and by_id["cadastre_rural"].to_be_confirmed
    assert by_id["cadastre_rural_dgm_guide"].rule.u0 == 2.5
    assert all("1510" in by_id[k].rule.source for k in ("cadastre_urban", "cadastre_rural"))


def test_cadastre_tolerance_worked_example():
    # square of 500 m² (Π = 4·√500 = 89.4427 m), urban U0 = 0.50 m
    e = 500.0
    perim = 4 * math.sqrt(e)
    t = cadastre_tolerance(e, perim, 0.5)
    assert t == pytest.approx(45.72, abs=0.005)
    # published form [(√E + 2U0)² − E]·Π / (4√E) gives the same value
    published = ((math.sqrt(e) + 1.0) ** 2 - e) * perim / (4 * math.sqrt(e))
    assert t == pytest.approx(published, rel=1e-14)
    rule = AreaToleranceRule(kind="cadastre", u0=0.5)
    assert area_tolerance(rule, e, perim) == pytest.approx(t)
    capped = rule.model_copy(update={"cap_percent": 7.0})
    assert area_tolerance(capped, e, perim) == pytest.approx(35.0)
    with pytest.raises(ValueError):
        area_tolerance(rule, e)  # needs the perimeter


def test_compare_with_cadastre_rule_uses_the_parcel_perimeter():
    side = math.sqrt(500.0)
    sq = parcel([("A", 0, 0), ("B", side, 0), ("C", side, side), ("D", 0, side)])
    rule = AreaToleranceRule(kind="cadastre", u0=0.5, source="ΦΕΚ Β΄ 1510/2008")
    r = compare_areas(AreaCompareRequest(parcel=sq, cadastre_area=540.0, tolerance=rule))
    assert r.perimeter == pytest.approx(4 * side)
    row = r.rows[0]
    # E = 540 (reference), Π = 89.44 → T = 0.5·89.44·(1 + 0.5/√540) ≈ 45.68 > |−40|
    assert row.tolerance == pytest.approx(0.5 * 4 * side * (1 + 0.5 / math.sqrt(540)))
    assert row.within is True
    with pytest.raises(ValueError):  # area only, no perimeter: the rule cannot be evaluated
        compare_areas(AreaCompareRequest(surveyed_area=500, cadastre_area=540.0, tolerance=rule))
    r3 = compare_areas(
        AreaCompareRequest(
            surveyed_area=500, perimeter=4 * side, cadastre_area=540.0, tolerance=rule
        )
    )
    assert r3.rows[0].tolerance == pytest.approx(row.tolerance)


def test_every_parcel_issue_code_has_a_greek_template():
    import re
    from pathlib import Path

    from atsurvey.core import messages

    src = Path(messages.__file__).parent
    found = set()
    for name in ("parcels.py", "parcels_subdivide.py", "parcels_merge.py", "parcels_coverage.py"):
        found |= set(re.findall(r'"(PARCEL_[A-Z_]+)"', (src / name).read_text("utf-8")))
    assert found, "no codes found"
    assert found <= set(messages.EL), found - set(messages.EL)


def test_greek_message_is_rendered_from_params():
    from atsurvey.core.messages import localize

    g = analyze_parcel(parcel([("A", 0, 0), ("B", 10, 10), ("C", 10, 0), ("D", 0, 10)]))
    assert localize(g.issues[0], "el").startswith("Το όριο τέμνει τον εαυτό του")
