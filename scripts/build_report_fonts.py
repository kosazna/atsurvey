"""Build the TTF fonts embedded in PDF reports from the official IBM Plex Sans package.

    npm pack @ibm/plex-sans@1.1.0 && tar xzf ibm-plex-sans-1.1.0.tgz
    uv run python scripts/build_report_fonts.py package/fonts/complete/woff

Typst needs TTF/OTF and groups faces by the legacy family name (name ID 1), while Plex
names its Medium/SemiBold faces "IBM Plex Sans Medm"/"SmBld". We convert WOFF → TTF and
normalise the family name so weights resolve through OS/2 usWeightClass.
Fonts are licensed under the SIL Open Font License 1.1 (see fonts/OFL.txt).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parents[1] / "engine" / "src" / "atsurvey" / "exports" / "fonts"
FACES = {"Regular": "Regular", "Italic": "Italic", "Medium": "Regular", "SemiBold": "Regular"}


def main(src_dir: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for face, subfamily in FACES.items():
        font = TTFont(Path(src_dir) / f"IBMPlexSans-{face}.woff")
        font.flavor = None
        name = font["name"]
        for rec in list(name.names):
            if rec.nameID == 1:
                rec.string = "IBM Plex Sans"
            elif rec.nameID == 2:
                rec.string = subfamily
        name.removeNames(nameID=16)
        name.removeNames(nameID=17)
        font.save(OUT / f"IBMPlexSans-{face}.ttf")
        print("wrote", f"IBMPlexSans-{face}.ttf", font["OS/2"].usWeightClass)


if __name__ == "__main__":
    main(sys.argv[1])
