"""Format round-trips: synthetic survey → file text → parser → engine → true coordinates.

The writers below produce files in each instrument format using the published record
layouts. They prove the parsers' structure and unit handling; real files from the field
are added under tests/fixtures/ as they become available.
"""

import math

import pytest

from atsurvey import ProjectInput, TraverseSpec, compute_project
from atsurvey.core.units import from_rad
from atsurvey.formats import detect_format, parse_file
from atsurvey.formats.base import ParseError

from synth import TRUTH, observe, traverse_setups
from test_traverse import LINK, assert_truth, control


def survey():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "D1", "D2"], codes={"D1": "KR"}))
    return setups


def check(parsed, tol=0.003):
    inp = ProjectInput(
        control_points=control(), setups=parsed.setups, traverses=[TraverseSpec(route=LINK)]
    )
    r = compute_project(inp)
    t = r.traverses[0]
    assert t.status == "ok", [i.message for i in r.issues]
    assert_truth(r, ["S1", "S2", "S3", "D1", "D2"], tol=tol, ztol=tol)
    return r


# ---------------------------------------------------------------------------- writers


def gsi16(setups, unit="gon"):
    code = {"gon": "2", "deg": "3"}[unit]
    lines = []
    n = 1

    def word(wi, info, value, width=16):
        sign = "-" if value < 0 else "+"
        return f"{wi}{info}{sign}{abs(round(value)):0{width}d}"

    def pid(name):
        return f"11{n:04d}+{name:>016}".replace(" ", "0")

    for s in setups:
        lines.append(
            "*"
            + " ".join([pid(s.station), word("88", "..1" + "0", s.instrument_height * 1000)])
            + " "
        )
        n += 1
        for o in s.observations:
            hz = from_rad(o.hz, unit) * 100000
            v = from_rad(o.v, unit) * 100000
            lines.append(
                "*"
                + " ".join(
                    [
                        pid(o.target),
                        word("21", ".32" + code, hz),
                        word("22", ".32" + code, v),
                        word("31", "..0" + "0", o.sd * 1000),
                        word("87", "..1" + "0", o.target_height * 1000),
                    ]
                )
                + " "
            )
            n += 1
    return "\n".join(lines).encode()


def jobxml(setups):
    parts = ['<?xml version="1.0"?>', '<JOBFile jobName="t" version="5.6">', "<FieldBook>"]
    rid = 1
    for s in setups:
        sid = f"{rid:08x}"
        rid += 1
        parts.append(
            f'<StationRecord ID="{sid}"><StationName>{s.station}</StationName>'
            f"<TheodoliteHeight>{s.instrument_height}</TheodoliteHeight>"
            f"<StationType>StationSetup</StationType></StationRecord>"
        )
        for o in s.observations:
            tid = f"{rid:08x}"
            rid += 1
            parts.append(
                f'<TargetRecord ID="{tid}"><TargetHeight>{o.target_height}</TargetHeight>'
                f"</TargetRecord>"
            )
            pid = f"{rid:08x}"
            rid += 1
            parts.append(
                f'<PointRecord ID="{pid}"><Name>{o.target}</Name>'
                f"<Code>{o.code or ''}</Code><Method>Direction</Method>"
                f"<Deleted>false</Deleted><StationID>{sid}</StationID><TargetID>{tid}</TargetID>"
                f"<Circle><HorizontalCircle>{math.degrees(o.hz):.10f}</HorizontalCircle>"
                f"<VerticalCircle>{math.degrees(o.v):.10f}</VerticalCircle>"
                f"<EDMDistance>{o.sd:.5f}</EDMDistance><Face>Face1</Face></Circle></PointRecord>"
            )
    # a deleted shot that must be ignored
    parts.append(
        '<PointRecord ID="ffff"><Name>JUNK</Name><Deleted>true</Deleted>'
        "<StationID>00000001</StationID><Circle><HorizontalCircle>1</HorizontalCircle>"
        "</Circle></PointRecord>"
    )
    parts.append("</FieldBook></JOBFile>")
    return "".join(parts).encode()


