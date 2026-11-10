"""/v1/setout/* endpoints (stateless). Owned by the setout feature; see docs/science-roadmap.md."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["setout"])
