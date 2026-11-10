"""Contracts for terrain surfaces (TIN), contours, heights, volumes and profiles.

Coordinates are metres, x = Easting, y = Northing, z = orthometric height (ΕΓΣΑ87).
Every list and number is bounded so that a single request cannot exhaust CPU or memory.
Implementation: ``core/surfaces/*``; API routes ``/v1/surfaces/*`` (docs/surfaces.md).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Issue

MAX_POINTS = 50_000
MAX_BREAKLINES = 1_000
MAX_BREAKLINE_VERTICES = 20_000
MAX_BOUNDARY_VERTICES = 2_000
MAX_QUERY_POINTS = 10_000
MAX_ALIGNMENT_VERTICES = 500
MAX_SECTIONS = 2_000
MAX_CONTOUR_LEVELS = 2_000
MAX_CONTOUR_VERTICES = 1_000_000

Coord = Annotated[float, Field(ge=-1e8, le=1e8)]
Height = Annotated[float, Field(ge=-20_000, le=20_000)]
Name = Annotated[str, Field(max_length=100)]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SurfacePoint(_M):
    name: Name | None = None
    x: Coord
    y: Coord
    z: Height | None = Field(default=None, description="Points without a height are excluded")


class PlanXY(_M):
    x: Coord
    y: Coord


class NamedXY(_M):
    name: Name | None = None
    x: Coord
    y: Coord


class Breakline(_M):
    """A polyline of surface point names whose segments become TIN edges."""

    points: list[Name] = Field(min_length=2, max_length=5_000)
    closed: bool = False


class SurfaceSpec(_M):
    points: list[SurfacePoint] = Field(min_length=1, max_length=MAX_POINTS)
    breaklines: list[Breakline] = Field(default_factory=list, max_length=MAX_BREAKLINES)
    boundary: list[PlanXY] | None = Field(
        default=None,
        max_length=MAX_BOUNDARY_VERTICES,
        description="Simple polygon (no closing vertex needed); the surface is clipped to it",
    )
    max_edge: float | None = Field(
        default=None,
        gt=0,
        le=1e6,
        description="Peel triangles from the outside whose boundary edge is longer than this (m)",
    )
    duplicate_tolerance: float = Field(
        default=0.001, ge=0, le=1, description="Points closer than this in plan are merged (m)"
    )

    @model_validator(mode="after")
    def _bounds(self) -> SurfaceSpec:
        n = sum(len(b.points) for b in self.breaklines)
        if n > MAX_BREAKLINE_VERTICES:
            raise ValueError(f"Too many breakline vertices ({n} > {MAX_BREAKLINE_VERTICES})")
        if self.boundary is not None and len(self.boundary) < 3:
            raise ValueError("The boundary needs at least 3 vertices")
        return self


class DuplicateGroup(_M):
    kept: str | None
    merged: list[str | None]
    dz: float = Field(description="Height spread of the merged points (m)")


class SurfaceStats(_M):
    points_in: int
    points_without_z: int
    duplicates_merged: int
    vertices: int = Field(description="Vertices of the final TIN")
    triangles: int
    z_min: float
    z_max: float
    area_2d: float = Field(description="Plan area covered by the surface (m²)")
    area_3d: float = Field(description="Sloped (true) area of the surface (m²)")
    breakline_segments: int = Field(description="Breakline segments enforced as TIN edges")
    trimmed_triangles: int


class SurfaceResult(_M):
    stats: SurfaceStats
    outline: list[list[tuple[float, float]]] = Field(
        description="Closed rings of the surface border (plan), first vertex not repeated"
    )
    duplicates: list[DuplicateGroup] = Field(description="First 200 merged groups")
    issues: list[Issue]


class SurfaceRequest(_M):
    surface: SurfaceSpec


# ------------------------------------------------------------------------------ contours


class ContoursRequest(_M):
    surface: SurfaceSpec
    interval: float = Field(gt=0, le=1_000, description="Contour interval (m)")
    base: float = Field(
        default=0.0, ge=-20_000, le=20_000, description="Levels are base + k·interval"
    )
    index_every: int = Field(
        default=5, ge=0, le=100, description="Index contour every N (0 = none)"
    )


class ContourLine(_M):
    z: float
    index: bool
    closed: bool
    points: list[tuple[float, float]]


class ContoursResult(_M):
    surface: SurfaceResult
    interval: float
    base: float
    levels: list[float]
    lines: list[ContourLine]
    issues: list[Issue]


# ------------------------------------------------------------------------------- heights


class HeightsRequest(_M):
    surface: SurfaceSpec
    points: list[NamedXY] = Field(min_length=1, max_length=MAX_QUERY_POINTS)


class HeightRow(_M):
    name: str | None
    x: float
    y: float
    z: float | None = Field(description="Interpolated height; null outside the surface")
    inside: bool


class HeightsResult(_M):
    surface: SurfaceResult
    rows: list[HeightRow]
    issues: list[Issue]


# ------------------------------------------------------------------------------- volumes


class LevelVolumeRequest(_M):
    surface: SurfaceSpec
    level: Height = Field(description="Horizontal reference plane (m)")


class SurfaceVolumeRequest(_M):
    existing: SurfaceSpec = Field(description="Existing ground (e.g. first survey)")
    design: SurfaceSpec = Field(description="Design or second survey")
    boundary: list[PlanXY] | None = Field(
        default=None, max_length=MAX_BOUNDARY_VERTICES, description="Applied to both surfaces"
    )


class VolumeResult(_M):
    method: str
    reference: Literal["level", "surface"]
    level: float | None = None
    cut: float = Field(description="Volume where the surface is above the reference (m³)")
    fill: float = Field(description="Volume where the surface is below the reference (m³)")
    net: float = Field(description="cut − fill (m³)")
    cut_area: float = Field(description="Plan area in cut (m²)")
    fill_area: float = Field(description="Plan area in fill (m²)")
    area: float = Field(description="Plan area evaluated (m²)")
    surfaces: list[SurfaceResult]
    issues: list[Issue]


# ------------------------------------------------------------------------------ profiles


class ProfileRequest(_M):
    surface: SurfaceSpec
    alignment: list[PlanXY] = Field(min_length=2, max_length=MAX_ALIGNMENT_VERTICES)
    section_interval: float | None = Field(
        default=None, gt=0, le=100_000, description="Cross-sections every … m of chainage"
    )
    half_width: float = Field(default=10.0, gt=0, le=1_000, description="Cross-section half width")


class ProfileStation(_M):
    chainage: float = Field(description="Along the alignment (long profile) or offset (section)")
    x: float
    y: float
    z: float
    run: int = Field(
        description="Continuous part of the line on the surface (gaps start a new run)"
    )


class CrossSection(_M):
    chainage: float
    x: float
    y: float
    z: float | None
    azimuth: float = Field(description="Azimuth of the alignment at the section (rad)")
    stations: list[ProfileStation] = Field(description="chainage = offset, negative to the left")


class ProfileResult(_M):
    surface: SurfaceResult
    length: float
    stations: list[ProfileStation]
    sections: list[CrossSection]
    issues: list[Issue]


# ------------------------------------------------------------------------------- exports

ExportContent = Literal["contours", "heights", "volume", "profile"]


class SurfaceExportRequest(_M):
    format: Literal["dxf", "csv"]
    content: ExportContent
    project_name: str = Field(default="surface", max_length=200)
    contours: ContoursRequest | None = None
    heights: HeightsRequest | None = None
    volume_level: LevelVolumeRequest | None = None
    volume_surfaces: SurfaceVolumeRequest | None = None
    profile: ProfileRequest | None = None
    include_tin: bool = Field(default=False, description="DXF: TIN as 3DFACE entities")
    include_points: bool = Field(default=True, description="DXF: surface points")
    text_height: float = Field(default=0.5, gt=0, le=50)
    vertical_exaggeration: float = Field(default=10.0, gt=0, le=100)
    decimals: int = Field(default=3, ge=0, le=6)
    csv_delimiter: Literal[",", ";", "\t"] = ","
    workspace_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
