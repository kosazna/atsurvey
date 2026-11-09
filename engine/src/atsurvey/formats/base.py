"""Common parser types. Every parser returns a :class:`ParseResult` with angles in radians."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..core.models import ControlPoint, Setup
from ..core.units import AngleUnit

FormatName = Literal["leica_gsi", "trimble_jobxml", "landxml", "nikon_raw", "rw5", "csv", "dxf"]


class ParseStats(BaseModel):
    setups: int = 0
    observations: int = 0
    control_points: int = 0


class ParseResult(BaseModel):
    format: FormatName
    angle_unit: AngleUnit | None = None
    setups: list[Setup] = Field(default_factory=list)
    control_points: list[ControlPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: ParseStats = Field(default_factory=ParseStats)

    def finalise(self) -> ParseResult:
        self.setups = [s for s in self.setups if s.observations]
        self.stats = ParseStats(
            setups=len(self.setups),
            observations=sum(len(s.observations) for s in self.setups),
            control_points=len(self.control_points),
        )
        return self


class ParseError(ValueError):
    """Raised when a file cannot be parsed in the requested format."""


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1253", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
