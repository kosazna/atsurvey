"""Geometric (spirit) levelling lines.

Each setup has one backsight (``bs``) and one foresight (``fs``) reading, plus any number
of intermediate sights (``is``). Heights are carried from the starting benchmark through the
turning points: ``HI = H(bs) + bs``, ``H(fs) = HI − fs``, ``H(is) = HI − is``. When the line
ends on a benchmark (or returns to its start) the misclosure ``w = H_known − H_computed``
is distributed in proportion to the cumulative sight length or equally per setup.
Intermediate sights receive the correction of their setup's height of collimation,
interpolated between the backsight and the foresight of that setup.
"""

from __future__ import annotations

import math

from .cogo_models import (
    LevelingPoint,
    LevelingReading,
    LevelingRequest,
    LevelingResult,
    LevelingRow,
)


def _split(i: int, readings: list[LevelingReading]):
    bs = [r for r in readings if r.kind == "bs"]
    fs = [r for r in readings if r.kind == "fs"]
    if len(bs) != 1 or len(fs) != 1:
        raise ValueError(f"Setup {i + 1} needs exactly one backsight and one foresight reading")
    return bs[0], fs[0], [r for r in readings if r.kind == "is"]


def level(req: LevelingRequest) -> LevelingResult:
    bench = {b.name: b.h for b in req.benchmarks}
    parsed = [_split(i, s.readings) for i, s in enumerate(req.setups)]
    for i in range(len(parsed) - 1):
        if parsed[i][1].point != parsed[i + 1][0].point:
            raise ValueError(
                f"Setup {i + 2} must start on the foresight point of setup {i + 1} "
                f"({parsed[i][1].point}), not {parsed[i + 1][0].point}"
            )
    start = parsed[0][0].point
    if start not in bench:
        raise ValueError(f"The line must start on a benchmark ({start} has no known height)")
    end = parsed[-1][1].point
    n = len(parsed)

    # raw heights
    h = bench[start]
    his: list[float] = []
    raw_fs: list[float] = []
    rows: list[LevelingRow] = []
    lengths: list[float | None] = []
    for i, (bs, fs, _) in enumerate(parsed):
        hi = h + bs.reading
        his.append(hi)
        h = hi - fs.reading
        raw_fs.append(h)
        ln = (
            bs.distance + fs.distance
            if bs.distance is not None and fs.distance is not None
            else None
        )
        lengths.append(ln)
        rows.append(
            LevelingRow(
                setup=i + 1,
                backsight=bs.point,
                foresight=fs.point,
                dh=bs.reading - fs.reading,
                length=ln,
            )
        )

    all_lengths = all(ln is not None for ln in lengths)
    total = math.fsum(ln or 0.0 for ln in lengths) if all_lengths else None
    length_km = total / 1000.0 if total is not None else None

    message = None
    misclosure = None
    if end in bench:
        misclosure = bench[end] - raw_fs[-1]

    # cumulative correction at the end of each setup, and the share at its backsight
    mode = req.distribute
    if misclosure is not None and mode == "distance" and (not all_lengths or not total):
        mode = "setups"
        message = "Sight distances are missing; the misclosure was distributed equally per setup"
    cum: list[float] = []
    frac_bs: list[float] = []
    w = misclosure or 0.0
    acc = 0.0
    for i, (bs, _fs, _) in enumerate(parsed):
        if mode == "distance" and total:
            share = (lengths[i] or 0.0) / total
            frac = (bs.distance or 0.0) / (lengths[i] or 1.0) if lengths[i] else 0.5
        else:
            share = 1.0 / n
            frac = 0.5
        acc += share
        cum.append(w * acc)
        frac_bs.append(frac)

    tolerance = within = None
    if misclosure is not None:
        if length_km is not None:
            tolerance = (
                req.tolerance_base_mm + req.tolerance_mm_per_sqrt_km * math.sqrt(length_km)
            ) / 1000.0
            within = abs(misclosure) <= tolerance
        elif message is None:
            message = "Sight distances are missing; the tolerance cannot be evaluated"
    else:
        message = message or f"Open line: {end} is not a benchmark, so the line is not checked"

    points: list[LevelingPoint] = []
    seen: set[str] = set()

    def add(p: LevelingPoint) -> None:
        if p.name not in seen:
            seen.add(p.name)
            points.append(p)

    add(
        LevelingPoint(
            name=start, h=bench[start], h_unadjusted=bench[start], correction=0.0, kind="benchmark"
        )
    )
    prev_corr = 0.0
    for i, (_bs, fs, inter) in enumerate(parsed):
        setup_corr = cum[i] - prev_corr
        for r in inter:
            corr = prev_corr + setup_corr * frac_bs[i]
            raw = his[i] - r.reading
            add(
                LevelingPoint(
                    name=r.point,
                    h=raw + corr,
                    h_unadjusted=raw,
                    correction=corr,
                    kind="intermediate",
                )
            )
        is_bench = fs.point in bench
        corr = cum[i] if misclosure is not None else 0.0
        if i == n - 1 and is_bench:
            add(
                LevelingPoint(
                    name=fs.point,
                    h=bench[fs.point],
                    h_unadjusted=raw_fs[i],
                    correction=corr,
                    kind="benchmark",
                )
            )
        else:
            add(
                LevelingPoint(
                    name=fs.point,
                    h=raw_fs[i] + corr,
                    h_unadjusted=raw_fs[i],
                    correction=corr,
                    kind="benchmark" if is_bench else "turning",
                )
            )
        prev_corr = cum[i]

    return LevelingResult(
        points=points,
        rows=rows,
        start=start,
        end=end,
        misclosure=misclosure,
        tolerance=tolerance,
        within_tolerance=within,
        length_km=length_km,
        n_setups=n,
        message=message,
    )
