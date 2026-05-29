"""扫描相关入参 / 出参。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    strategy: str = Field(default="breakout_washout", description="策略 name，对应 STRATEGIES 注册表")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数字典")
    target_date: str | None = Field(default=None, description="YYYY-MM-DD；None=每只股票最后一日")
    limit: int | None = Field(default=200, ge=1, le=5000)
    sort_by: str = Field(default="score")
    desc: bool = True
    max_codes: int | None = Field(default=None, description="仅扫描前 N 只股票（调试用）")


class ScanRow(BaseModel):
    code: str
    name: str = ""
    market: str
    tier: str
    date: str
    close: float
    score: float
    breakout_pct: float
    is_limit_up: bool
    washout_high: float
    test_date: str | None = None
    days_since_test: int = 0
    pullback_pct: float
    vol_ratio: float
    ma_spread_pct: float
    macd: float
    dif: float
    close_to_ma30: float
    day_change_pct: float
    bull_ma_count: int


class ScanResponse(BaseModel):
    rows: list[ScanRow]
    total: int
    scanned: int = 0
    took_ms: int
    strategy: str | None = None
    target_date: str | None = None
    warning: str | None = None
