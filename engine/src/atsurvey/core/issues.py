"""Structured diagnostics.

Every issue has a stable ``code`` and machine-readable ``params`` so the UI can show
a translated (Greek) message; ``message`` is an English fallback.
"""

from __future__ import annotations

from typing import Any

from .models import Issue, Severity


class IssueSink:
    def __init__(self) -> None:
        self.items: list[Issue] = []

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        traverse: str | None = None,
        setup: str | None = None,
        **params: Any,
    ) -> None:
        self.items.append(
            Issue(
                severity=severity,
                code=code,
                message=message,
                params=params,
                traverse=traverse,
                setup=setup,
            )
        )

    def error(self, code: str, message: str, **kw: Any) -> None:
        self.add("error", code, message, **kw)

    def warning(self, code: str, message: str, **kw: Any) -> None:
        self.add("warning", code, message, **kw)

    def info(self, code: str, message: str, **kw: Any) -> None:
        self.add("info", code, message, **kw)
