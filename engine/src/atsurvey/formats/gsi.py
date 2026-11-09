"""Leica GSI-8 / GSI-16 raw data.

A GSI line is a sequence of *words*. Each word is ``WI`` (2-digit word index) + 4 info
characters + sign + data (8 or 16 chars). Info position 6 (index 5 of the word) holds the
unit code. GSI-16 lines start with ``*``.

Word indices used:
    11 point id · 21 Hz · 22 V (zenith) · 31 slope distance · 32 horizontal distance
    41–49 codes/info · 71 remark · 81/82/83 target E/N/H · 84/85/86 station E/N/H
    87 reflector height · 88 instrument height

A *station* line carries 84–88 (and no 21); subsequent lines with 21/22/31 are
observations from that station. Coordinates in 81–86 are returned as candidate
control points.
"""

from __future__ import annotations

import math
import re

from ..core.models import ControlPoint, Observation, Setup
from ..core.units import AngleUnit, to_rad
from .base import ParseError, ParseResult, decode

_ANGLE_UNITS: dict[str, AngleUnit | str] = {
    "2": "gon",
    "3": "deg",
    "4": "dms",
    "5": "mil",
}
# distance unit code → divisor
_DIST_DIV = {"0": 1000.0, "1": 1000.0 / 0.3048, "6": 10000.0, "7": 10000.0 / 0.3048, "8": 100000.0}

_WORD_RE = re.compile(r"(\d{2})([0-9.]{4})([+-])(\S+)")


def _words(line: str) -> dict[str, tuple[str, str, str]]:
    """Return {word_index: (info, sign, data)}."""
    out: dict[str, tuple[str, str, str]] = {}
    body = line.strip()
    if body.startswith("*"):
        body = body[1:]
    for token in body.split():
        m = _WORD_RE.fullmatch(token)
        if not m:
            continue
        wi, info, sign, data = m.groups()
        out.setdefault(wi, (info, sign, data))
    return out


def _angle(word: tuple[str, str, str], warnings: list[str]) -> float:
    info, sign, data = word
    unit = _ANGLE_UNITS.get(info[3:4], "gon")
    raw = int(data) * (-1 if sign == "-" else 1)
    if unit == "gon":
        return to_rad(raw / 100000.0, "gon")
    if unit == "deg":
        return to_rad(raw / 100000.0, "deg")
    if unit == "dms":
        # dddmmss.s packed as integer with 1 decimal of seconds: e.g. 12345300 → 123°45'30.0"
        v = abs(raw)
        sec = (v % 1000) / 10.0
        minutes = (v // 1000) % 100
        deg = v // 100000
        val = deg + minutes / 60.0 + sec / 3600.0
        return math.copysign(val, raw) * math.pi / 180.0
    if unit == "mil":
        return raw / 10000.0 * (2 * math.pi / 6400.0)
    warnings.append(f"Unknown GSI angle unit code {info[3:4]!r}; assumed gon")
    return to_rad(raw / 100000.0, "gon")


def _dist(word: tuple[str, str, str]) -> float:
    info, sign, data = word
    div = _DIST_DIV.get(info[3:4], 1000.0)
    return int(data) * (-1 if sign == "-" else 1) / div


def _text(word: tuple[str, str, str]) -> str:
    return word[2].lstrip("0") or "0"


def parse_gsi(data: bytes) -> ParseResult:
    text = decode(data)
    res = ParseResult(format="leica_gsi")
    current: Setup | None = None
    unit_seen: AngleUnit | None = None
    coords: dict[str, ControlPoint] = {}
    n_lines = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        w = _words(line)
        if "11" not in w and "21" not in w and "84" not in w:
            continue
        n_lines += 1
        pid = _text(w["11"]) if "11" in w else f"L{lineno}"
        code = None
        for ci in ("41", "71"):
            if ci in w:
                code = _text(w[ci])
                break
        # station records
        if "21" not in w and ("84" in w or "88" in w):
            current = Setup(
                station=pid,
                instrument_height=_dist(w["88"]) if "88" in w else 0.0,
            )
            res.setups.append(current)
            if "84" in w and "85" in w:
                coords.setdefault(
                    pid,
                    ControlPoint(
                        name=pid,
                        x=_dist(w["84"]),
                        y=_dist(w["85"]),
                        z=_dist(w["86"]) if "86" in w else None,
                    ),
                )
            continue
        if "21" in w:
            if current is None:
                current = Setup(station="?", instrument_height=0.0)
                res.setups.append(current)
                res.warnings.append(
                    f"Line {lineno}: observation before any station record; station set to '?'"
                )
            if unit_seen is None:
                u = _ANGLE_UNITS.get(w["21"][0][3:4])
                unit_seen = u if u in ("gon", "deg", "dms") else None  # type: ignore[assignment]
            hz = _angle(w["21"], res.warnings)
            v = _angle(w["22"], res.warnings) if "22" in w else None
            sd = _dist(w["31"]) if "31" in w else None
            if sd is None and "32" in w:
                hd = _dist(w["32"])
                sd = hd / math.sin(v) if v is not None and math.sin(v) else hd
            ht = _dist(w["87"]) if "87" in w else 0.0
            if "88" in w and current.instrument_height == 0.0:
                current.instrument_height = _dist(w["88"])
            current.observations.append(
                Observation(
                    target=pid, hz=hz, v=v, sd=sd if sd else None, target_height=ht, code=code
                )
            )
        elif "81" in w and "82" in w:
            coords.setdefault(
                pid,
                ControlPoint(
                    name=pid,
                    x=_dist(w["81"]),
                    y=_dist(w["82"]),
                    z=_dist(w["83"]) if "83" in w else None,
                ),
            )
    if n_lines == 0:
        raise ParseError("No GSI words found")
    res.angle_unit = unit_seen
    res.control_points = list(coords.values())
    return res.finalise()
