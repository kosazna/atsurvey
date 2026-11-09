import math

import pytest

from atsurvey import ControlPoint, ProjectInput, compute_project
from atsurvey.core.linework import build_linework
from atsurvey.core.models import ComputeSettings, DetailShot, LineworkSettings, ResultPoint
from synth import observe


def shot(target: str, code: str | None) -> DetailShot:
    return DetailShot(
        station="S",
        target=target,
        direction=0,
        zenith=None,
        sd=None,
        hd=None,
        distance_grid=None,
        azimuth=0,
        x=0,
        y=0,
        z=0,
        code=code,
    )


def pts(**xy: tuple[float, float]) -> list[ResultPoint]:
    return [ResultPoint(name=n, x=x, y=y, z=None, kind="detail") for n, (x, y) in xy.items()]


SQUARE = pts(a=(0, 0), b=(10, 0), c=(10, 10), d=(0, 10), e=(20, 0), f=(30, 0))


def test_no_line_codes_no_lines():
    assert build_linework([shot("a", "KR")], SQUARE, LineworkSettings()) == []


def test_open_line_in_observation_order():
    lines = build_linework(
        [shot("a", "KR"), shot("b", "kr"), shot("c", "KR"), shot("e", "DEN")],
        SQUARE,
        LineworkSettings(line_codes=["KR"]),
    )
    assert len(lines) == 1
    line = lines[0]
    assert line.points == ["a", "b", "c"] and not line.closed and line.area is None
    assert line.length == pytest.approx(20.0)
    assert line.name == "KR#1"


def test_closed_polygon_area_and_perimeter():
    lines = build_linework(
        [shot("a", "OIK"), shot("b", "OIK"), shot("c", "OIK"), shot("d", "OIK CL")],
        SQUARE,
        LineworkSettings(line_codes=["OIK"]),
    )
    (poly,) = lines
    assert poly.closed and poly.area == pytest.approx(100.0)
    assert poly.length == pytest.approx(40.0)


def test_start_and_end_tokens_split_lines():
    lines = build_linework(
        [
            shot("a", "KR"),
            shot("b", "KR E"),
            shot("e", "KR"),
            shot("f", "KR"),
            shot("c", "KR ST"),
            shot("d", "KR"),
        ],
        SQUARE,
        LineworkSettings(line_codes=["KR"]),
    )
    assert [line.points for line in lines] == [["a", "b"], ["e", "f"], ["c", "d"]]
    assert [line.name for line in lines] == ["KR#1", "KR#2", "KR#3"]


def test_numbered_features_are_separate_lines():
    lines = build_linework(
        [shot("a", "KR1"), shot("e", "KR2"), shot("b", "KR1"), shot("f", "KR2")],
        SQUARE,
        LineworkSettings(line_codes=["KR"]),
    )
    assert {line.name: line.points for line in lines} == {"KR1#1": ["a", "b"], "KR2#1": ["e", "f"]}
    assert all(line.code == "KR" for line in lines)


def test_greek_codes_and_single_points():
    lines = build_linework(
        [shot("a", "ΚΡ"), shot("b", "ΚΡ ΚΛ"), shot("c", "ΤΟ")],
        SQUARE,
        LineworkSettings(line_codes=["ΚΡ", "ΤΟ"]),
    )
    # ΚΡ with two points cannot close; ΤΟ with one point is dropped
    assert len(lines) == 1 and not lines[0].closed and lines[0].points == ["a", "b"]


def test_case_sensitive_option():
    lines = build_linework(
        [shot("a", "kr"), shot("b", "kr")],
        SQUARE,
        LineworkSettings(line_codes=["KR"], case_sensitive=True),
    )
    assert lines == []


