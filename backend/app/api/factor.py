"""因子分析 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.factor import FactorAnalysisResponse
from ..services import factor_service

router = APIRouter()


@router.get("/factor/analysis", response_model=FactorAnalysisResponse)
def factor_analysis(
    task_id: str = Query(..., description="回测任务 ID"),
    target: str = Query(default="return_pct"),
    quantile_n: int = Query(default=5, ge=2, le=10),
) -> FactorAnalysisResponse:
    res = factor_service.analyze(task_id, target=target, quantile_n=quantile_n)
    if res is None:
        raise HTTPException(404, "task not found")
    return FactorAnalysisResponse(**res)
