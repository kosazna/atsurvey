"""Διάγραμμα Γεωμετρικών Μεταβολών (ΔΓΜ) for the Hellenic Cadastre: build, write, validate.

* ``build_dgm`` (build.py): subdivision / merge (deed) and correction (ΤΔΓΜ) geometry, tables
  and checks.
* ``read_kd`` (kd_reader.py): parcels and KAEK from a Κτηματογραφικό Διάγραμμα DXF.
* ``write_dgm_dxf`` (writer.py): DXF 2004 with the 27 layers of Table I.
* ``validate_dxf`` (validate.py): pre-submission checks of any DXF.

The Cadastre's own system is authoritative; this is a pre-check. See docs/dgm.md.
"""

from .build import build_dgm
from .models import DgmRequest, DgmResult, KdReadResult, ValidationReport

__all__ = ["DgmRequest", "DgmResult", "KdReadResult", "ValidationReport", "build_dgm"]
