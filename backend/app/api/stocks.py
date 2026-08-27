"""股票搜索 API（键盘精灵）。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from model.data.stock_search import search_stocks

from ..schemas.stocks import StockSearchItem
from ..services.name_service import ensure_names_path

router = APIRouter()


@router.get("/stocks/search", response_model=list[StockSearchItem])
def stock_search(
    q: str = Query(default="", max_length=32, description="代码 / 名称 / 拼音首字母"),
    limit: int = Query(default=15, ge=1, le=50),
) -> list[StockSearchItem]:
    ensure_names_path()
    rows = search_stocks(q, limit=limit)
    return [StockSearchItem(code=r["code"], name=r["name"], market=r["market"]) for r in rows]
