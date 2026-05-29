"""扫描 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from model.strategies import STRATEGIES

from ..schemas.scan import ScanRequest, ScanResponse
from ..services.scan_service import run_scan
from ..services.strategy_service import resolve_strategy_params

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
def scan(req: ScanRequest) -> ScanResponse:
    if req.strategy not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {req.strategy}; 可选: {list(STRATEGIES)}")
    try:
        result = run_scan(
            strategy_name=req.strategy,
            strategy_params=resolve_strategy_params(req.strategy, req.params),
            target_date=req.target_date,
            limit=req.limit,
            sort_by=req.sort_by,
            desc=req.desc,
            max_codes=req.max_codes,
        )
    except TypeError as e:
        raise HTTPException(400, f"参数错误: {e}") from e
    return ScanResponse(**result)
