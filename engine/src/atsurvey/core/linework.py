"""Field-code line work: join coded detail points into polylines.

A point code is split on whitespace. The first token is the *feature*; it belongs to a line
code ``C`` when it equals ``C`` or is ``C`` followed by digits (``KR``, ``KR1``, ``KR2`` …), and
each distinct feature token is its own line (so ``KR1`` and ``KR2`` are two curbs). Further
tokens control the line:

* a start token (``ST``) closes any open line of that feature and starts a new one;
* a close token (``CL``) adds the point and closes the line into a polygon;
* an end token (``E``) adds the point and ends the line.

Points are taken in observation order (setup by setup, shot by shot), which is the order
they were measured in the field. Consecutive repeats of the same point are ignored.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .models import DetailShot, LineworkSettings, Polyline, ResultPoint


@dataclass
class _Open:
    code: str
    feature: str
    points: list[str] = field(default_factory=list)


def _norm(s: str, case_sensitive: bool) -> str:
    return s if case_sensitive else s.upper()


def build_linework(
    shots: list[DetailShot], points: list[ResultPoint], settings: LineworkSettings
) -> list[Polyline]:
    if not settings.line_codes:
        return []
    cs = settings.case_sensitive
    codes = {_norm(c.strip(), cs) for c in settings.line_codes if c.strip()}
    start = {_norm(t, cs) for t in settings.start_tokens}
    close = {_norm(t, cs) for t in settings.close_tokens}
    end = {_norm(t, cs) for t in settings.end_tokens}
    coords = {p.name: p for p in points}

    def line_code(feature: str) -> str | None:
        if feature in codes:
            return feature
        m = re.fullmatch(r"(.*?)(\d+)", feature)
        if m and m.group(1) in codes:
            return m.group(1)
        return None

    open_lines: dict[str, _Open] = {}
    finished: list[tuple[_Open, bool]] = []
    for shot in shots:
        if not shot.code or shot.target not in coords:
            continue
        tokens = [_norm(t, cs) for t in shot.code.split()]
        if not tokens:
            continue
        feature = tokens[0]
        code = line_code(feature)
        if code is None:
            continue
        controls = set(tokens[1:])
        current = open_lines.get(feature)
        if controls & start and current is not None:
            finished.append((current, False))
            current = None
        if current is None:
            current = open_lines[feature] = _Open(code=code, feature=feature)
        if not current.points or current.points[-1] != shot.target:
            current.points.append(shot.target)
        if controls & close:
            finished.append((current, True))
            del open_lines[feature]
        elif controls & end:
            finished.append((current, False))
            del open_lines[feature]
    finished.extend((line, False) for line in open_lines.values())

    counters: dict[str, int] = {}
    out: list[Polyline] = []
    for line, closed in finished:
        pts = line.points
        if closed and len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 2:
            continue
        closed = closed and len(pts) >= 3
        xy = [(coords[n].x, coords[n].y) for n in pts]
        segs = list(zip(xy, xy[1:] + ([xy[0]] if closed else []), strict=False))
        length = math.fsum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
        area = None
        if closed:
            # shoelace, centred on the first vertex to keep products small (ΕΓΣΑ87 magnitudes)
            x0, y0 = xy[0]
            rel = [(x - x0, y - y0) for x, y in xy]
            twice = math.fsum(
                a[0] * b[1] - b[0] * a[1] for a, b in zip(rel, rel[1:] + rel[:1], strict=True)
            )
            area = abs(twice) / 2.0
        counters[line.feature] = counters.get(line.feature, 0) + 1
        out.append(
            Polyline(
                code=line.code,
                name=f"{line.feature}#{counters[line.feature]}",
                points=pts,
                closed=closed,
                length=length,
                area=area,
            )
        )
    return out
