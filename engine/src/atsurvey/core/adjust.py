"""Least-squares network adjustment (implemented by the adjustment workstream).

Contract
--------
``adjust_network`` is called after the traverses (whose coordinates serve as approximate
values) and before the detail points. It adjusts every *network point* — points that are not
control points and that are occupied stations or traverse points — using all reduced
directions, distances and height differences between network points and control points.
It updates ``known`` in place (x, y, z, sx, sy, sz, ellipse) and returns the adjustment
summary, or ``None`` when there is nothing to adjust (the reason is reported as an issue).
"""

from __future__ import annotations

from .issues import IssueSink
from .models import AdjustmentResult, AdjustmentSettings, ReductionSettings
from .reduce import ObservationIndex, ReducedSetup
from .traverse import KnownPoint


def adjust_network(
    setups: list[ReducedSetup],
    index: ObservationIndex,
    known: dict[str, KnownPoint],
    fixed: set[str],
    rs: ReductionSettings,
    settings: AdjustmentSettings,
    sink: IssueSink,
) -> AdjustmentResult | None:
    sink.info("ADJUSTMENT_UNAVAILABLE", "Least-squares adjustment is not available yet")
    return None
