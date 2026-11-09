"""Greek message templates for issue codes (used by exports; the web app has its own copy)."""

from __future__ import annotations

from .models import Issue

EL: dict[str, str] = {
    "ROUND_SPREAD": "Οι διευθύνσεις προς {target} από τη στάση {station} διαφέρουν κατά {spread_cc} cc μεταξύ περιόδων/θέσεων",
    "TRAVERSE_ROUTE_TOO_SHORT": "Η όδευση χρειάζεται τουλάχιστον 3 σημεία (προσανατολισμός, στάση, επόμενο σημείο)",
    "TRAVERSE_MISSING_ANGLE": "Λείπει η γωνία {angle}: καμία στάση στο {station} δεν σκοπεύει και τα δύο σημεία",
    "TRAVERSE_MISSING_DISTANCE": "Λείπει μετρημένη απόσταση στην πλευρά {leg}",
    "TRAVERSE_ANGULAR_TOLERANCE": "Γωνιακό σφάλμα κλεισίματος {misclosure_cc} cc πάνω από το όριο {tolerance_cc} cc",
    "TRAVERSE_LINEAR_TOLERANCE": "Γραμμικό σφάλμα κλεισίματος {misclosure_m} m πάνω από το όριο {tolerance_m} m",
    "TRAVERSE_RELATIVE_PRECISION": "Σχετική ακρίβεια 1:{relative} χειρότερη από 1:{minimum}",
    "TRAVERSE_HEIGHT_TOLERANCE": "Υψομετρικό σφάλμα κλεισίματος {misclosure_m} m πάνω από το όριο {tolerance_m} m",
    "TRAVERSE_NO_HEIGHTS": "Δεν υπολογίστηκαν υψόμετρα (λείπει υψόμετρο αφετηρίας ή κατακόρυφες γωνίες)",
    "TRAVERSE_OPEN": "Ανοιχτή όδευση: οι συντεταγμένες δεν ελέγχονται",
    "TRAVERSE_KNOWN_POINT_MID": "Η όδευση περνά από το γνωστό σημείο {point} (διαφορά {diff_mm} mm) — κρατήθηκαν οι γνωστές συντεταγμένες",
    "TRAVERSE_UNRESOLVED": "Η όδευση δεν μπορεί να ξεκινήσει: λείπουν γνωστά σημεία ({missing})",
    "POINT_CONFLICT": "Το σημείο {point} υπολογίστηκε ξανά με διαφορά {diff_mm} mm — κρατήθηκε ο πρώτος προσδιορισμός",
    "LEG_DISTANCE_FB": "Πλευρά {leg}: μετάβαση/επιστροφή απόστασης διαφέρουν κατά {diff_mm} mm",
    "LEG_HEIGHT_FB": "Πλευρά {leg}: μετάβαση/επιστροφή υψομετρικής διαφοράς διαφέρουν κατά {diff_mm} mm",
    "SETUP_STATION_UNKNOWN": "Η στάση {station} δεν έχει συντεταγμένες· οι μετρήσεις της δεν υπολογίστηκαν",
    "SETUP_NO_ORIENTATION": "Η στάση {station} δεν σκοπεύει γνωστό σημείο· {count} μετρήσεις δεν προσανατολίστηκαν",
    "ORIENTATION_SPREAD": "Στάση {station}: οι προσανατολισμοί διαφέρουν κατά {spread_cc} cc",
    "DETAIL_DUPLICATE": "Το σημείο {target} μετρήθηκε {count} φορές με απόκλιση έως {spread_mm} mm",
    "DETAIL_NO_DISTANCE": "Το σημείο {target} από τη στάση {station} δεν έχει απόσταση",
    "CHECK_SHOT_RESIDUAL": "Έλεγχος {station}→{target}: απόκλιση {residual_mm} mm από τις γνωστές συντεταγμένες",
    "CONTROL_DUPLICATE": "Το γνωστό σημείο {point} δηλώνεται περισσότερες φορές· χρησιμοποιήθηκε το πρώτο",
    "STATION_BY_RADIATION": "Η στάση {station} προσδιορίστηκε ακτινωτά (χωρίς έλεγχο)",
    "ADJUSTMENT_DATUM": "Ανεπαρκές datum για τη συνόρθωση ({dimension}): συνδέονται {fixed} σταθερά σημεία — διατηρήθηκε η λύση των οδεύσεων",
    "ADJUSTMENT_TOO_LARGE": "Το δίκτυο είναι πολύ μεγάλο για συνόρθωση ({n} άγνωστοι, όριο {limit})",
    "ADJUSTMENT_NOT_CONVERGED": "Η συνόρθωση δεν συνέκλινε σε {iterations} επαναλήψεις",
    "ADJUSTMENT_GLOBAL_TEST": "Ο ολικός έλεγχος απέτυχε: σ0 = {sigma0} με {dof} βαθμούς ελευθερίας — ελέγξτε τις εκ των προτέρων ακρίβειες ή αναζητήστε χονδροειδή σφάλματα",
    "ADJUSTMENT_BLUNDER": "Πιθανό χονδροειδές σφάλμα: {kind} {station}→{target} (w = {w}, κρίσιμη τιμή {critical})",
    "ADJUSTMENT_NO_REDUNDANCY": "Η συνόρθωση δεν έχει πλεονάζουσες μετρήσεις (βαθμοί ελευθερίας {dof}) — δεν είναι δυνατός στατιστικός έλεγχος",
    "ADJUSTMENT_EXCLUDED_POINT": "Το σημείο {point} εξαιρέθηκε από τη συνόρθωση (χωρίς προσεγγιστικές συντεταγμένες ή ανεπαρκείς μετρήσεις)",
}


def localize(issue: Issue, lang: str) -> str:
    if lang != "el" or issue.code not in EL:
        return issue.message
    params = {
        k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in issue.params.items()
    }
    try:
        prefix = (
            f"[{issue.traverse}] "
            if issue.traverse and issue.code.startswith(("TRAVERSE", "LEG"))
            else ""
        )
        return prefix + EL[issue.code].format(**params)
    except (KeyError, IndexError):
        return issue.message
