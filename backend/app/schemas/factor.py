"""因子分析 schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FactorICRow(BaseModel):
    field: str
    label: str
    ic_return: float | None = None
    ic_max_up: float | None = None


class QuantileRow(BaseModel):
    quantile: str
    count: int
    mean: float
    median: float
    win_rate: float
    big_win_rate: float


class FactorQuantile(BaseModel):
    field: str
    label: str
    quantiles: list[QuantileRow]


class FactorAnalysisResponse(BaseModel):
    task_id: str
    total_trades: int
    ic: list[FactorICRow]
    quantiles: list[FactorQuantile]


class FactorAnalysisRequest(BaseModel):
    task_id: str
    target: str = Field(default="return_pct", description="目标变量：return_pct 或 max_up_pct")
    quantile_n: int = Field(default=5, ge=2, le=10)
