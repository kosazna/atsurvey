"""SHA-512 of the DXF and the unsigned "hash PDF" for the Cadastre's submission package.

The Cadastre asks for the SHA-512 of the final DXF inside a PDF "without blank characters,
headers or footers", signed by the engineer with a qualified, timestamped signature, zipped
flat together with the DXF ([S11]; [S5] ΣΤ.4). ATSurvey produces the unsigned PDF only:
**we never sign**; the engineer signs it with their own qualified certificate.
"""

from __future__ import annotations

import hashlib
import re
from importlib import resources

_HEX512 = re.compile(r"^[0-9a-f]{128}$")

#: One line, the hash only; the page shrinks to the text (no header, footer or other text).
_TEMPLATE = b"""
#set page(width: auto, height: auto, margin: 8pt)
#set text(font: "IBM Plex Sans", size: 7pt)
#sys.inputs.hash
"""


def sha512_hex(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def hash_pdf(sha512: str) -> bytes:
    """Single-page PDF holding only the lowercase hexadecimal SHA-512 (128 characters)."""
    h = sha512.strip().lower()
    if not _HEX512.match(h):
        raise ValueError("Not a SHA-512 hex digest (128 hexadecimal characters)")
    import typst

    pkg = resources.files("atsurvey.exports")
    with resources.as_file(pkg.joinpath("fonts")) as fonts:
        return typst.compile(
            _TEMPLATE,
            format="pdf",
            font_paths=[str(fonts)],  # pyright: ignore[reportArgumentType]
            ignore_system_fonts=True,
            sys_inputs={"hash": h},
        )
