"""A synthetic cadastral diagram (ΚΔ) for tests and the "example" button of the web tool.

Three adjacent parcels in ΕΓΣΑ87 with millimetre coordinates (made-up KAEK and coordinates,
not real cadastral data). A and B share a side; C lies north of both and shares their north
sides, including the common vertex 3:

        5 ─────────────────── 6 ──── 8   (C = 4,3,7,8,5 … north)
        │          C                 │
        4 ──────── 3 ─────────────── 7
        │    A     │       B         │
        1 ──────── 2 ─────────────── 9
"""

from __future__ import annotations

from ..parcels_models import Parcel, ParcelVertex

KAEK_A = "050681703001"
KAEK_B = "050681703002"
KAEK_C = "050681703003"

P1 = (476200.123, 4205100.456)
P2 = (476230.789, 4205101.234)
P3 = (476231.567, 4205140.890)
P4 = (476199.345, 4205139.012)
P9 = (476262.111, 4205102.222)
P7 = (476263.333, 4205141.444)
P8 = (476262.904, 4205170.517)
P5 = (476198.712, 4205168.338)

POINTS = {"1": P1, "2": P2, "3": P3, "4": P4, "5": P5, "7": P7, "8": P8, "9": P9}


def _parcel(kaek: str, names: list[str]) -> Parcel:
    return Parcel(
        kaek=kaek,
        vertices=[ParcelVertex(name=n, x=POINTS[n][0], y=POINTS[n][1]) for n in names],
    )


def sample_parcels() -> list[Parcel]:
    """PST_KAEK of the sample ΚΔ: A (≈1220 m²), B (≈1260 m²), C (≈1870 m²)."""
    return [
        _parcel(KAEK_A, ["1", "2", "3", "4"]),
        _parcel(KAEK_B, ["2", "9", "7", "3"]),
        _parcel(KAEK_C, ["4", "3", "7", "8", "5"]),
    ]
