"""/v1/coords/* endpoints (stateless). Owned by the coords feature; see docs/science-roadmap.md."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["coords"])
