"""Verify that web/public/_headers allows exactly the inline scripts in web/index.html.

    uv run python scripts/check_csp.py   # exit 1 if an inline script's hash is missing
"""

from __future__ import annotations

import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    headers = (ROOT / "web" / "public" / "_headers").read_text(encoding="utf-8")
    csp = next((ln for ln in headers.splitlines() if "Content-Security-Policy:" in ln), "")
    if not csp:
        print("no Content-Security-Policy in web/public/_headers", file=sys.stderr)
        return 1
    missing = []
    for body in re.findall(r"<script>(.*?)</script>", html, re.S):
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        if f"'sha256-{digest}'" not in csp:
            missing.append(digest)
    for d in missing:
        print(f"inline script hash missing from CSP: 'sha256-{d}'", file=sys.stderr)
    if "unsafe-eval" in csp or "script-src 'self' 'unsafe-inline'" in csp:
        print("CSP must not allow unsafe-eval or inline scripts", file=sys.stderr)
        return 1
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
