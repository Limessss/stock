"""个股诊断 + K 线 API。"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from model.diagnose import diagnose
from model.strategies import STRATEGIES

from ..schemas.diagnose import DiagnoseResponse, KlineResponse
from ..services.cache_service import get_cache
from ..services.kline_service import get_kline
from ..services.name_service import get_name
from ..services.strategy_service import (
    get_default_strategy_name,
    get_effective_label,
    resolve_strategy_params,
)

router = APIRouter()


def _parse_params(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"params 必须是合法 JSON: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(400, "params 必须是 JSON 对象")
    return data


@router.get("/diagnose/{code}", response_model=DiagnoseResponse)
def diagnose_stock(
    code: str,
    date: str | None = Query(default=None, description="YYYY-MM-DD；省略=最后一日"),
    strategy: str | None = Query(default=None, description="策略名；省略=全局默认策略"),
    params: str | None = Query(default=None, description="策略参数 JSON 对象"),
) -> DiagnoseResponse:
    strategy_name = strategy or get_default_strategy_name()
    if strategy_name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {strategy_name}; 可选: {list(STRATEGIES)}")

    cache = get_cache()
    df = cache.load(code)
    if df is None:
        raise HTTPException(404, f"无该股票缓存: {code}；请先构建缓存或确认代码")

    ts = pd.Timestamp(date) if date else None
    strategy_params = resolve_strategy_params(strategy_name, _parse_params(params))
    try:
        report = diagnose(
            code.upper(),
            df,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            target_date=ts,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except TypeError as e:
        raise HTTPException(400, f"参数错误: {e}") from e

    return DiagnoseResponse(
        code=report.code,
        name=get_name(report.code),
        strategy=strategy_name,
        strategy_label=get_effective_label(strategy_name),
        date=report.date,
        close=report.close,
        final_status=report.final_status,
        score=report.score,
        indicators=report.indicators,
        rules=[asdict(r) for r in report.rules],  # type: ignore[misc]
    )


@router.get("/kline/{code}", response_model=KlineResponse)
def kline(
    code: str,
    last_n: int = Query(default=300, ge=20, le=2000),
    end_date: str | None = Query(default=None, description="窗口右端对齐到该交易日"),
    min_date: str | None = Query(default=None, description="窗口需覆盖的最早交易日（如试盘日）"),
    center_date: str | None = Query(default=None, description="以该交易日为窗口中点"),
    max_date: str | None = Query(default=None, description="窗口需覆盖的最晚交易日（如卖出日）"),
) -> KlineResponse:
    cache = get_cache()
    if cache.load(code) is None:
        raise HTTPException(404, f"无该股票缓存: {code}")
    try:
        payload = get_kline(
            code,
            last_n=last_n,
            end_date=end_date,
            min_date=min_date,
            center_date=center_date,
            max_date=max_date,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    payload["name"] = get_name(code)
    return KlineResponse(**payload)
