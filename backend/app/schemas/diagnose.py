"""个股诊断 schemas。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DiagnoseRule(BaseModel):
    name: str
    status: str  # pass / fail / warn / skip
    value: Any = None
    threshold: Any = None
    note: str = ""


class DiagnoseResponse(BaseModel):
    code: str
    name: str = ""
    strategy: str = "breakout_washout"
    strategy_label: str = ""
    date: str
    close: float
    final_status: str
    score: float | None = None
    indicators: dict[str, float | None]
    rules: list[DiagnoseRule]


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


class KlineResponse(BaseModel):
    code: str
    name: str = ""
    candles: list[KlineCandle]
    volume: list[KlineVolumePoint]
    ma5: list[KlineMaPoint]
    ma10: list[KlineMaPoint]
    ma20: list[KlineMaPoint]
    ma60: list[KlineMaPoint]
