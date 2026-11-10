"""/v1/parcels/* endpoints (stateless). Owned by the parcels feature; see docs/science-roadmap.md."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["parcels"])
