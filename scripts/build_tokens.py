"""Generate theme files from design/tokens.json.

    uv run python scripts/build_tokens.py          # write files
    uv run python scripts/build_tokens.py --check  # CI: fail if generated files are stale

Outputs:
  web/src/styles/tokens.css                       CSS custom properties (light, dark, system)
  engine/src/atsurvey/exports/theme.json          light theme for PDF / Excel reports
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "design" / "tokens.json"
CSS_OUT = ROOT / "web" / "src" / "styles" / "tokens.css"
THEME_OUT = ROOT / "engine" / "src" / "atsurvey" / "exports" / "theme.json"
HEADER = "Generated from design/tokens.json by scripts/build_tokens.py — do not edit."


def css(tokens: dict) -> str:
    def block(selector: str, items: list[tuple[str, str]], indent: str = "") -> str:
        body = "\n".join(f"{indent}  --{k}: {v};" for k, v in items)
        return f"{indent}{selector} {{\n{body}\n{indent}}}"

    static: list[tuple[str, str]] = [
        ("font-sans", tokens["font"]["sans"]),
        ("font-mono", tokens["font"]["mono"]),
    ]
    for group, prefix in (
        ("text", "text"),
        ("leading", "leading"),
        ("weight", "weight"),
        ("radius", "radius"),
        ("space", "space"),
        ("duration", "duration"),
        ("ease", "ease"),
    ):
        static += [(f"{prefix}-{k}", v) for k, v in tokens[group].items()]
    static += list(tokens["layout"].items())

    def themed(mode: str) -> list[tuple[str, str]]:
        items = [(f"color-{k}", v) for k, v in tokens["color"][mode].items()]
        items += [(f"shadow-{k}", v) for k, v in tokens["shadow"][mode].items()]
        return items

    light = static + themed("light")
    dark = themed("dark")
    parts = [
        f"/* {HEADER} */",
        "",
        block(":root", light),
        "",
        block(':root[data-theme="dark"]', dark),
        "",
        "@media (prefers-color-scheme: dark) {",
        block(':root:not([data-theme="light"])', dark, indent="  "),
        "}",
        "",
        ':root { color-scheme: light; }',
        ':root[data-theme="dark"] { color-scheme: dark; }',
        "",
    ]
    return "\n".join(parts)


def theme(tokens: dict) -> str:
    c = tokens["color"]["light"]
    out = {
        "_comment": HEADER,
        "font": "IBM Plex Sans",
        "font_mono": "IBM Plex Mono",
        "color": {k: v for k, v in c.items() if v.startswith("#")},
        "radius_pt": 3,
    }
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    tokens = json.loads(SRC.read_text(encoding="utf-8"))
    outputs = {CSS_OUT: css(tokens), THEME_OUT: theme(tokens)}
    if "--check" in sys.argv:
        stale = [p for p, text in outputs.items() if not p.exists() or p.read_text() != text]
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)} — run scripts/build_tokens.py", file=sys.stderr)
        return 1 if stale else 0
    for p, text in outputs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
