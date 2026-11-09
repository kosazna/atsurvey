"""Comma-separated text formats: Nikon RAW v2.00, Carlson/TDS RW5 and CSV tables.

Note on the 2020 prototype: its "Nikon" converter actually read **RW5-style** records
(``OP``/``FP``/``AR``/``ZE``/``SD``/``HR``/``HI`` prefixes), which Nikon/Spectra
instruments and Carlson software can export. Both formats are supported here.

Neither Nikon RAW nor RW5 declares its angular unit reliably, so the unit comes from
the caller (project setting, default ``gon``).
"""

from __future__ import annotations

import csv
import io
import re

from ..core.models import ControlPoint, Observation, Setup
from ..core.units import AngleUnit, to_rad
from .base import ParseError, ParseResult, decode


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------------- Nikon RAW


def parse_nikon_raw(data: bytes, angle_unit: AngleUnit = "gon") -> ParseResult:
    text = decode(data)
    res = ParseResult(format="nikon_raw", angle_unit=angle_unit)
    current: Setup | None = None
    coords: dict[str, ControlPoint] = {}
    seen = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or "," not in line:
            continue
        f = [x.strip() for x in line.split(",")]
        rec = f[0].upper()
        if rec in ("CO", "JB", "MO", "LS"):
            seen += 1
            continue
        if rec == "ST":
            seen += 1
            # ST,stn,stn_code,bs,bs_code,HI,BS_AZ,BS_HA
            stn = f[1] if len(f) > 1 else ""
            bs = f[3] if len(f) > 3 else ""
            hi = _num(f[5]) if len(f) > 5 else None
            current = Setup(station=stn, instrument_height=hi or 0.0, backsight=bs or None)
            res.setups.append(current)
            bs_ha = _num(f[7]) if len(f) > 7 else None
            if bs and bs_ha is not None:
                # backsight circle reading — lets the engine orient even without F1/F2 shots
                current.observations.append(
                    Observation(target=bs, hz=to_rad(bs_ha, angle_unit), v=None, sd=None)
                )
            continue
        if rec in ("SS", "F1", "F2", "CP", "TR"):
            seen += 1
            if current is None:
                res.warnings.append(f"Line {lineno}: observation before a ST record; skipped")
                continue
            pt = f[1] if len(f) > 1 else ""
            rest = f[2:]
            code = None
            if rest and (rest[0] == "" or _num(rest[0]) is None):
                code = rest[0] or None
                rest = rest[1:]
            ht, sd, ha, va = (rest + [""] * 4)[:4]
            tail = rest[4:]
            if tail:
                # time then code
                for t in tail[1:] if re.match(r"^\d{1,2}:\d{2}", tail[0] or "") else tail:
                    if t:
                        code = code or t
                        break
            h = _num(ha)
            if not pt or h is None:
                continue
            v = _num(va)
            d = _num(sd)
            if (
                current.backsight == pt
                and current.observations
                and current.observations[0].sd is None
            ):
                # replace the ST backsight reading with the measured shot
                current.observations.pop(0)
            current.observations.append(
                Observation(
                    target=pt,
                    hz=to_rad(h, angle_unit),
                    v=to_rad(v, angle_unit) if v is not None else None,
                    sd=d or None,
                    target_height=_num(ht) or 0.0,
                    code=code,
                )
            )
            continue
        if rec in ("UP", "KI", "CC", "XY"):
            # coordinate records: REC,PT,CODE,X(E),Y(N),Z
            pt = f[1] if len(f) > 1 else ""
            vals = [_num(x) for x in f[2:]]
            nums = [v for v in vals if v is not None]
            if pt and len(nums) >= 2:
                coords.setdefault(
                    pt,
                    ControlPoint(
                        name=pt, x=nums[0], y=nums[1], z=nums[2] if len(nums) > 2 else None
                    ),
                )
            seen += 1
    if not seen:
        raise ParseError("No Nikon RAW records found")
    res.control_points = list(coords.values())
    res.warnings.append(
        f"Angles read as {angle_unit}; Nikon RAW does not state its unit — check the project setting"
    )
    return res.finalise()


