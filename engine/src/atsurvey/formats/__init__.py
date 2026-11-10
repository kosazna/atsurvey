"""Instrument raw-data parsers with format auto-detection."""

from __future__ import annotations

import re

from ..core.units import AngleUnit
from .base import FormatName, ParseError, ParseResult, decode
from .dxf import parse_dxf
from .gsi import parse_gsi
from .textformats import parse_csv, parse_nikon_raw, parse_rw5
from .topcon import parse_topcon_gts7
from .xmlformats import parse_jobxml, parse_landxml

PARSER_VERSION = "1"

#: Upper bounds that keep parsing linear and bounded regardless of input
MAX_BYTES = 64 * 1024 * 1024
MAX_LINES = 2_000_000

BINARY_DXF = b"AutoCAD Binary DXF"

_BINARY_HINT = (
    "This looks like a binary file. Export the job as text first: Leica GSI or LandXML "
    "(not DBX), Trimble JobXML (not .job), Nikon RAW, RW5 or CSV."
)


def _guard(data: bytes) -> bytes:
    """Bound the input and return it as UTF-8-compatible bytes."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        # Excel "Unicode text" exports are UTF-16 (they contain NUL bytes, but are not binary)
        try:
            data = data.decode("utf-16").encode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError("Invalid UTF-16 text file") from exc
    if len(data) > MAX_BYTES:
        raise ParseError(f"File too large ({len(data) // (1024 * 1024)} MB)")
    head = data[:8192]
    if b"\x00" in head and not data.startswith(BINARY_DXF):
        raise ParseError(_BINARY_HINT)
    if data.count(b"\n") > MAX_LINES:
        raise ParseError(f"Too many lines (more than {MAX_LINES:,})")
    return data


def detect_format(data: bytes, filename: str | None = None) -> FormatName:
    name = (filename or "").lower()
    if data.startswith(BINARY_DXF) or name.endswith(".dxf"):
        return "dxf"
    head = decode(data[:8192]).lstrip("﻿ \r\n\t")
    if head.startswith("<") or name.endswith((".jxl", ".xml")):
        if "<JOBFile" in head:
            return "trimble_jobxml"
        if "<LandXML" in head:
            return "landxml"
        if name.endswith(".jxl"):
            return "trimble_jobxml"
        return "landxml"
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
    if lines[:2] == ["0", "SECTION"]:
        return "dxf"
    if name.endswith((".gt7", ".gts7")) or (lines and lines[0].upper().startswith("GTS-7")):
        return "topcon_gts7"
    if name.endswith((".gsi", ".gs8", ".gs16")) or any(
        re.match(r"^\*?11[0-9.]{4}[+-]", ln) for ln in lines[:20]
    ):
        return "leica_gsi"
    if name.endswith(".rw5") or any(
        re.match(r"^(OC|LS|BK|SS|TR|BD|FD|OB),(OP|HI|HR)", ln) for ln in lines[:50]
    ):
        return "rw5"
    if name.endswith(".raw") or any(
        re.match(r"^(CO,Nikon|ST,|F1,|F2,|SS,)", ln) for ln in lines[:50]
    ):
        return "nikon_raw"
    return "csv"


def parse_file(
    data: bytes,
    filename: str | None = None,
    *,
    fmt: FormatName | None = None,
    angle_unit: AngleUnit | None = None,
) -> ParseResult:
    data = _guard(data)
    fmt = fmt or detect_format(data, filename)
    if fmt == "leica_gsi":
        return parse_gsi(data)
    if fmt == "trimble_jobxml":
        return parse_jobxml(data)
    if fmt == "landxml":
        return parse_landxml(data, angle_unit)
    if fmt == "nikon_raw":
        return parse_nikon_raw(data, angle_unit or "gon")
    if fmt == "rw5":
        return parse_rw5(data, angle_unit or "gon")
    if fmt == "csv":
        return parse_csv(data, angle_unit or "gon")
    if fmt == "dxf":
        return parse_dxf(data)
    if fmt == "topcon_gts7":
        return parse_topcon_gts7(data, angle_unit or "gon")
    raise ParseError(f"Unsupported format {fmt}")


__all__ = ["PARSER_VERSION", "ParseError", "ParseResult", "detect_format", "parse_file"]
