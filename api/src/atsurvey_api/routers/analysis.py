"""/v1/analysis/* endpoints (stateless): network pre-analysis. See docs/analysis.md."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from atsurvey.core.preanalysis import preanalyse
from atsurvey.core.preanalysis_models import PreanalysisRequest, PreanalysisResult

from ..auth import Caller, require_compute

router = APIRouter(prefix="/v1", tags=["analysis"])
ComputeCaller = Annotated[Caller, Depends(require_compute)]


@router.post("/analysis/preanalysis", response_model=PreanalysisResult)
def preanalysis(req: PreanalysisRequest, caller: ComputeCaller) -> PreanalysisResult:
    """Precision (σ, error ellipses) and reliability (r, MDB) of a planned network.
    Inputs are bounded by the model (≤ 500 points, ≤ 5000 observations)."""
    try:
        return preanalyse(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
