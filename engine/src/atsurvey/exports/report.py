"""PDF computation report (Typst)."""

from __future__ import annotations

import json
from datetime import datetime
from importlib import resources
from zoneinfo import ZoneInfo

from ..core.messages import localize
from ..core.models import ProjectInput, ProjectResult
from ..core.units import from_rad, rad_to_cc
from . import ExportOptions, selected_points
from .labels import KIND_LABELS, L

UNIT_LABELS = {
    "gon": "grad (gon)",
    "deg": "μοίρες (δεκαδικές)",
    "dms": "μοίρες (° ′ ″)",
    "rad": "rad",
}

REPORT_LABELS = {
    "el": {
        "report_title": "Τεύχος υπολογισμών",
        "date": "Ημερομηνία",
        "crs": "Σύστημα αναφοράς",
        "angle_unit": "Μονάδα γωνιών",
        "reductions": "Αναγωγές",
        "summary": "Σύνοψη",
        "traverse": "Όδευση",
        "type": "Τύπος",
        "length": "Μήκος",
        "limit": "όριο",
        "result": "Αποτέλεσμα",
        "within": "Εντός ορίων",
        "exceeded": "Εκτός ορίων",
        "failed": "Απέτυχε",
        "unchecked": "Χωρίς έλεγχο",
        "correction": "Διόρθωση γωνίας",
        "angles_azimuths": "Γωνίες και αζιμούθια",
        "legs": "Πλευρές",
        "station": "Στάση",
        "back": "Πίσω",
        "fore": "Εμπρός",
        "from": "Από",
        "to": "Προς",
        "coordinates": "Συντεταγμένες σημείων",
        "name": "Όνομα",
        "code": "Κωδικός",
        "kind": "Είδος",
        "issues": "Παρατηρήσεις υπολογισμού",
        "severity": "Επίπεδο",
        "message": "Μήνυμα",
        "page": "Σελίδα",
        "disclaimer": (
            "Οι υπολογισμοί έγιναν αυτόματα με βάση τις μετρήσεις και τα γνωστά σημεία που "
            "καταχωρήθηκαν. Ο μηχανικός που υπογράφει τη μελέτη ελέγχει τα δεδομένα, τις "
            "παραμέτρους αναγωγής και τα όρια ανοχών πριν από τη χρήση τους. Το αναγνωριστικό "
            "υπολογισμού στο υποσέλιδο ταυτοποιεί μοναδικά τα δεδομένα εισόδου."
        ),
        "cards": [
            "Γνωστά σημεία",
            "Στάσεις οδεύσεων",
            "Σημεία λεπτομερειών",
            "Οδεύσεις εντός ορίων",
        ],
    },
    "en": {
        "report_title": "Computation report",
        "date": "Date",
        "crs": "Reference system",
        "angle_unit": "Angle unit",
        "reductions": "Reductions",
        "summary": "Summary",
        "traverse": "Traverse",
        "type": "Type",
        "length": "Length",
        "limit": "limit",
        "result": "Result",
        "within": "Within tolerance",
        "exceeded": "Out of tolerance",
        "failed": "Failed",
        "unchecked": "Unchecked",
        "correction": "Angle correction",
        "angles_azimuths": "Angles and azimuths",
        "legs": "Legs",
        "station": "Station",
        "back": "Back",
        "fore": "Fore",
        "from": "From",
        "to": "To",
        "coordinates": "Point coordinates",
        "name": "Name",
        "code": "Code",
        "kind": "Kind",
        "issues": "Computation notes",
        "severity": "Level",
        "message": "Message",
        "page": "Page",
        "disclaimer": (
            "Computed automatically from the observations and control points entered. The "
            "responsible engineer must verify the data, reduction parameters and tolerances "
            "before use. The computation id in the footer uniquely identifies the input data."
        ),
        "cards": [
            "Control points",
            "Traverse stations",
            "Detail points",
            "Traverses within tolerance",
        ],
    },
}


def _reductions_text(inp: ProjectInput, lang: str) -> str:
    rs = inp.settings.reduction
    el = lang == "el"
    scale = {
        "leg_simpson": "k ανά πλευρά (Simpson)" if el else "k per leg (Simpson)",
        "leg_mean": "k ανά πλευρά (μέσο)" if el else "k per leg (mid-point)",
        "traverse_mean": "ενιαίο k όδευσης" if el else "single k per traverse",
        "none": "χωρίς k" if el else "no scale factor",
        "fixed": f"k = {rs.fixed_scale:.7f}",
    }[rs.scale_mode]
    parts = [scale]
    if rs.elevation_reduction:
        parts.append(
            ("αναγωγή υψομέτρου" if el else "height reduction") + f" (R = {rs.earth_radius:.0f} m)"
        )
    if rs.curvature_refraction:
        parts.append(
            ("καμπυλότητα/διάθλαση" if el else "curvature/refraction")
            + f" (κ = {rs.refraction_coefficient})"
        )
    return " · ".join(parts)


