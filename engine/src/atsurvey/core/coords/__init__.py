"""Coordinate systems used in Greece: ΕΓΣΑ87, UTM, TM3, Hatt, geographic; datum shifts.

See docs/coords.md. Public entry points: ``convert`` and ``point_info``.
"""

from .convert import convert, point_info
from .errors import CoordsError
from .models import (
    ConvertedPoint,
    ConvertRequest,
    ConvertResult,
    CoordPoint,
    HattSpec,
    PointInfoRequest,
    PointInfoResult,
    SystemId,
)

__all__ = [
    "ConvertRequest",
    "ConvertResult",
    "ConvertedPoint",
    "CoordPoint",
    "CoordsError",
    "HattSpec",
    "PointInfoRequest",
    "PointInfoResult",
    "SystemId",
    "convert",
    "point_info",
]
