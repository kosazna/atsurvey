"""Tolerance presets for traverses.

The Greek specification table (as used in the reference workbooks): limits depend on the map
scale, the traverse class (primary/secondary) and the terrain (flat/sloped).

* linear misclosure  w ≤ a·√L + b      (L = traverse length in **metres**)
* angular misclosure wβ ≤ k·√n  c      (n = number of angles; 1 c = 0.01 grad = 100 cc)

Relative precision (1:N) is not part of this specification, so presets disable it. Height
misclosure limits are not in the table either; the defaults are kept.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .models import Tolerances

Scale = Literal["1/200", "1/500", "1/1000", "1/2000", "1/5000", "1/10000"]
TraverseClass = Literal["primary", "secondary"]
Terrain = Literal["flat", "sloped"]

#: (terrain, class) → scale → (a, b, k): w ≤ a·√L(m) + b, wβ ≤ k·√n (c)
GREEK_TRAVERSE: dict[tuple[str, str], dict[str, tuple[float, float, float]]] = {
    ("flat", "primary"): {
        "1/200": (0.005, 0.05, 1),
        "1/500": (0.005, 0.05, 2),
        "1/1000": (0.01, 0.1, 2),
        "1/2000": (0.02, 0.1, 2),
        "1/5000": (0.04, 0.2, 3),
        "1/10000": (0.1, 0.3, 3),
    },
    ("flat", "secondary"): {
        "1/200": (0.01, 0.05, 1.5),
        "1/500": (0.01, 0.05, 3),
        "1/1000": (0.02, 0.1, 5),
        "1/2000": (0.04, 0.1, 5),
        "1/5000": (0.06, 0.2, 5),
        "1/10000": (0.15, 0.3, 5),
    },
    ("sloped", "primary"): {
        "1/200": (0.01, 0.1, 2),
        "1/500": (0.01, 0.1, 3),
        "1/1000": (0.02, 0.2, 5),
        "1/2000": (0.04, 0.2, 5),
        "1/5000": (0.06, 0.4, 5),
        "1/10000": (0.15, 0.3, 5),
    },
    ("sloped", "secondary"): {
        "1/200": (0.02, 0.1, 3),
        "1/500": (0.02, 0.1, 5),
        "1/1000": (0.04, 0.2, 8),
        "1/2000": (0.08, 0.2, 8),
        "1/5000": (0.1, 0.4, 8),
        "1/10000": (0.2, 0.3, 8),
    },
}

TERRAIN_EL = {"flat": "Ομαλό", "sloped": "Κεκλιμένο"}
CLASS_EL = {"primary": "Πρωτεύουσα", "secondary": "Δευτερεύουσα"}


class TolerancePreset(BaseModel):
    id: str
    label_el: str
    label_en: str
    scale: Scale
    traverse_class: TraverseClass
    terrain: Terrain
    tolerances: Tolerances


def greek_tolerances(
    scale: Scale, traverse_class: TraverseClass, terrain: Terrain, base: Tolerances | None = None
) -> Tolerances:
    a, b, k = GREEK_TRAVERSE[(terrain, traverse_class)][scale]
    base = base or Tolerances()
    return base.model_copy(
        update={
            "angular_base_cc": 0.0,
            "angular_per_sqrt_n_cc": k * 100.0,
            "linear_base_m": b,
            "linear_per_sqrt_km_m": 0.0,
            "linear_per_sqrt_m_m": a,
            "min_relative_precision": 0.0,
            "preset": f"gr:{terrain}:{traverse_class}:{scale}",
        }
    )


def tolerance_presets() -> list[TolerancePreset]:
    out = []
    for (terrain, cls), table in GREEK_TRAVERSE.items():
        for scale in table:
            out.append(
                TolerancePreset(
                    id=f"gr:{terrain}:{cls}:{scale}",
                    label_el=f"{CLASS_EL[cls]} · {TERRAIN_EL[terrain]} · {scale}",
                    label_en=f"{cls.capitalize()} · {terrain} · {scale}",
                    scale=scale,  # type: ignore[arg-type]
                    traverse_class=cls,  # type: ignore[arg-type]
                    terrain=terrain,  # type: ignore[arg-type]
                    tolerances=greek_tolerances(scale, cls, terrain),  # type: ignore[arg-type]
                )
            )
    return out
