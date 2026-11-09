"""Instrument raw-data parsers with format auto-detection."""

from __future__ import annotations

import re

from ..core.units import AngleUnit
from .base import FormatName, ParseError, ParseResult, decode
from .gsi import parse_gsi
from .textformats import parse_csv, parse_nikon_raw, parse_rw5
from .xmlformats import parse_jobxml, parse_landxml

PARSER_VERSION = "1"


def detect_format(data: bytes, filename: str | None = None) -> FormatName:
    name = (filename or "").lower()
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
    raise ParseError(f"Unsupported format {fmt}")


__all__ = ["PARSER_VERSION", "ParseError", "ParseResult", "detect_format", "parse_file"]
