"""Fail if a tracked file looks like it contains a credential.

    uv run python scripts/check_secrets.py

Deliberately simple and dependency-free; complements GitHub secret scanning. Patterns cover the
credentials this project actually uses (Supabase service-role / JWT secrets, Paddle keys, SSH and
TLS private keys, cloud keys). Allow a line by appending ``secret-scan: allow``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "JWT (possible Supabase service-role key)": re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"
    ),
    "Paddle API key / webhook secret": re.compile(r"\b(?:pdl_(?:live|sdbx)_apikey_|pdl_ntfset_)[A-Za-z0-9_]{16,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Stripe live key": re.compile(r"\bsk_live_[0-9A-Za-z]{16,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "assigned secret": re.compile(
        r"(?i)\b(?:SUPABASE_SERVICE_ROLE_KEY|SUPABASE_JWT_SECRET|PADDLE_WEBHOOK_SECRET|"
        r"PADDLE_API_KEY)\s*[=:]\s*['\"]?[A-Za-z0-9_\-.]{16,}"
    ),
}
SKIP_SUFFIXES = {".png", ".jpg", ".ttf", ".woff", ".woff2", ".pdf", ".lock", ".ico"}


def main() -> int:
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    hits = []
    for rel in files:
        path = ROOT / rel
        if path.suffix in SKIP_SUFFIXES or rel.endswith("pnpm-lock.yaml") or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "secret-scan: allow" in line:
                continue
            for label, rx in PATTERNS.items():
                if rx.search(line):
                    hits.append(f"{rel}:{lineno}: {label}")
    for h in hits:
        print(h, file=sys.stderr)
    print(f"secret scan: {len(files)} files, {len(hits)} findings")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
