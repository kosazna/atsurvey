"""In-memory drawing: the Table I content of a DXF as plain shapes.

Both the ΔΓΜ builder (before writing) and the DXF validator (after reading any CAD file) run
the same topology checks on this model, so a drawing ATSurvey builds is checked exactly like an
uploaded one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Pt = tuple[float, float]


@dataclass(frozen=True)
class Shape:
    layer: str
    form: Literal["polygon", "polyline", "text", "point"]
    coords: tuple[Pt, ...]
    handle: str | None = None
    text: str | None = None


@dataclass
class Drawing:
    shapes: list[Shape] = field(default_factory=list)

    def on(self, layer: str, form: str | None = None) -> list[Shape]:
        return [s for s in self.shapes if s.layer == layer and (form is None or s.form == form)]

    def layers_with_content(self) -> set[str]:
        return {s.layer for s in self.shapes}
