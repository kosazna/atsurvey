"""Field-code line work: join coded detail points into polylines."""

from __future__ import annotations

from .models import DetailShot, LineworkSettings, Polyline, ResultPoint


def build_linework(
    shots: list[DetailShot], points: list[ResultPoint], settings: LineworkSettings
) -> list[Polyline]:
    return []