def to_pdf(
    project_name: str, inp: ProjectInput, result: ProjectResult, opts: ExportOptions
) -> bytes:
    import typst

    lang = opts.language
    unit = opts.angle_unit
    d = opts.decimals
    t = REPORT_LABELS[lang]
    kinds = {k: L[lang][f"kind_{k}"] for k in ("open", "link", "closed")}

    def a(v: float | None) -> str:
        if v is None:
            return "–"
        return f"{from_rad(v, unit):.4f}" if unit != "dms" else f"{from_rad(v, unit):.6f}"

    def m(v: float | None, dec: int = 3, sign: bool = True) -> str:
        if v is None:
            return "–"
        if round(v, dec) == 0:
            v = 0.0
        return f"{v:+.{dec}f}" if sign else f"{v:.{dec}f}"

    def c(v: float | None) -> str:
        return "–" if v is None else f"{rad_to_cc(v):+.1f} cc"

    trs = []
    for tr in result.traverses:
        status = (
            "failed"
            if tr.status == "failed"
            else "ok"
            if tr.within_tolerance
            else "bad"
            if tr.within_tolerance is False
            else "unchecked"
        )
        wb = c(tr.angular_misclosure)
        if tr.angular_tolerance is not None:
            wb += f" / {rad_to_cc(tr.angular_tolerance):.0f}"
        w = m(tr.linear_misclosure, 3, False)
        if tr.linear_tolerance is not None:
            w += f" / {tr.linear_tolerance:.3f}"
        trs.append(
            {
                "name": tr.name,
                "kind": kinds[tr.kind] + (" (α)" if tr.end_orientation else ""),
                "n": str(tr.n_angles),
                "length": f"{tr.length:.2f} m",
                "wb": wb,
                "w": w,
                "wxy": f"{m(tr.wx)} / {m(tr.wy)}",
                "rel": f"1:{tr.relative_precision:,.0f}".replace(",", ".")
                if tr.relative_precision
                else "–",
                "wz": m(tr.wz),
                "corr": c(tr.stations[0].angle_correction) if tr.stations else "–",
                "status": status,
                "stations": [
                    [
                        s.station,
                        s.backsight,
                        s.foresight,
                        a(s.angle_measured),
                        f"{rad_to_cc(s.angle_correction):+.1f}",
                        a(s.angle_corrected),
                        a(s.azimuth),
                        f"{s.x:.{d}f}",
                        f"{s.y:.{d}f}",
                        m(s.z, d, False),
                    ]
                    for s in tr.stations
                ],
                "legs": [
                    [
                        lg.frm,
                        lg.to,
                        f"{lg.hd_measured:.3f}",
                        f"{lg.reduction_scale:.6f}",
                        f"{lg.distance_grid:.3f}",
                        a(lg.azimuth),
                        m(lg.dx),
                        m(lg.dy),
                        m(lg.corr_x),
                        m(lg.corr_y),
                        m(lg.dh),
                        m(lg.corr_h),
                    ]
                    for lg in tr.legs
                ],
            }
        )

    s = result.summary
    data = {
        "lang": lang,
        "labels": t,
        "project": project_name,
        "date": datetime.now(ZoneInfo("Europe/Athens")).strftime("%d/%m/%Y %H:%M"),
        "angle_unit_label": UNIT_LABELS.get(unit, unit),
        "reductions": _reductions_text(inp, lang),
        "engine_version": result.engine_version,
        "input_hash_short": result.input_hash[:12],
        "summary_cards": [
            {"label": t["cards"][0], "value": str(s.n_control)},
            {"label": t["cards"][1], "value": str(s.n_traverse_points)},
            {"label": t["cards"][2], "value": str(s.n_detail_points)},
            {"label": t["cards"][3], "value": f"{s.n_traverses_ok}/{s.n_traverses}"},
        ],
        "traverses": trs,
        "points": [
            [
                p.name,
                f"{p.x:.{d}f}",
                f"{p.y:.{d}f}",
                m(p.z, d, False),
                p.code or "",
                KIND_LABELS[lang][p.kind],
            ]
            for p in selected_points(result, opts)
        ],
        "issues": [
            [
                {
                    "error": "Σφάλμα" if lang == "el" else "Error",
                    "warning": "Προσοχή" if lang == "el" else "Warning",
                }[i.severity],
                localize(i, lang),
            ]
            for i in result.issues
            if i.severity in ("error", "warning")
        ],
    }
    template = resources.files("atsurvey.exports").joinpath("templates/report.typ").read_bytes()
    return typst.compile(
        template, format="pdf", sys_inputs={"data": json.dumps(data, ensure_ascii=False)}
    )
