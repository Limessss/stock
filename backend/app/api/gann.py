"""江恩角度线 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
import pandas as pd

from model.analysis.gann import compute_gann_analysis

from ..schemas.gann import GannResponse
from ..services.cache_service import get_cache
from ..services.name_service import get_name

router = APIRouter()


@router.get("/gann/{code}", response_model=GannResponse)
def gann_analysis(
    code: str,
    last_n: int = Query(default=250, ge=60, le=2000, description="K 线窗口根数"),
    swing_half: int = Query(default=10, ge=3, le=30, description="摆动点半径（左右各 N 根）"),
    min_move_pct: float = Query(default=0.08, ge=0.02, le=0.5, description="主波段最小幅度"),
    up_anchor_date: str | None = Query(default=None, description="自定义上升起点 YYYY-MM-DD"),
    down_anchor_date: str | None = Query(default=None, description="自定义下降起点 YYYY-MM-DD"),
) -> GannResponse:
    cache = get_cache()
    df = cache.load(code)
    if df is None:
        raise HTTPException(404, f"无该股票缓存: {code}；请先构建缓存或确认代码")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", ascending=True).reset_index(drop=True)
    df = df.tail(last_n)

    try:
        payload = compute_gann_analysis(
            df,
            swing_half=swing_half,
            min_move_pct=min_move_pct,
            up_anchor_date=up_anchor_date,
            down_anchor_date=down_anchor_date,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return GannResponse(
        code=code.upper(),
        name=get_name(code),
        window_bars=payload["window_bars"],
        price_scale=payload["price_scale"],
        note=payload["note"],
        anchors=payload["anchors"],
        calibration=payload["calibration"],
        lines=payload["lines"],
    )
