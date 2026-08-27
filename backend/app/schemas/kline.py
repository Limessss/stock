"""K 线查询 schemas。"""
from __future__ import annotations

from pydantic import BaseModel


class KlineCandle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    change_pct: float | None = None
    amount: float | None = None


class KlineMaPoint(BaseModel):
    time: str
    value: float


class KlineVolumePoint(BaseModel):
    time: str
    value: float
    color: str


class KlineMacdBar(BaseModel):
    time: str
    value: float
    color: str


class KlineMacdLine(BaseModel):
    time: str
    value: float


class KlineResponse(BaseModel):
    code: str
    name: str = ""
    adjustment: str = "none"
    candles: list[KlineCandle]
    volume: list[KlineVolumePoint]
    macd: list[KlineMacdBar] = []
    dif: list[KlineMacdLine] = []
    dea: list[KlineMacdLine] = []
    ma5: list[KlineMaPoint]
    ma10: list[KlineMaPoint]
    ma20: list[KlineMaPoint]
    ma60: list[KlineMaPoint]
