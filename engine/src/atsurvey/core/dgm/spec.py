"""The Hellenic Cadastre's rules for electronic diagrams, encoded as data.

Sources (all published by the Hellenic Cadastre, Ελληνικό Κτηματολόγιο):

* [S1] «Τεύχος Τεχνικών Προδιαγραφών για την Ηλεκτρονική Υποβολή Διαγραμμάτων», v1.3
  (Dec 2024): Table I (ΠΙΝΑΚΑΣ Ι) of layers, §4.3 file names, §4.5.1 general DXF rules,
  §4.5.2 completeness rules, §4.5.3 topology rules, §5 checks.
* [S5] «Ηλεκτρονική υποβολή διαγραμμάτων — Συχνές ερωτήσεις» v1.2: ΣΤ.5 (no blocks, hatches,
  images, xrefs; layer names uppercase without spaces), ΣΤ.10–13 (typical failures: a shared
  vertex missing in one of two adjacent polygons, a duplicate polygon, PST_KAEK ≠
  DGM_PROP_FINAL union, KAEK text inside its polygon, no stray closed shapes on PST_KAEK, TEXT
  not MTEXT, 2D only).
* [S9] Official layer template «PINAKAS I LAYERS MODEL AN ΕΚ.dxf»: AC1018 (DXF 2004),
  $INSUNITS = 6 (metres), $DWGCODEPAGE = ANSI_1253, the suggested ACI colours, linetypes and
  lineweights below (optional, FAQ B.8).
* [S3] Κτηματολόγιο Α.Ε., οδηγός σύνταξης ΔΓΜ: KAEK = 12 digits (2 prefecture, 3 municipality,
  2 sector, 2 block, 3 parcel serial).
* [S4] Οδηγία ΤΔΓΜ (Ν.4602/2019) §6.2: change table columns and the engineer's declaration.

Note: the PDF of [S1] prints row 26 as ``AREA_Α`` with a Greek capital alpha (U+0391); the
template DXF and the body text use Latin ``AREA_A``, which is what is written and expected here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

#: ΤΔ (topographic diagram), ΔΓΜ for a deed (εγγραπτέα πράξη), ΔΓΜ for correction / ΤΔΓΜ
DiagramKind = Literal["topo", "deed", "correction"]

#: Entity forms of Table I column (4)
Form = Literal["polygon", "polyline", "text", "point"]


@dataclass(frozen=True)
class LayerSpec:
    no: int
    name: str
    description: str
    forms: frozenset[str]
    kinds: frozenset[str]
    color: int
    linetype: str = "Continuous"
    lineweight: int = -3  # -3 = default


def _l(
    no: int,
    name: str,
    description: str,
    forms: tuple[str, ...],
    kinds: str,
    color: int,
    linetype: str = "Continuous",
    lineweight: int = -3,
) -> LayerSpec:
    kind_map = {"T": "topo", "P": "deed", "D": "correction"}
    return LayerSpec(
        no,
        name,
        description,
        frozenset(forms),
        frozenset(kind_map[k] for k in kinds),
        color,
        linetype,
        lineweight,
    )


_PL = ("polygon", "polyline")
_LT = ("polyline", "text")
_PT = ("polygon", "text")
DASHED = "JIS_02_2.0"

#: Table I of [S1] (layer no., name, content, entity forms, diagram kinds) with the template's
#: suggested colours [S9]. Kinds: T = ΤΔ, P = ΔΓΜ for a deed, D = ΔΓΜ for correction / ΤΔΓΜ.
LAYERS: tuple[LayerSpec, ...] = (
    _l(1, "BOUND_IMPL", "Όρια ιδιοκτησίας υλοποιημένα", _PL, "TPD", 42),
    _l(2, "BOUND_UNIMPL", "Όρια ιδιοκτησίας μη υλοποιημένα", _PL, "TPD", 61),
    _l(3, "DBOUND_RYM", "Ρυμοτομική γραμμή", _PL, "TPD", 80),
    _l(4, "DBOUND_AIG", "Οριογραμμή αιγιαλού και πράξη καθορισμού", _LT, "TPD", 1),
    _l(5, "DBOUND_PRL", "Οριογραμμή παραλίας και πράξη καθορισμού", _LT, "TPD", 2),
    _l(6, "DBOUND_PAIG", "Οριογραμμή παλαιού αιγιαλού και πράξη", _LT, "TPD", 152),
    _l(7, "DBOUND_REM", "Οριογραμμή ρέματος και πράξη επικύρωσης", _LT, "TPD", 141),
    _l(8, "DBOUND_APAL", "Οριογραμμή απαλλοτρίωσης και πράξη κήρυξης", _LT, "TPD", 84),
    _l(9, "DBOUND_PROP", "Όριο ιδιοκτησίας βάσει διοικητικής πράξης", (*_PL, "text"), "TPD", 7),
    _l(10, "ROAD", "Ονοματολογία οδών", ("text",), "TPD", 2),
    _l(11, "OT", "Ονοματολογία Ο.Τ.", ("text",), "TPD", 80),
    _l(12, "PST_KAEK", "Γεωτεμάχια και ΚΑΕΚ κατά το κτηματολογικό διάγραμμα", _PT, "TPD", 16),
    _l(13, "TOPO_PROP", "Όρια ιδιοκτησίας κατά την αποτύπωση", ("polygon",), "TPD", 30),
    _l(14, "TOPO_PROP_NEW", "Νέα όρια ιδιοκτησιών μετά την πράξη", ("polygon",), "TP", 224),
    _l(15, "BLD", "Υφιστάμενα μόνιμα κτίσματα και αρίθμηση", _PT, "TPD", 163),
    _l(16, "VST", "Χώροι αποκλειστικής χρήσης (κάθετη ιδιοκτησία)", _PT, "TP", 233),
    _l(17, "EAS", "Χώροι δουλείας", _PT, "TP", 233),
    _l(18, "MINE", "Όριο μεταλλείου", ("polygon",), "TPD", 157),
    _l(19, "LINE_XM", "Γραμμή χωρικής μεταβολής γεωτεμαχίων", ("polyline",), "P", 1, DASHED, 30),
    _l(20, "LINE_XM_VST", "Γραμμή μεταβολής χώρων αποκλ. χρήσης", ("polyline",), "PD", 1, DASHED, 30),
    _l(21, "VST_FINAL", "Τελικοί χώροι αποκλειστικής χρήσης", ("polygon",), "PD", 4),
    _l(22, "EAS_FINAL", "Τελικοί χώροι δουλείας", ("polygon",), "PD", 4),
    _l(23, "MINE_FINAL", "Τελικό όριο μεταλλείου", ("polygon",), "PD", 4),
    _l(24, "DGM_PROP_FINAL", "Τελικά γεωτεμάχια (ενημέρωση Κτηματολογίου)", ("polygon",), "PD", 4, lineweight=30),
    _l(25, "AREA_D", "Τμήματα που προσαρτώνται στο διορθούμενο γεωτεμάχιο (Δ)", ("polygon",), "D", 4),
    _l(26, "AREA_A", "Τμήματα που αφαιρούνται από το διορθούμενο γεωτεμάχιο (Α)", ("polygon",), "D", 6),
    _l(27, "OBJ", "Σημειακά κτηματολογικά στοιχεία με ΚΑΕΚ", ("point",), "D", 3),
)  # fmt: skip

BY_NAME: dict[str, LayerSpec] = {s.name: s for s in LAYERS}
BY_NO: dict[int, LayerSpec] = {s.no: s for s in LAYERS}

#: Template linetype JIS_02_2.0 ("HIDDEN02"): dash 2.0, gap 1.0 (pattern length 3.0) [S9]
DASHED_PATTERN = (3.0, 2.0, -1.0)
DASHED_DESCRIPTION = "HIDDEN02 __ __ __ __ __ __ __ __ __ __ __"

#: DXF versions accepted: [S1] §4.2 says 2004–2014, §4.4 says 2000–2014 fully supported
ACCEPTED_VERSIONS = {
    "AC1015": "2000",
    "AC1018": "2004",
    "AC1021": "2007",
    "AC1024": "2010",
    "AC1027": "2013/2014",
}
PREFERRED_VERSIONS = {"AC1018", "AC1021", "AC1024", "AC1027"}

#: DXF + PDF together ≤ 10 MB [S1] §4.6; the FAQ recommends < 6 MB
MAX_FILE_BYTES = 10 * 1024 * 1024
RECOMMENDED_FILE_BYTES = 6 * 1024 * 1024

#: Entities that must not appear on Table I layers [S1] §4.5.1, [S5] ΣΤ.5
FORBIDDEN_TYPES = {
    "MTEXT": "MTEXT",
    "INSERT": "block",
    "HATCH": "hatch",
    "MPOLYGON": "hatch",
    "IMAGE": "image",
    "WIPEOUT": "image",
    "OLE2FRAME": "image",
    "UNDERLAY": "image",
    "PDFUNDERLAY": "image",
    "DWFUNDERLAY": "image",
    "DGNUNDERLAY": "image",
}

# ---------------------------------------------------------------------- completeness rules


@dataclass(frozen=True)
class Rule:
    """``when`` (all present) ⇒ at least one of ``need`` present, unless any of ``unless``.
    An empty ``when`` means the rule always applies (a required layer or group)."""

    need: tuple[int, ...]
    when: tuple[int, ...] = ()
    unless: tuple[int, ...] = ()


_FINALS_ONLY = (20, 21, 22, 23, 27)

#: [S1] §4.5.2 α (ΤΔ), β (ΔΓΜ for a deed), γ (ΔΓΜ for correction / ΤΔΓΜ)
COMPLETENESS: dict[str, tuple[Rule, ...]] = {
    "topo": (Rule((1, 2)), Rule((12,)), Rule((13,)), Rule((13,), when=(14,))),
    "deed": (
        Rule((1, 2)),
        Rule((12,)),
        Rule((13, 14)),
        Rule((19, 20, 21, 22, 23, 24)),
        Rule((24,), when=(19,)),
        Rule((19,), when=(24,)),
        Rule((21,), when=(20,)),
        Rule((20,), when=(21,)),
    ),
    "correction": (
        Rule((12,)),
        Rule((13,)),
        Rule((20, 21, 22, 23, 24, 25, 26, 27)),
        # 13 ⇔ 24, but 24 is optional for vertical spaces / easement / mine / objects
        Rule((24,), when=(13,), unless=_FINALS_ONLY),
        Rule((13,), when=(24,)),
        Rule((25, 26), when=(24,)),
        Rule((1, 2), when=(13,)),
        Rule((21,), when=(20,)),
        Rule((20,), when=(21,)),
    ),
}

# --------------------------------------------------------------------------- file names

FILE_PREFIX = {"topo": "topo_", "deed": "dgm_", "correction": "dgm_"}
MAX_NAME_CHARS = 15
_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_VERSION_RE = re.compile(r"_v\d+$", re.IGNORECASE)


def check_file_name(filename: str, kind: DiagramKind) -> list[tuple[str, dict[str, object]]]:
    """File-name rules of [S1] §4.3. Returns (code, params) pairs; codes ending in ``_WARN``
    are recommendations, the others are errors."""
    out: list[tuple[str, dict[str, object]]] = []
    base, dot, ext = filename.rpartition(".")
    if not dot:
        base, ext = filename, ""
    if ext.lower() != "dxf":
        out.append(("DGM_FILE_EXTENSION", {"name": filename}))
    if not _NAME_RE.match(base):
        out.append(("DGM_FILE_CHARS", {"name": filename}))
    if len(base) > MAX_NAME_CHARS:
        out.append(("DGM_FILE_LENGTH", {"name": filename, "length": len(base)}))
    prefix = FILE_PREFIX[kind]
    if not base.lower().startswith(prefix):
        out.append(("DGM_FILE_PREFIX", {"name": filename, "prefix": prefix}))
    if not _VERSION_RE.search(base):
        out.append(("DGM_FILE_VERSION_WARN", {"name": filename}))
    return out


def suggest_file_name(stem: str, kind: DiagramKind, version: int = 1) -> str:
    """A compliant name ``dgm_<stem>_vNN.dxf`` (stem reduced to Latin letters/digits)."""
    prefix = FILE_PREFIX[kind]
    suffix = f"_v{version:02d}"
    clean = re.sub(r"[^A-Za-z0-9]+", "", latinize(stem)) or "diagr"
    room = MAX_NAME_CHARS - len(prefix) - len(suffix)
    return f"{prefix}{clean[:room]}{suffix}.dxf"


# ------------------------------------------------------------------------- KAEK and text

#: 12 digits: prefecture (2), municipality (3), sector (2), block (2), parcel serial (3) [S3]
KAEK_RE = re.compile(r"^\d{12}$")
#: Special areas (roads, …) appear with ids like ΕΚ00001 [S6] §9.5 (format not confirmed)
SPECIAL_KAEK_RE = re.compile(r"^(ΕΚ|EK)\d+$")


def normalize_kaek(text: str) -> str:
    """Strip a «ΚΑΕΚ» prefix, spaces, dots and dashes: «ΚΑΕΚ: 05 068 17 03 004» → 050681703004."""
    t = text.strip()
    t = re.sub(r"^(ΚΑΕΚ|KAEK)\s*[:.]?\s*", "", t, flags=re.IGNORECASE)
    return re.sub(r"[\s.\-/]", "", t)


def kaek_status(kaek: str) -> Literal["valid", "special", "invalid"]:
    if KAEK_RE.match(kaek):
        return "valid"
    if SPECIAL_KAEK_RE.match(kaek):
        return "special"
    return "invalid"


#: Greek (and Cyrillic) capitals that look like Latin letters
_LOOKALIKES = str.maketrans(
    {
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
        "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
        "С": "C", "Т": "T", "Х": "X",
    }
)  # fmt: skip


def latinize(text: str) -> str:
    """Replace Greek/Cyrillic look-alike capitals with Latin ones (AREA_Α → AREA_A)."""
    return text.translate(_LOOKALIKES)


def is_latin_name(name: str) -> bool:
    return all(ord(c) < 128 for c in name)


# ----------------------------------------------------------------------- texts on drawing

#: Verbatim engineer's declaration for a ΤΔΓΜ ([S4] §6.2), with blanks for ΚΗΔ and date
TDGM_DECLARATION = (
    "«Το παρόν (ΤΔΓΜ) υποβλήθηκε ηλεκτρονικά στον ψηφιακό υποδοχέα της βάσης δεδομένων του "
    "«Φορέα», έλαβε μοναδικό Κωδικό Ηλεκτρονικού Διαγράμματος (ΚΗΔ) ........../(ημερομηνία) "
    "και η γεωμετρική μεταβολή που απεικονίζεται σε αυτό, είναι τεχνικά εφαρμόσιμη και δεκτική "
    "εισαγωγής στην κτηματολογική βάση, σύμφωνα με την «Αναφορά Εφαρμογής» που εκδόθηκε από το "
    "σύστημα ηλεκτρονικών ελεγχων της βάσης δεδομένων του Εθνικού Κτηματολογίου για το ίδιο "
    "(ΤΔΓΜ) και λήφθηκε υπόψη για την παρούσα δήλωση»."
)

KIND_TITLES = {
    "topo": "ΤΟΠΟΓΡΑΦΙΚΟ ΔΙΑΓΡΑΜΜΑ",
    "deed": "ΔΙΑΓΡΑΜΜΑ ΓΕΩΜΕΤΡΙΚΩΝ ΜΕΤΑΒΟΛΩΝ ΓΙΑ ΕΓΓΡΑΠΤΕΑ ΠΡΑΞΗ",
    "correction": "ΔΙΑΓΡΑΜΜΑ ΓΕΩΜΕΤΡΙΚΩΝ ΜΕΤΑΒΟΛΩΝ ΓΙΑ ΔΙΟΡΘΩΣΗ ΓΕΩΜΕΤΡΙΚΩΝ ΣΤΟΙΧΕΙΩΝ",
}
NEW_PARCEL = "ΝΕΟ"
#: Free layer for cadastral parcels shown for context only (not changed by a deed)
NEIGHBOURS = "ATS_NEIGHBOURS"
