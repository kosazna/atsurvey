"""ΔΓΜ DXF writer, validator, ΚΔ reader and hash PDF.

Every DXF the writer produces must pass the validator; each injected fault (missing shared
vertex, MTEXT, Greek alpha in a layer name, z ≠ 0, 1 mm gap, KAEK text outside, overlap, …)
must be caught with its own code.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from ezdxf import recover
from test_dgm_build import correction_request, subdivision

from atsurvey.core.dgm import DgmRequest, build_dgm
from atsurvey.core.dgm.hashpdf import hash_pdf, sha512_hex
from atsurvey.core.dgm.kd_reader import read_kd
from atsurvey.core.dgm.models import TitleBlock, ValidationReport
from atsurvey.core.dgm.samples import KAEK_A, KAEK_B, KAEK_C, POINTS, sample_parcels
from atsurvey.core.dgm.spec import LAYERS, DiagramKind, check_file_name, suggest_file_name
from atsurvey.core.dgm.validate import validate_dxf
from atsurvey.core.dgm.writer import write_dgm_dxf
from atsurvey.core.messages import EL, localize

FIXTURES = Path(__file__).parent / "fixtures" / "dgm"


def errors(rep: ValidationReport) -> set[str]:
    return {i.code for c in rep.checks for i in c.issues if i.severity == "error"}


def all_codes(rep: ValidationReport) -> set[str]:
    return {i.code for c in rep.checks for i in c.issues}


def status(rep: ValidationReport, check: str) -> str:
    return next(c.status for c in rep.checks if c.id == check)


@pytest.fixture(scope="module")
def deed_dxf() -> bytes:
    res = subdivision()
    assert res.ok
    return write_dgm_dxf(res, TitleBlock(author="Α. Μηχανικός", client="Εργοδότης", scale=500))


@pytest.fixture(scope="module")
def correction_dxf() -> bytes:
    req = correction_request()
    res = build_dgm(req)
    assert res.ok
    return write_dgm_dxf(res, TitleBlock(tdgm=True, notes="Δοκιμή"))


def mutate(data: bytes, fn: Callable) -> bytes:
    doc, _ = recover.read(io.BytesIO(data))
    fn(doc)
    buf = io.StringIO()
    doc.write(buf)
    return doc.encode(buf.getvalue())


def polys(doc, layer: str) -> list[Any]:
    return [e for e in doc.modelspace().query("LWPOLYLINE") if e.dxf.layer == layer]


# ------------------------------------------------------------------------------- writer


def test_written_files_pass_the_validator(deed_dxf, correction_dxf):
    ps = sample_parcels()
    merge = build_dgm(DgmRequest(mode="merge", parcels=ps[:2], topo_prop=[ps[0]]))
    merge_dxf = write_dgm_dxf(merge, TitleBlock())
    cases: list[tuple[bytes, DiagramKind]] = [
        (deed_dxf, "deed"),
        (merge_dxf, "deed"),
        (correction_dxf, "correction"),
    ]
    for data, kind in cases:
        rep = validate_dxf(data, "dgm_test_v01.dxf", kind)
        bad = [
            (c.id, [i.code for i in c.issues]) for c in rep.checks if c.status in ("fail", "warn")
        ]
        assert rep.ok and not bad, bad
        assert rep.dxf_version == "AC1018"
        assert rep.sha512 == hashlib.sha512(data).hexdigest()


def test_writer_header_layers_and_exact_coordinates(correction_dxf):
    doc = ezdxf.read(io.StringIO(correction_dxf.decode("cp1253")))  # pyright: ignore[reportPrivateImportUsage]
    assert doc.dxfversion == "AC1018"
    assert doc.header["$INSUNITS"] == 6
    assert doc.header["$DWGCODEPAGE"] == "ANSI_1253"
    names = {lay.dxf.name for lay in doc.layers}
    assert {s.name for s in LAYERS} <= names
    assert doc.layers.get("PST_KAEK").dxf.color == 16
    assert doc.layers.get("LINE_XM").dxf.linetype == "JIS_02_2.0"
    assert doc.layers.get("DGM_PROP_FINAL").dxf.lineweight == 30
    msp = doc.modelspace()
    assert not msp.query("MTEXT INSERT HATCH")
    lw: list[Any] = list(msp.query("LWPOLYLINE"))
    coords = {(x, y) for e in lw for x, y in e.get_points("xy")}
    for name in ("1", "2", "3", "4", "5", "7", "8", "9"):
        assert POINTS[name] in coords  # bit-identical round trip
    texts = [e.dxf.text for e in msp.query("TEXT")]
    assert {KAEK_A, KAEK_B, KAEK_C} <= set(texts)
    assert any("Κωδικό Ηλεκτρονικού Διαγράμματος" in t for t in texts)  # ΤΔΓΜ declaration
    assert any("ΠΙΝΑΚΑΣ ΜΕΤΑΒΟΛΩΝ" in t for t in texts)
    assert any(t.startswith("Δ1") or t == "Δ1" for t in texts)


# ------------------------------------------------------------------------ fault injection


def test_missing_shared_vertex_is_caught(correction_dxf):
    def drop_3n(doc):
        for e in polys(doc, "DGM_PROP_FINAL"):
            pts = e.get_points("xy")
            if len(pts) == 6:  # final C with the healed vertex 3n
                e.set_points([p for k, p in enumerate(pts) if k != 5], format="xy")

    rep = validate_dxf(mutate(correction_dxf, drop_3n), "dgm_test_v01.dxf", "correction")
    assert "DGM_SHARED_VERTEX_MISSING" in errors(rep)
    issue = next(i for c in rep.checks for i in c.issues if i.code == "DGM_SHARED_VERTEX_MISSING")
    assert issue.params["layer"] == "DGM_PROP_FINAL" and issue.params["handle"]
    assert issue.params["x"] == pytest.approx(476234.744, abs=0.01)


def test_mtext_on_pst_kaek_is_forbidden(deed_dxf):
    rep = validate_dxf(
        mutate(
            deed_dxf,
            lambda d: d.modelspace().add_mtext(
                KAEK_A, dxfattribs={"layer": "PST_KAEK", "insert": POINTS["1"]}
            ),
        ),
        "dgm_a_v01.dxf",
        "deed",
    )
    assert "DGM_FORBIDDEN_ENTITY" in errors(rep)


def test_greek_alpha_in_layer_name(correction_dxf):
    def rename(doc):
        doc.layers.add("AREA_Α")  # Greek capital alpha U+0391
        for e in polys(doc, "AREA_A"):
            e.dxf.layer = "AREA_Α"

    rep = validate_dxf(mutate(correction_dxf, rename), "dgm_a_v01.dxf", "correction")
    assert "DGM_LAYER_GREEK_LOOKALIKE" in errors(rep)
    issue = next(i for c in rep.checks for i in c.issues if i.code == "DGM_LAYER_GREEK_LOOKALIKE")
    assert issue.params["expected"] == "AREA_A"
    assert "U+0391" in issue.params["chars"][0]


def test_elevation_is_caught_and_empties_the_layer(deed_dxf):
    def lift(doc):
        for e in polys(doc, "TOPO_PROP"):
            e.dxf.elevation = 12.5

    rep = validate_dxf(mutate(deed_dxf, lift), "dgm_a_v01.dxf", "deed")
    assert "DGM_ELEVATION" in errors(rep)
    # the Cadastre then reports the layer as having no content; TOPO_PROP_NEW is absent too
    assert "DGM_LAYER_REQUIRED_ANY" in errors(rep)


def _shift(layer: str, index: int, dx: float):
    def fn(doc):
        e = polys(doc, layer)[index]
        e.set_points([(x + dx, y) for x, y in e.get_points("xy")], format="xy")

    return fn


def test_one_millimetre_gap_is_caught(deed_dxf):
    # the eastern part moves 1 mm east: a gap along the partition line
    rep = validate_dxf(
        mutate(deed_dxf, _shift("DGM_PROP_FINAL", 1, 0.001)), "dgm_a_v01.dxf", "deed"
    )
    assert "DGM_GAP" in errors(rep)
    assert "DGM_VERTEX_MISMATCH" in errors(rep)
    assert "DGM_OUTLINE_EXCEEDS" in errors(rep) and "DGM_OUTLINE_SHORT" in errors(rep)
    gap = next(i for c in rep.checks for i in c.issues if i.code == "DGM_GAP")
    assert gap.params["mm"] == pytest.approx(1.0, abs=0.05)


def test_overlap_is_caught(deed_dxf):
    rep = validate_dxf(
        mutate(deed_dxf, _shift("DGM_PROP_FINAL", 1, -0.001)), "dgm_a_v01.dxf", "deed"
    )
    assert "DGM_OVERLAP" in errors(rep)


def test_kaek_text_outside_its_polygon(deed_dxf):
    def move(doc):
        for t in doc.modelspace().query("TEXT"):
            if t.dxf.layer == "PST_KAEK":
                t.dxf.insert = (POINTS["9"][0] + 50, POINTS["9"][1])

    rep = validate_dxf(mutate(deed_dxf, move), "dgm_a_v01.dxf", "deed")
    assert {"DGM_KAEK_TEXT_OUTSIDE", "DGM_KAEK_TEXT_MISSING"} <= errors(rep)


def test_duplicate_polygon_and_stray_circle(deed_dxf):
    def dup(doc):
        e = polys(doc, "PST_KAEK")[0]
        doc.modelspace().add_lwpolyline(
            e.get_points("xy"), format="xy", close=True, dxfattribs={"layer": "PST_KAEK"}
        )
        doc.modelspace().add_circle(POINTS["1"], 0.2, dxfattribs={"layer": "PST_KAEK"})

    rep = validate_dxf(mutate(deed_dxf, dup), "dgm_a_v01.dxf", "deed")
    assert {"DGM_DUPLICATE", "DGM_KAEK_STRAY_SHAPE"} <= errors(rep)


def test_open_polyline_block_and_hatch(deed_dxf):
    def add(doc):
        msp = doc.modelspace()
        msp.add_lwpolyline([POINTS["1"], POINTS["2"]], dxfattribs={"layer": "DGM_PROP_FINAL"})
        blk = doc.blocks.new("MARK")
        blk.add_circle((0, 0), 0.1)
        msp.add_blockref("MARK", POINTS["1"], dxfattribs={"layer": "BLD"})
        h = msp.add_hatch(dxfattribs={"layer": "TOPO_PROP"})
        h.paths.add_polyline_path([POINTS["1"], POINTS["2"], POINTS["3"]])

    rep = validate_dxf(mutate(deed_dxf, add), "dgm_a_v01.dxf", "deed")
    assert {"DGM_POLYGON_OPEN", "DGM_FORBIDDEN_ENTITY"} <= errors(rep)


def test_required_layers_depend_on_the_kind(deed_dxf):
    rep = validate_dxf(deed_dxf, "dgm_a_v01.dxf", "correction")
    codes = all_codes(rep)
    assert "DGM_LAYER_PAIR" in codes  # DGM_PROP_FINAL without AREA_A/AREA_D
    assert "DGM_LAYER_NOT_FOR_KIND" in codes  # LINE_XM in a correction
    rep = validate_dxf(deed_dxf, "topo_a_v01.dxf", "topo")
    assert status(rep, "layers_required") == "pass"
    assert "outline" not in {c.id for c in rep.checks}


def test_layer_name_case_and_spaces(deed_dxf):
    def rename(doc):
        doc.layers.add("Pst kaek")
        doc.modelspace().add_lwpolyline(
            [(0, 0), (1, 0), (1, 1)], close=True, dxfattribs={"layer": "Pst kaek"}
        )

    rep = validate_dxf(mutate(deed_dxf, rename), "dgm_a_v01.dxf", "deed")
    assert "DGM_LAYER_NAME_FORM" in errors(rep)


def test_unreadable_and_old_versions():
    rep = validate_dxf(b"this is not a dxf", "dgm_a_v01.dxf", "deed")
    assert not rep.ok and "DGM_DXF_UNREADABLE" in errors(rep)
    assert status(rep, "overlaps") == "skip"
    doc = ezdxf.new("R12")  # pyright: ignore[reportPrivateImportUsage]
    buf = io.StringIO()
    doc.write(buf)
    rep = validate_dxf(buf.getvalue().encode("cp1252"), "dgm_a_v01.dxf", "deed")
    assert "DGM_DXF_VERSION" in errors(rep)


def test_file_name_rules():
    assert check_file_name("dgm_name_v01.dxf", "deed") == []
    codes = {c for c, _ in check_file_name("ΔΓΜ αγρός.v1.dxf", "deed")}
    assert {"DGM_FILE_CHARS", "DGM_FILE_PREFIX"} <= codes
    codes = {c for c, _ in check_file_name("dgm_averyveryverylongname_v01.dxf", "correction")}
    assert "DGM_FILE_LENGTH" in codes
    assert {c for c, _ in check_file_name("topo_x_v01.dxf", "deed")} == {"DGM_FILE_PREFIX"}
    assert {c for c, _ in check_file_name("dgm_x.dxf", "deed")} == {"DGM_FILE_VERSION_WARN"}
    name = suggest_file_name("Αγρός Παπαδόπουλου", "deed")
    assert check_file_name(name, "deed") == [] and len(name) <= 19


def test_size_limit_is_reported(deed_dxf):
    padded = deed_dxf + b"999\n" + b"x" * (10 * 1024 * 1024) + b"\n"
    rep = validate_dxf(padded, "dgm_a_v01.dxf", "deed")
    assert "DGM_FILE_TOO_LARGE" in errors(rep)


def test_validator_messages_are_localized(deed_dxf):
    rep = validate_dxf(
        mutate(deed_dxf, _shift("DGM_PROP_FINAL", 1, 0.001)), "bad name.dxf", "correction"
    )
    for c in rep.checks:
        for i in c.issues:
            assert i.code in EL, i.code
            assert localize(i, "el") != i.message, i.code


# ----------------------------------------------------------------------------- ΚΔ reader


def make_kd(version: str = "R2000") -> bytes:
    """A synthetic ΚΔ: the three sample parcels with KAEK texts (one with a «ΚΑΕΚ:» prefix and
    spaces), a sheet frame and a building outline without KAEK, Greek title text in cp1253."""
    doc = ezdxf.new(version)  # pyright: ignore[reportPrivateImportUsage]
    doc.encoding = "cp1253"
    msp = doc.modelspace()
    for p in sample_parcels():
        pts = [(q.x, q.y) for q in p.vertices]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "ΓΕΩΤΕΜΑΧΙΑ"})
        cx = sum(x for x, _ in pts) / len(pts)
        cy = sum(y for _, y in pts) / len(pts)
        text = f"ΚΑΕΚ: {p.kaek[:5]} {p.kaek[5:]}" if p.kaek == KAEK_B else p.kaek
        msp.add_text(text or "", dxfattribs={"layer": "ΚΑΕΚ", "insert": (cx, cy), "height": 1.0})
    msp.add_lwpolyline(
        [(476150, 4205050), (476320, 4205050), (476320, 4205220), (476150, 4205220)],
        close=True,
        dxfattribs={"layer": "FRAME"},
    )
    msp.add_lwpolyline(
        [(476205, 4205110), (476210, 4205110), (476210, 4205115), (476205, 4205115)],
        close=True,
        dxfattribs={"layer": "ΚΤΙΡΙΑ"},
    )
    msp.add_text(
        "ΚΤΗΜΑΤΟΓΡΑΦΙΚΟ ΔΙΑΓΡΑΜΜΑ", dxfattribs={"layer": "FRAME", "insert": (476160, 4205210)}
    )
    msp.add_text("999999999999", dxfattribs={"layer": "ΚΑΕΚ", "insert": (476400, 4205100)})
    buf = io.StringIO()
    doc.write(buf)
    return doc.encode(buf.getvalue())


def test_kd_reader_assigns_kaek_to_the_smallest_polygon():
    res = read_kd(make_kd())
    assert [p.kaek for p in res.parcels] == [KAEK_A, KAEK_B, KAEK_C]
    a = res.parcels[0]
    assert {(q.x, q.y) for q in a.vertices} == {POINTS[n] for n in ("1", "2", "3", "4")}
    # shared vertices get one name across parcels
    names = {}
    for p in res.parcels:
        for q in p.vertices:
            assert names.setdefault((q.x, q.y), q.name) == q.name
    codes = {i.code for i in res.issues}
    assert {"DGM_KD_POLYGONS_SKIPPED", "DGM_KD_TEXT_UNASSIGNED"} <= codes


def test_kd_fixture_file_in_utf8_dxf2007():
    data = (FIXTURES / "kd_three_parcels.dxf").read_bytes()
    res = read_kd(data)
    assert [p.kaek for p in res.parcels] == [KAEK_A, KAEK_B, KAEK_C]
    assert res.parcels[2].area == pytest.approx(1851.7174, abs=1e-3)


def test_kd_reader_without_kaek_texts_and_garbage():
    doc = ezdxf.new("R2004")  # pyright: ignore[reportPrivateImportUsage]
    doc.modelspace().add_lwpolyline([POINTS["1"], POINTS["2"], POINTS["3"]], close=True)
    buf = io.StringIO()
    doc.write(buf)
    res = read_kd(buf.getvalue().encode())
    assert len(res.parcels) == 1 and res.parcels[0].kaek is None
    assert "DGM_KD_NO_KAEK" in {i.code for i in res.issues}
    res = read_kd(b"\x00\x01garbage")
    assert res.parcels == [] and res.issues[0].code == "DGM_DXF_UNREADABLE"


# ------------------------------------------------------------------------------ hash PDF


def test_hash_pdf():
    h = sha512_hex(b"abc")
    assert h.startswith("ddaf35a193617aba")  # FIPS 180-2 test vector
    pdf = hash_pdf(h.upper())
    assert pdf.startswith(b"%PDF") and b"/Type/Pages/Count 1" in pdf
    with pytest.raises(ValueError):
        hash_pdf("1234")


def test_deed_with_neighbours_for_context_passes():
    res = subdivision(parcels=sample_parcels(), subject=KAEK_A)
    data = write_dgm_dxf(res, TitleBlock())
    rep = validate_dxf(data, "dgm_a_v01.dxf", "deed")
    assert rep.ok, errors(rep)
    doc, _ = recover.read(io.BytesIO(data))
    assert len(polys(doc, "ATS_NEIGHBOURS")) == 2