def landxml(setups, unit="grads"):
    u = {"grads": "gon", "decimal degrees": "deg"}[unit]
    parts = [
        '<?xml version="1.0"?>',
        '<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" version="1.2">',
        f'<Units><Metric linearUnit="meter" angularUnit="{unit}"/></Units>',
        "<CgPoints>",
    ]
    for n in ["T1", "T2"]:
        x, y, z = TRUTH[n]
        parts.append(f'<CgPoint name="{n}">{y} {x} {z}</CgPoint>')
    parts.append("</CgPoints><Survey>")
    for i, s in enumerate(setups):
        parts.append(
            f'<InstrumentSetup id="IS{i}" stationName="{s.station}" '
            f'instrumentHeight="{s.instrument_height}"><InstrumentPoint pntRef="{s.station}"/>'
        )
        for o in s.observations:
            parts.append(
                f'<RawObservation targetHeight="{o.target_height}" '
                f'horizAngle="{from_rad(o.hz, u):.8f}" zenithAngle="{from_rad(o.v, u):.8f}" '
                f'slopeDistance="{o.sd:.5f}"><TargetPoint pntRef="{o.target}"/></RawObservation>'
            )
        parts.append("</InstrumentSetup>")
    parts.append("</Survey></LandXML>")
    return "".join(parts).encode()


def nikon(setups, unit="gon"):
    lines = ["CO,Nikon RAW data format V2.00", "JB,NMtest,DT11-09-2026,TM10:00:00"]
    for s in setups:
        bs = s.observations[0].target
        lines.append(f"ST,{s.station},,{bs},,{s.instrument_height:.4f},0.0000,0.0000")
        for o in s.observations:
            rec = "F1" if o.target == bs else "SS"
            hz = from_rad(o.hz, unit)
            v = from_rad(o.v, unit)
            if rec == "F1":
                lines.append(
                    f"F1,{o.target},,{o.target_height:.4f},{o.sd:.4f},{hz:.5f},{v:.5f},10:00:00"
                )
            else:
                lines.append(
                    f"SS,{o.target},{o.target_height:.4f},{o.sd:.4f},{hz:.5f},{v:.5f},10:01:00,"
                    f"{o.code or ''}"
                )
    return "\n".join(lines).encode()


def rw5(setups, unit="gon"):
    lines = ["JB,NMtest,DT11-09-2026,TM10:00:00", "MO,AD0,UN2,SF1.00000000,EC0,EO0.0,AU1"]
    for s in setups:
        lines.append(f"LS,HI{s.instrument_height:.6f},HR{s.observations[0].target_height:.6f}")
        for o in s.observations:
            hz = from_rad(o.hz, unit)
            v = from_rad(o.v, unit)
            lines.append(
                f"SS,OP{s.station},FP{o.target},AR{hz:.5f},ZE{v:.5f},SD{o.sd:.6f}"
                + (f",--{o.code}" if o.code else "")
            )
    return "\n".join(lines).encode()


def csv_greek(setups, unit="gon"):
    # Greek Excel style: ; separator and decimal comma
    lines = ["Στάση;Σημείο;Οριζόντια;Κατακόρυφη;Απόσταση;υο;υσ;Κωδικός"]
    for s in setups:
        for o in s.observations:
            vals = [
                s.station,
                o.target,
                f"{from_rad(o.hz, unit):.5f}",
                f"{from_rad(o.v, unit):.5f}",
                f"{o.sd:.4f}",
                f"{s.instrument_height:.3f}",
                f"{o.target_height:.3f}",
                o.code or "",
            ]
            lines.append(";".join(v.replace(".", ",") for v in vals))
    return "\n".join(lines).encode("utf-8")


# ------------------------------------------------------------------------------ tests


def test_leica_gsi16_roundtrip():
    data = gsi16(survey())
    assert detect_format(data) == "leica_gsi"
    p = parse_file(data)
    assert p.format == "leica_gsi" and p.angle_unit == "gon"
    assert p.stats.setups == 6
    check(p)


def test_leica_gsi_degrees_unit_code():
    p = parse_file(gsi16(survey(), unit="deg"), "job.gsi")
    assert p.angle_unit == "deg"
    check(p)


