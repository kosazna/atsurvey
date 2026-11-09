"""Topcon GTS-7 raw data (BETA — written from the published record layout; verify with real
files before relying on it).

Records (comma-separated values after a record keyword)::

    STN  point,HI[,code]          new setup
    XYZ  X,Y,Z                    coordinates of the preceding STN/BS/FS/SS point
    BKB  point,azimuth,HZ         backsight by bearing (circle reading HZ to point)
    BS   point,HT                 backsight target
    FS   point,HT[,code]          foresight target   } followed by an observation
    SS   point,HT[,code]          sideshot target    }
    SD   HZ,VZ,SD                 horizontal circle, zenith, slope distance
    HD   HZ,HD,VD                 horizontal circle, horizontal distance, height difference
    HV   HZ,VZ                    angles only
    UNITS M,G | M,D               metres; G = gon, D = degrees

The angle unit comes from ``UNITS`` when present (G → gon, D → decimal degrees), otherwise
from the project setting.
"""

from __future__ import annotations

import math
import re

from ..core.models import ControlPoint, Observation, Setup
from ..core.units import AngleUnit, to_rad
from .base import ParseError, ParseResult, decode

_REC = re.compile(r"^\s*([A-Z]{2,5})\s+(.*)$")


def _num(s: str | None) -> float | None:
    if s is None or not s.strip():
        return None
    try:
        return float(s.strip())
    except ValueError:
        return None


def parse_topcon_gts7(data: bytes, angle_unit: AngleUnit = "gon") -> ParseResult:
    text = decode(data)
    res = ParseResult(format="topcon_gts7", angle_unit=angle_unit)
    unit: AngleUnit = angle_unit
    current: Setup | None = None
    target: tuple[str, float, str | None] | None = None  # point, HT, code
    last_point: str | None = None
    coords: dict[str, ControlPoint] = {}
    seen = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        m = _REC.match(raw)
        if not m:
            continue
        rec, rest = m.group(1).upper(), m.group(2)
        f = [x.strip() for x in rest.split(",")]
        if rec == "UNITS":
            seen += 1
            if len(f) > 1 and f[1].upper().startswith("G"):
                unit = "gon"
            elif len(f) > 1 and f[1].upper().startswith("D"):
                unit = "deg"
            res.angle_unit = unit
        elif rec == "STN":
            seen += 1
            current = Setup(
                station=f[0], instrument_height=_num(f[1] if len(f) > 1 else None) or 0.0
            )
            res.setups.append(current)
            target = None
            last_point = f[0]
        elif rec == "XYZ":
            seen += 1
            x, y, z = (_num(v) for v in ([*f, "", "", ""])[:3])
            if last_point and x is not None and y is not None:
                coords.setdefault(last_point, ControlPoint(name=last_point, x=x, y=y, z=z))
        elif rec == "BKB":
            seen += 1
            if current is not None and f and _num(f[2] if len(f) > 2 else None) is not None:
                hz = _num(f[2])
                assert hz is not None
                current.backsight = f[0]
                current.observations.append(Observation(target=f[0], hz=to_rad(hz, unit)))
        elif rec in ("BS", "FS", "SS"):
            seen += 1
            ht = _num(f[1] if len(f) > 1 else None) or 0.0
            code = f[2] if len(f) > 2 and f[2] else None
            target = (f[0], ht, code)
            last_point = f[0]
        elif rec in ("SD", "HD", "HV"):
            seen += 1
            if current is None or target is None:
                res.warnings.append(f"Line {lineno}: observation without station/target; skipped")
                continue
            vals = [_num(v) for v in f]
            hz = vals[0] if vals else None
            if hz is None:
                continue
            v = sd = None
            if rec == "SD" and len(vals) >= 3:
                v = to_rad(vals[1], unit) if vals[1] is not None else None
                sd = vals[2]
            elif rec == "HV" and len(vals) >= 2:
                v = to_rad(vals[1], unit) if vals[1] is not None else None
            elif rec == "HD" and len(vals) >= 3 and vals[1] is not None:
                hd, vd = vals[1], vals[2] or 0.0
                sd = math.hypot(hd, vd)
                v = math.atan2(hd, vd)
            name, ht, code = target
            if (
                current.backsight == name
                and current.observations
                and current.observations[0].sd is None
            ):
                current.observations.pop(0)  # replace the BKB reading with the measured shot
            current.observations.append(
                Observation(
                    target=name,
                    hz=to_rad(hz, unit),
                    v=v,
                    sd=sd or None,
                    target_height=ht,
                    code=code,
                )
            )
    if not seen:
        raise ParseError("No Topcon GTS-7 records found")
    res.control_points = list(coords.values())
    res.warnings.append(
        "Topcon GTS-7 support is in beta: check the first computed points against the field notes"
    )
    if res.angle_unit is None:
        res.angle_unit = unit
    return res.finalise()
