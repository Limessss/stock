"""共享 K 线查询 API。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..schemas.kline import KlineResponse
from ..services.kline_service import get_kline, get_kline_name
from ..services.name_service import get_name

router = APIRouter()


@router.get("/kline/{code}", response_model=KlineResponse)
def kline(
    code: str,
    last_n: int = Query(default=300, ge=20, le=2000),
    adjust: Literal["qfq", "none"] = Query(default="qfq", description="前复权或不复权"),
    end_date: str | None = Query(default=None, description="窗口右端对齐到该交易日"),
    min_date: str | None = Query(default=None, description="窗口需覆盖的最早交易日"),
    center_date: str | None = Query(default=None, description="以该交易日为窗口中点"),
    max_date: str | None = Query(default=None, description="窗口需覆盖的最晚交易日"),
) -> KlineResponse:
    try:
        payload = get_kline(
            code,
            last_n=last_n,
            adjust=adjust,
            end_date=end_date,
            min_date=min_date,
            center_date=center_date,
            max_date=max_date,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not payload["candles"]:
        raise HTTPException(404, f"无该证券缓存: {code}")
    payload["name"] = get_kline_name(code) or get_name(code)
    return KlineResponse(**payload)