def test_trimble_jobxml_roundtrip():
    data = jobxml(survey())
    assert detect_format(data, "job.jxl") == "trimble_jobxml"
    p = parse_file(data)
    assert all(o.target != "JUNK" for s in p.setups for o in s.observations)
    assert any("deleted" in w for w in p.warnings)
    r = check(p, tol=1e-4)
    assert {pt.name: pt for pt in r.points}["D1"].code == "KR"


@pytest.mark.parametrize("unit", ["grads", "decimal degrees"])
def test_landxml_roundtrip(unit):
    data = landxml(survey(), unit)
    assert detect_format(data) == "landxml"
    p = parse_file(data)
    assert p.angle_unit == {"grads": "gon", "decimal degrees": "deg"}[unit]
    cps = {c.name: c for c in p.control_points}
    assert cps["T1"].x == pytest.approx(TRUTH["T1"][0])  # easting, not northing
    check(p, tol=1e-4)


def test_nikon_raw_roundtrip():
    data = nikon(survey())
    assert detect_format(data, "job.raw") == "nikon_raw"
    p = parse_file(data, angle_unit="gon")
    check(p)


def test_rw5_roundtrip():
    data = rw5(survey())
    assert detect_format(data) == "rw5"
    p = parse_file(data, angle_unit="gon")
    r = check(p)
    assert {pt.name: pt for pt in r.points}["D1"].code == "KR"


def test_greek_excel_csv_roundtrip():
    data = csv_greek(survey())
    assert detect_format(data, "obs.csv") == "csv"
    p = parse_file(data, angle_unit="gon")
    check(p)


def test_control_points_csv_headerless_and_header():
    p = parse_file(b"T1,476120.412,4205333.187,182.341\nT2,476402.955,4205418.664,190.006\n")
    assert [c.name for c in p.control_points] == ["T1", "T2"]
    p2 = parse_file("Όνομα;X;Y;Z\nT9;476000,5;4205000,25;100,1\n".encode())
    assert p2.control_points[0].x == pytest.approx(476000.5)


def test_garbage_is_rejected():
    with pytest.raises(ParseError):
        parse_file(b"hello world\nnothing here\n")
    with pytest.raises(ParseError):
        parse_file(b"<notxml", "x.xml")


def test_xml_entity_attack_rejected():
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;">]><LandXML>&lol2;</LandXML>'
    )
    with pytest.raises(ParseError):
        parse_file(bomb, "x.xml")


def test_legacy_rw5_style_with_backsight_record():
    # shape of the files the 2020 prototype read (OP/FP/AR/ZE/SD, HR with colon)
    text = (
        '--Target Generic Prism: "My Prism"\n'
        "LS,HI1.550000,HR:1.800000\n"
        "BK,OPS1,BPT2,BS0.0000,BC0.0000\n"
        "SS,OPS1,FP101,AR123.4567,ZE99.1234,SD45.678000,--KR\n"
    )
    p = parse_file(text.encode(), angle_unit="gon")
    assert p.format == "rw5"
    s = p.setups[0]
    assert s.station == "S1" and s.instrument_height == pytest.approx(1.55)
    assert [o.target for o in s.observations] == ["T2", "101"]
    assert s.observations[1].target_height == pytest.approx(1.8)
    assert s.observations[1].code == "KR"


def topcon_gts7(setups, unit="gon"):
    lines = ["GTS-7", "JOB    test", f"UNITS  M,{'G' if unit == 'gon' else 'D'}"]
    for s in setups:
        lines.append(f"STN    {s.station},{s.instrument_height:.3f},STN")
        for i, o in enumerate(s.observations):
            rec = "BS" if i == 0 else "SS"
            lines.append(
                f"{rec:<6} {o.target},{o.target_height:.3f}" + (f",{o.code}" if o.code else "")
            )
            lines.append(f"SD     {from_rad(o.hz, unit):.6f},{from_rad(o.v, unit):.6f},{o.sd:.4f}")
    return "\n".join(lines).encode()


@pytest.mark.parametrize("unit", ["gon", "deg"])
def test_topcon_gts7_roundtrip(unit):
    from atsurvey.formats.topcon import parse_topcon_gts7

    p = parse_topcon_gts7(topcon_gts7(survey(), unit), angle_unit="gon")
    assert p.format == "topcon_gts7" and p.angle_unit == unit
    r = check(p)
    assert {pt.name: pt for pt in r.points}["D1"].code == "KR"
