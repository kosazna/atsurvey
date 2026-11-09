"""COGO tools and geometric levelling: /v1/cogo/*, /v1/leveling (stateless, no plan limits)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["cogo"])
