"""Neutralise spreadsheet formula injection (CWE-1236) in user-controlled text.

Point names, codes, sources and messages come from uploaded files and user input. When a
CSV is opened in Excel/LibreOffice, a cell starting with ``=``, ``+``, ``-``, ``@``, tab or
carriage return (or their full-width forms) can be evaluated as a formula (DDE, HYPERLINK
exfiltration). Such text is prefixed with an apostrophe, the OWASP-recommended
neutralisation. Numbers are never passed through here and stay numeric.
"""

from __future__ import annotations

FORMULA_TRIGGERS = frozenset("=+-@\t\r\n＝＋－＠")


def safe_text(value: str | None) -> str:
    if not value:
        return ""
    if value[0] in FORMULA_TRIGGERS:
        return "'" + value
    return value
