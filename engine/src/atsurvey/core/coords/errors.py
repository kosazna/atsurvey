"""Request-level failures of the coordinate tools, with a stable issue code.

``CoordsError`` is a ``ValueError`` (the API maps it to HTTP 422) that also carries the
``COORD_*`` code and parameters, so the web app can show the Greek message.
"""

from __future__ import annotations

from typing import Any


class CoordsError(ValueError):
    def __init__(self, code: str, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code = code
        self.params = params