def test_area_precision_at_egsa87_magnitudes():
    # a 1 m × 1 m square far from the origin must still give exactly 1 m²
    x0, y0 = 899_999.123, 4_699_999.456
    big = pts(p=(x0, y0), q=(x0 + 1, y0), r=(x0 + 1, y0 + 1), s=(x0, y0 + 1))
    (sq,) = build_linework(
        [shot("p", "Ο"), shot("q", "Ο"), shot("r", "Ο"), shot("s", "Ο CL")],
        big,
        LineworkSettings(line_codes=["Ο"]),
    )
    assert sq.area == pytest.approx(1.0, abs=1e-9)


def test_end_to_end_compute_project():
    truth = {
        "K1": (476000.0, 4205000.0, 100.0),
        "K2": (476100.0, 4205000.0, 101.0),
        "P1": (476020.0, 4205030.0, 100.5),
        "P2": (476040.0, 4205030.0, 100.6),
        "P3": (476040.0, 4205050.0, 100.7),
        "P4": (476020.0, 4205050.0, 100.4),
    }
    codes = {"P1": "OIK", "P2": "OIK", "P3": "OIK", "P4": "OIK CL"}
    setup = observe(truth, "K1", ["K2", "P1", "P2", "P3", "P4"], codes=codes)
    r = compute_project(
        ProjectInput(
            control_points=[
                ControlPoint(name=n, x=truth[n][0], y=truth[n][1], z=truth[n][2])
                for n in ("K1", "K2")
            ],
            setups=[setup],
            settings=ComputeSettings(linework=LineworkSettings(line_codes=["OIK"])),
        )
    )
    (poly,) = r.linework
    assert poly.closed and poly.points == ["P1", "P2", "P3", "P4"]
    assert poly.area == pytest.approx(400.0, abs=1e-3)
    assert math.isclose(poly.length, 80.0, abs_tol=1e-3)


def _polygon_project():
    truth = {
        "K1": (476000.0, 4205000.0, 100.0),
        "K2": (476100.0, 4205000.0, 101.0),
        "P1": (476020.0, 4205030.0, 100.5),
        "P2": (476040.0, 4205030.0, 100.6),
        "P3": (476040.0, 4205050.0, 100.7),
        "P4": (476020.0, 4205050.0, 100.4),
    }
    codes = {"P1": "OIK", "P2": "OIK", "P3": "OIK", "P4": "OIK CL"}
    inp = ProjectInput(
        control_points=[
            ControlPoint(name=n, x=truth[n][0], y=truth[n][1], z=truth[n][2]) for n in ("K1", "K2")
        ],
        setups=[observe(truth, "K1", ["K2", "P1", "P2", "P3", "P4"], codes=codes)],
        settings=ComputeSettings(linework=LineworkSettings(line_codes=["OIK"])),
    )
    return inp, compute_project(inp)


def test_linework_in_dxf_and_shapefile():
    import io
    import zipfile

    import ezdxf
    import shapefile

    from atsurvey.exports import export

    inp, res = _polygon_project()
    data, *_ = export("dxf", "t", inp, res)
    doc = ezdxf.read(io.StringIO(data.decode()))
    polys = [e for e in doc.modelspace().query("POLYLINE") if e.dxf.layer == "ATS_LINE_OIK"]
    assert len(polys) == 1 and polys[0].is_closed and len(list(polys[0].vertices)) == 4

    z = zipfile.ZipFile(io.BytesIO(export("shp", "t", inp, res)[0]))
    assert "t_lines.prj" in z.namelist()
    r = shapefile.Reader(
        shp=io.BytesIO(z.read("t_lines.shp")),
        shx=io.BytesIO(z.read("t_lines.shx")),
        dbf=io.BytesIO(z.read("t_lines.dbf")),
        encoding="utf-8",
    )
    rec = r.record(0)
    assert rec["CODE"] == "OIK" and rec["CLOSED"] is True
    assert rec["AREA"] == pytest.approx(400.0, abs=1e-3)
    assert len(r.shape(0).points) == 5  # closed ring repeats the first vertex
