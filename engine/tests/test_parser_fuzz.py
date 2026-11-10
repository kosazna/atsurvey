"""Parsers must fail *cleanly* on hostile input: only ParseError / ValueError, quickly.

Any other exception (IndexError, KeyError, OverflowError, …) would surface as a 500 and is a
robustness bug; anything slow is a denial-of-service vector.
"""

import contextlib
import time

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from atsurvey.formats import ParseError, parse_file
from atsurvey.formats.base import FormatName

FORMATS: list[FormatName] = ["leica_gsi", "trimble_jobxml", "landxml", "nikon_raw", "rw5", "csv"]

PREFIXES = {
    "leica_gsi": [
        "*110001+",
        "21.322+",
        "22.324+",
        "31..00+",
        "84..10+",
        "87..10+",
        "88..10+",
        "11",
    ],
    "nikon_raw": ["CO,", "ST,", "F1,", "F2,", "SS,", "UP,", "MO,", ","],
    "rw5": ["LS,HI", "OC,OP", "BK,OP", "SS,OP", "FP", "AR", "ZE", "SD", "--", ",N ", ",E "],
    "csv": ["station,target,hz,v,sd\n", "name,x,y,z\n", ";", ",", "\t", "1e309", "nan", "-"],
    "trimble_jobxml": ["<JOBFile>", "<PointRecord>", "<Circle>", "<StationRecord ID='1'>", "</"],
    "landxml": [
        "<LandXML>",
        "<InstrumentSetup stationName='a'>",
        "<RawObservation horizAngle='x'>",
        "<CgPoint name='p'>",
    ],
}


def _call(data: bytes, fmt: FormatName | None) -> None:
    start = time.perf_counter()
    with contextlib.suppress(ParseError, ValueError):
        parse_file(data, None, fmt=fmt, angle_unit="gon")
    assert time.perf_counter() - start < 2.0, "parser too slow on small input"


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.binary(max_size=2048), fmt=st.sampled_from([None, *FORMATS]))
def test_random_bytes(data, fmt):
    _call(data, fmt)


@st.composite
def structured(draw):
    fmt = draw(st.sampled_from(FORMATS))
    parts = draw(
        st.lists(
            st.one_of(
                st.sampled_from(PREFIXES[fmt]),
                st.text(alphabet="0123456789+-.,;eE:*OPFAR \n", max_size=20),
                st.sampled_from(["\n", " ", ",", "'", '"', ">", "<", "=", "1e400", "-0", "∞"]),
            ),
            max_size=60,
        )
    )
    return fmt, "".join(parts).encode("utf-8")


@settings(max_examples=600, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=structured())
def test_structured_garbage(case):
    fmt, data = case
    _call(data, fmt)
    _call(data, None)


def test_binary_files_get_a_helpful_message():
    with pytest.raises(ParseError, match="binary"):
        parse_file(b"\x00\x01\x02DBX" * 100, "job.dbx")


def test_utf16_excel_export_is_text():
    text = "Όνομα,X,Y,Z\nT1,476120.412,4205333.187,182.341\n"
    p = parse_file(text.encode("utf-16"), "points.csv")
    assert p.control_points[0].name == "T1"


@pytest.mark.parametrize(
    "payload",
    [
        # billion laughs
        b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;">]><LandXML>&c;</LandXML>',
        # external entity (file disclosure)
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        b"<LandXML><Survey>&e;</Survey></LandXML>",
        # external DTD retrieval (SSRF)
        b'<?xml version="1.0"?><!DOCTYPE JOBFile SYSTEM "http://169.254.169.254/latest/meta-data/">'
        b"<JOBFile/>",
        # parameter entity
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY % p SYSTEM "http://example.com/x.dtd"> %p;]>'
        b"<LandXML/>",
    ],
)
def test_xml_attacks_rejected(payload):
    for fmt in ("landxml", "trimble_jobxml", None):
        with pytest.raises(ParseError):
            parse_file(payload, "x.xml", fmt=fmt)
