import io

import ezdxf
import pytest

from atsurvey.exports import export
from atsurvey.formats.base import ParseError
from atsurvey.formats.dxf import parse_dxf

from test_exports import computed  # noqa: F401  (fixture)


def _bytes(doc) -> bytes:
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode()


def test_round_trip_of_our_own_dxf(computed):  # noqa: F811
    inp, res = computed
    data, *_ = export("dxf", "t", inp, res)
    p = parse_dxf(data)
    got = {c.name: c for c in p.control_points}
    assert set(got) == {pt.name for pt in res.points}
    for pt in res.points:
        assert got[pt.name].x == pytest.approx(pt.x, abs=1e-9)
        assert got[pt.name].y == pytest.approx(pt.y, abs=1e-9)
    assert not p.warnings or "label" not in " ".join(p.warnings)


def test_points_labelled_by_nearby_text_and_numbered_otherwise():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_point((476_000.0, 4_205_000.0, 101.25), dxfattribs={"layer": "ΣΗΜΕΙΑ"})
    msp.add_text("Σ12", height=0.5, dxfattribs={"insert": (476_000.4, 4_205_000.3)})
    msp.add_point((476_050.0, 4_205_050.0, 0.0))
    blk = doc.blocks.new("PT")
    blk.add_attdef("ID", (0, 0))
    blk.add_attdef("Z", (0, -1))
    ins = msp.add_blockref("PT", (476_100.0, 4_205_100.0))
    ins.add_auto_attribs({"ID": "K7", "Z": "99,5"})
    p = parse_dxf(_bytes(doc))
    got = {c.name: c for c in p.control_points}
    assert got["Σ12"].z == pytest.approx(101.25) and got["Σ12"].code == "ΣΗΜΕΙΑ"
    assert got["DXF1"].z is None  # z = 0 means no height
    assert got["K7"].z == pytest.approx(99.5)
    assert any("DXF1" in w for w in p.warnings)


def test_garbage_and_empty_dxf_rejected():
    with pytest.raises(ParseError):
        parse_dxf(b"this is not a dxf")
    with pytest.raises(ParseError):
        parse_dxf(_bytes(ezdxf.new("R2010")))
