"""/v1/surfaces/* endpoints (stateless). Owned by the surfaces feature; see docs/science-roadmap.md."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["surfaces"])
