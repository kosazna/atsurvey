"""/v1/analysis/* endpoints (stateless). Owned by the analysis feature; see docs/science-roadmap.md."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["analysis"])
