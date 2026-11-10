"""Contracts of the ΔΓΜ feature (Διάγραμμα Γεωμετρικών Μεταβολών, Hellenic Cadastre).

Conventions: x = Easting, y = Northing, metres, ΕΓΣΑ87; areas are grid areas (as registered by
the Cadastre). Parcels reuse :class:`~atsurvey.core.parcels_models.Parcel` (``kaek`` = ΚΑΕΚ).
See docs/dgm.md.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import Issue
from ..parcels_models import AreaToleranceRule, Parcel, ParcelVertex
from .spec import DiagramKind

MAX_PARCELS = 50
MAX_LINES = 20
MAX_LINE_VERTICES = 500
MAX_BUILDINGS = 100

Text = Annotated[str, Field(max_length=200)]
Kaek = Annotated[str, Field(min_length=1, max_length=32)]

#: subdivision / merge = ΔΓΜ for a deed; correction = ΔΓΜ for correction (or ΤΔΓΜ)
DgmMode = Literal["subdivision", "merge", "correction"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Polyline(_M):
    vertices: list[ParcelVertex] = Field(min_length=2, max_length=MAX_LINE_VERTICES)


class FinalPolygon(_M):
    """A final parcel of a correction (DGM_PROP_FINAL). ``kaek`` None = a new parcel («ΝΕΟ»)."""

    kaek: Kaek | None = None
    label: Text = ""
    vertices: list[ParcelVertex] = Field(min_length=3, max_length=1000)


class TitleBlock(_M):
    """Title block (πινακίδα) and the fields of the submission form ([S1], [S4] §6.2, [S10] §5)."""

    title: Text = ""
    author: Text = Field(default="", description="Μελετητής (συντάκτης μηχανικός)")
    author_details: Text = Field(default="", description="Ειδικότητα, Α.Μ. ΤΕΕ")
    client: Text = Field(default="", description="Εργοδότης")
    location: Text = Field(default="", description="Θέση / τοπωνύμιο")
    municipality: Text = Field(default="", description="Δήμος / Περιφερειακή Ενότητα")
    scale: int = Field(default=500, ge=1, le=100_000, description="1:scale")
    date: Annotated[str, Field(max_length=40)] = ""
    method: Literal["hepos", "other"] = Field(
        default="hepos", description="Μεθοδολογία εξάρτησης: HEPOS ή άλλη"
    )
    method_other: Text = ""
    notes: Annotated[str, Field(max_length=4000)] = ""
    tdgm: bool = Field(default=False, description="ΤΔΓΜ: add the engineer's declaration")


class DgmRequest(_M):
    """Build a ΔΓΜ.

    * ``subdivision`` (κατάτμηση): ``parcels`` holds the cadastral parcel(s) (PST_KAEK);
      ``subject`` (default: the first) is cut by ``partition_lines`` (the partition line of the
      topographic diagram). Line ends inside the parcel are extended to its boundary
      (``extend_lines``), parts outside are clipped: LINE_XM. DGM_PROP_FINAL = the parts.
    * ``merge`` (συνένωση): the parcels listed in ``merge`` (default: all) are united.
    * ``correction`` (διόρθωση / ΤΔΓΜ): ``parcels`` = subject(s) + affected neighbours;
      ``finals`` = the final polygons of ALL involved parcels; ``subjects`` = the KAEK being
      corrected. AREA_A / AREA_D come from overlaying PST_KAEK and DGM_PROP_FINAL.

    ``topo_prop`` (surveyed property, TOPO_PROP) is optional for a deed but required by the
    Cadastre for a correction; its outline is also written on BOUND_IMPL or BOUND_UNIMPL.
    """

    mode: DgmMode
    parcels: list[Parcel] = Field(min_length=1, max_length=MAX_PARCELS)
    subject: Kaek | None = None
    partition_lines: list[Polyline] = Field(default_factory=list, max_length=MAX_LINES)
    extend_lines: bool = True
    part_labels: list[Text] | None = Field(default=None, max_length=MAX_PARCELS)
    merge: list[Kaek] = Field(default_factory=list, max_length=MAX_PARCELS)
    subjects: list[Kaek] = Field(default_factory=list, max_length=MAX_PARCELS)
    finals: list[FinalPolygon] = Field(default_factory=list, max_length=MAX_PARCELS)
    topo_prop: list[Parcel] = Field(default_factory=list, max_length=MAX_PARCELS)
    topo_prop_new: list[Parcel] = Field(default_factory=list, max_length=MAX_PARCELS)
    buildings: list[Parcel] = Field(default_factory=list, max_length=MAX_BUILDINGS)
    boundary: Literal["implemented", "unimplemented"] = Field(
        default="unimplemented",
        description="Layer for the TOPO_PROP outline: BOUND_IMPL or BOUND_UNIMPL",
    )
    snap_tolerance: Annotated[float, Field(allow_inf_nan=False, gt=0, le=0.05)] = Field(
        default=0.001,
        description="Final vertices this close to a cadastral vertex take its exact coordinates, m",
    )
    tolerance: AreaToleranceRule | None = Field(
        default=None, description="Area tolerance for the comparisons (Cadastre rule)"
    )
    new_point_prefix: Annotated[str, Field(max_length=8)] = "Ν"
    title: TitleBlock = Field(default_factory=TitleBlock)


class DgmPolygon(_M):
    layer: str
    label: str
    kaek: str | None = None
    vertices: list[ParcelVertex] = Field(description="Named vertices, first not repeated")
    area: float
    perimeter: float


class DgmLine(_M):
    layer: str
    vertices: list[ParcelVertex]


class DgmPoint(_M):
    name: str
    x: float
    y: float
    new: bool = Field(default=False, description="Computed by the ΔΓΜ (intersection)")


class AreaRow(_M):
    """Areas before (cadastral) and after (final), m² (Πίνακας εμβαδών)."""

    label: str
    kaek: str | None
    before: float | None
    after: float | None
    difference: float | None


class AreaComparison(_M):
    """Cadastral area E against another area, with the Cadastre's tolerance (Π = perimeter on
    the cadastral diagram, ΟΚΧΕ 461/03/2008)."""

    label: str
    kaek: str | None
    against: Literal["survey", "final"]
    cadastre_area: float
    other_area: float
    difference: float
    difference_percent: float
    perimeter: float
    tolerance: float | None
    within: bool | None


class ChangeRow(_M):
    """One row of the change table «ΤΜΗΜΑ / ΠΕΡΙΓΡΑΦΗ / ΕΜΒΑΔΟ / ΑΠΟ ΚΑΕΚ / ΣΕ ΚΑΕΚ» ([S4] §6.2)."""

    part: str
    kind: Literal["A", "D"]
    description: list[str] = Field(description="Closed vertex sequence, e.g. 28,29,30,28")
    area: float
    from_kaek: str
    to_kaek: str = Field(description="KAEK, or «ΝΕΟ» for a part excluded from the parcel")


class DgmResult(_M):
    mode: DgmMode
    kind: DiagramKind
    polygons: list[DgmPolygon]
    lines: list[DgmLine]
    points: list[DgmPoint]
    areas: list[AreaRow]
    comparisons: list[AreaComparison]
    changes: list[ChangeRow]
    total_before: float
    total_after: float
    ok: bool = Field(description="No errors: the drawing should pass the Cadastre's checks")
    issues: list[Issue]


# ------------------------------------------------------------------- ΚΔ DXF (input) reader


class KdParcel(_M):
    kaek: str | None
    layer: str
    handle: str | None
    vertices: list[ParcelVertex]
    area: float


class KdReadResult(_M):
    parcels: list[KdParcel]
    issues: list[Issue]


# --------------------------------------------------------------------------- validation


class CheckResult(_M):
    id: str
    status: Literal["pass", "fail", "warn", "skip"]
    issues: list[Issue]


class LayerSummary(_M):
    name: str
    table_no: int | None = Field(description="Row of Table I, None for a free layer")
    counts: dict[str, int] = Field(description="Entities per DXF type")


class PreviewShape(_M):
    layer: str
    closed: bool
    coords: list[tuple[float, float]]


class ValidationReport(_M):
    kind: DiagramKind
    filename: str | None
    size: int
    sha512: str
    dxf_version: str | None
    ok: bool = Field(description="No errors found (the Cadastre's own system is authoritative)")
    checks: list[CheckResult]
    layers: list[LayerSummary]
    preview: list[PreviewShape]
    preview_truncated: bool = False
