"""/v1/instruments/* endpoints (stateless). Owned by the instruments feature; see docs/science-roadmap.md."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["instruments"])
