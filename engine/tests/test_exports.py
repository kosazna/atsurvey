import io
import shutil
import subprocess
import zipfile

import ezdxf
import pytest
import shapefile
from atsurvey import ProjectInput, TraverseSpec, compute_project
from atsurvey.exports import ExportOptions, export, slug
from synth import TRUTH, observe, traverse_setups
from test_traverse import LINK, control


@pytest.fixture(scope="module")
def computed():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "D1", "D2"], codes={"D1": "ΚΡ", "D2": "TO"}))
    inp = ProjectInput(
        control_points=control(), setups=setups, traverses=[TraverseSpec(route=LINK)]
    )
    return inp, compute_project(inp)


def test_csv(computed):
    inp, res = computed
    data, name, media = export("csv", "Αφίδνες 2026", inp, res, ExportOptions(decimals=3))
    assert name == "Afidnes_2026.csv" and media.startswith("text/csv")
    text = data.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0] == "name,x,y,z,code,kind"
    assert any(line.startswith("D1,") and ",ΚΡ," in line for line in lines)
    assert len(lines) == 1 + len(res.points)


def test_csv_filter_and_delimiter(computed):
    inp, res = computed
    data, *_ = export(
        "csv",
        "p",
        inp,
        res,
        ExportOptions(include=["detail"], csv_delimiter=";", csv_header=False),
    )
    lines = data.decode("utf-8-sig").strip().splitlines()
    assert all(line.split(";")[5] == "detail" for line in lines)


def test_xlsx_is_valid_workbook(computed):
    inp, res = computed
    data, _name, _ = export("xlsx", "Test", inp, res)
    z = zipfile.ZipFile(io.BytesIO(data))
    sheets = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
    assert len(sheets) == 4 + len(res.traverses)
    assert "Σημεία" in z.read("xl/workbook.xml").decode()


def test_shapefile_zip(computed):
    inp, res = computed
    data, _name, media = export("shp", "Test", inp, res)
    assert media == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    for ext in ("shp", "shx", "dbf", "prj", "cpg"):
        assert f"Test_points.{ext}" in names
    assert "Test_traverses.shp" in names
    assert (
        "Greek_Grid" in z.read("Test_points.prj").decode()
        or "GGRS" in z.read("Test_points.prj").decode()
    )
    r = shapefile.Reader(
        shp=io.BytesIO(z.read("Test_points.shp")),
        shx=io.BytesIO(z.read("Test_points.shx")),
        dbf=io.BytesIO(z.read("Test_points.dbf")),
        encoding="utf-8",
    )
    assert r.shapeType == shapefile.POINTZ
    recs = {rec["NAME"]: rec for rec in r.records()}
    assert recs["D1"]["CODE"] == "ΚΡ"
    shp = r.shape(0)
    p0 = res.points[0]
    assert shp.points[0][0] == pytest.approx(p0.x) and shp.z[0] == pytest.approx(p0.z)


def test_dxf(computed):
    inp, res = computed
    data, _name, _ = export("dxf", "Test", inp, res, ExportOptions(dxf_text_height=0.3))
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    msp = doc.modelspace()
    inserts = list(msp.query("INSERT"))
    assert len(inserts) == len(res.points)
    by_name = {i.get_attrib_text("NAME"): i for i in inserts}
    d1 = by_name["D1"]
    assert d1.dxf.layer == "ATS_DETAIL_ΚΡ"
    p = {pt.name: pt for pt in res.points}["D1"]
    assert d1.dxf.insert.x == pytest.approx(p.x) and d1.dxf.insert.z == pytest.approx(p.z)
    assert by_name["T1"].dxf.layer == "ATS_CONTROL"
    assert len(list(msp.query("POLYLINE"))) == len(res.traverses)
    assert doc.header["$INSUNITS"] == 6


def test_pdf_report(computed, tmp_path):
    inp, res = computed
    data, _name, media = export("pdf", "Αφίδνες", inp, res)
    assert data[:5] == b"%PDF-" and media == "application/pdf"
    if shutil.which("pdftotext"):
        f = tmp_path / "r.pdf"
        f.write_bytes(data)
        text = subprocess.run(["pdftotext", str(f), "-"], capture_output=True, text=True).stdout
        assert "Τεύχος υπολογισμών" in text
        assert "Αφίδνες" in text
        assert "Εντός ορίων" in text
        assert "S2" in text


def test_pdf_english(computed):
    inp, res = computed
    data, *_ = export("pdf", "Afidnes", inp, res, ExportOptions(language="en", angle_unit="deg"))
    assert data[:5] == b"%PDF-"


def test_slug():
    assert slug("Οικόπεδο Κηφισιάς / 12") == "Oikopedo_Kifisias_12"
    assert slug("***") == "project"
