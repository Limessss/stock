"""股票搜索 schemas。"""
from __future__ import annotations

from pydantic import BaseModel


class StockSearchItem(BaseModel):
    code: str
    name: str
    market: str