# ------------------------------------------------------------------------------- RW5

_RW5_KEY = re.compile(r"^(OP|FP|BP|AR|ZE|SD|HI|HR|BS|BC|PN|EL|N |E |N|E|--)\s*:?\s*(.*)$")


def _rw5_fields(parts: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in parts:
        p = p.strip()
        m = _RW5_KEY.match(p)
        if m:
            out.setdefault(m.group(1).strip(), m.group(2).strip())
    return out


def parse_rw5(data: bytes, angle_unit: AngleUnit = "gon") -> ParseResult:
    text = decode(data)
    res = ParseResult(format="rw5", angle_unit=angle_unit)
    current: Setup | None = None
    hi = 0.0
    hr = 0.0
    coords: dict[str, ControlPoint] = {}
    seen = 0
    obs_records = {"SS", "TR", "BD", "BR", "FD", "FR", "OB"}
    for _lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("--"):
            continue
        parts = [p for p in line.split(",")]
        rec = parts[0].strip().upper()
        f = _rw5_fields(parts[1:])
        if rec == "LS":
            seen += 1
            if "HI" in f and _num(f["HI"]) is not None:
                hi = _num(f["HI"]) or 0.0
                if current is not None and not current.observations:
                    current.instrument_height = hi
            if "HR" in f and _num(f["HR"]) is not None:
                hr = _num(f["HR"]) or 0.0
            continue
        if rec in ("OC", "SP"):
            seen += 1
            name = f.get("OP") or f.get("PN")
            n = _num(f.get("N")) if "N" in f else None
            e = _num(f.get("E")) if "E" in f else None
            if name and n is not None and e is not None:
                coords.setdefault(name, ControlPoint(name=name, x=e, y=n, z=_num(f.get("EL"))))
            if rec == "OC" and name:
                current = None  # next BK/obs starts a new setup on this point
                _oc_station = name
            continue
        if rec == "BK":
            seen += 1
            stn = f.get("OP", "")
            bp = f.get("BP")
            current = Setup(station=stn, instrument_height=hi, backsight=bp)
            res.setups.append(current)
            bc = _num(f.get("BC"))
            if bp and bc is not None:
                current.observations.append(Observation(target=bp, hz=to_rad(bc, angle_unit)))
            continue
        if rec in obs_records:
            seen += 1
            stn = f.get("OP", "")
            fp = f.get("FP", "")
            ar = _num(f.get("AR"))
            if not stn or not fp or ar is None:
                continue
            if current is None or current.station != stn:
                current = Setup(station=stn, instrument_height=hi)
                res.setups.append(current)
            ze = _num(f.get("ZE"))
            sd = _num(f.get("SD"))
            code = f.get("--") or None
            if (
                current.backsight == fp
                and current.observations
                and current.observations[0].sd is None
            ):
                current.observations.pop(0)
            current.observations.append(
                Observation(
                    target=fp,
                    hz=to_rad(ar, angle_unit),
                    v=to_rad(ze, angle_unit) if ze is not None else None,
                    sd=sd or None,
                    target_height=hr,
                    code=code,
                )
            )
            continue
    if not seen:
        raise ParseError("No RW5 records found")
    res.control_points = list(coords.values())
    res.warnings.append(
        f"Angles read as {angle_unit}; RW5 does not state its unit reliably — check the project "
        "setting"
    )
    return res.finalise()


# ------------------------------------------------------------------------------- CSV

_OBS_ALIASES = {
    "station": {"station", "stn", "stasi", "στάση", "σταση", "occupied"},
    "target": {"target", "fs", "point", "pt", "metrisi", "σημείο", "σημειο", "foresight"},
    "hz": {"hz", "h_angle", "ha", "horizontal", "orizontia", "οριζόντια", "οριζοντια"},
    "v": {"v", "v_angle", "va", "zenith", "ze", "katakorifi", "κατακόρυφη", "κατακορυφη"},
    "sd": {"sd", "slope_dist", "slope", "apostasi", "απόσταση", "αποσταση", "distance"},
    "hi": {"hi", "station_h", "instrument_height", "uo", "υο", "ih"},
    "ht": {"ht", "target_h", "target_height", "us", "υσ", "hr", "th"},
    "code": {"code", "κωδικός", "κωδικος", "description", "desc"},
}
_CP_ALIASES = {
    "name": {"name", "id", "point", "station", "pt", "όνομα", "ονομα", "σημείο", "σημειο"},
    "x": {"x", "e", "east", "easting"},
    "y": {"y", "n", "north", "northing"},
    "z": {"z", "h", "elev", "elevation", "height", "υψόμετρο", "υψομετρο"},
    "code": {"code", "κωδικός", "κωδικος", "description", "desc"},
}


def _sniff(text: str) -> tuple[list[list[str]], bool]:
    sample = text[:4096]
    delim = ","
    if sample.count(";") > sample.count(","):
        delim = ";"
    elif sample.count("\t") > sample.count(","):
        delim = "\t"
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    decimal_comma = delim != "," and bool(re.search(r"\d,\d", sample))
    if decimal_comma:
        rows = [[c.replace(",", ".") for c in r] for r in rows]
    return rows, decimal_comma


def _header_map(header: list[str], aliases: dict[str, set[str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, h in enumerate(header):
        key = h.strip().lower()
        for field, names in aliases.items():
            if key in names and field not in out:
                out[field] = i
    return out


def parse_csv(data: bytes, angle_unit: AngleUnit = "gon") -> ParseResult:
    text = decode(data)
    rows, _ = _sniff(text)
    if not rows:
        raise ParseError("Empty CSV file")
    header = rows[0]
    obs_map = _header_map(header, _OBS_ALIASES)
    cp_map = _header_map(header, _CP_ALIASES)
    res = ParseResult(format="csv", angle_unit=angle_unit)

    if {"station", "target", "hz"} <= obs_map.keys():
        current: Setup | None = None
        for r in rows[1:]:

            def g(field: str, r: list[str] = r) -> str | None:
                i = obs_map.get(field)
                return r[i].strip() if i is not None and i < len(r) else None

            stn, tgt, hz = g("station"), g("target"), _num(g("hz"))
            if not stn or not tgt or hz is None:
                continue
            hi = _num(g("hi")) or 0.0
            if current is None or current.station != stn or current.instrument_height != hi:
                current = Setup(station=stn, instrument_height=hi)
                res.setups.append(current)
            v = _num(g("v"))
            current.observations.append(
                Observation(
                    target=tgt,
                    hz=to_rad(hz, angle_unit),
                    v=to_rad(v, angle_unit) if v is not None else None,
                    sd=_num(g("sd")) or None,
                    target_height=_num(g("ht")) or 0.0,
                    code=g("code") or None,
                )
            )
        return res.finalise()

    # control points: with header, or headerless name,x,y[,z[,code]]
    if {"name", "x", "y"} <= cp_map.keys():
        body, m = rows[1:], cp_map
    else:
        body, m = rows, {"name": 0, "x": 1, "y": 2, "z": 3, "code": 4}
    for r in body:

        def c(field: str, r: list[str] = r) -> str | None:
            i = m.get(field)
            return r[i].strip() if i is not None and i < len(r) else None

        name, x, y = c("name"), _num(c("x")), _num(c("y"))
        if not name or x is None or y is None:
            continue
        res.control_points.append(
            ControlPoint(name=name, x=x, y=y, z=_num(c("z")), code=c("code") or None)
        )
    if not res.control_points:
        raise ParseError(
            "CSV not recognised: expected observation columns (station, target, hz, v, sd, hi, ht) "
            "or point columns (name, x, y, z)"
        )
    return res.finalise()
