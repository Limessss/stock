"""参数调优 API schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TuningBacktestConfig(BaseModel):
    start_date: str
    end_date: str
    val_start_date: str | None = None
    val_end_date: str | None = None
    take_profit: float = Field(default=0.20, gt=0)
    stop_loss: float = Field(default=0.07, gt=0)
    max_hold: int = Field(default=20, ge=1, le=120)
    split_tp: float | None = Field(default=None, description="分批止盈；None 表示不分批")
    max_codes: int | None = Field(default=None, description="调试用：仅扫描前 N 只股票；None=全市场")
    num_workers: int | None = Field(default=8, ge=1, le=32)
    engine: str = Field(default="legacy", description="legacy 或 vectorbt")
    initial_capital: float = Field(default=1_000_000.0, gt=0)
    position_pct: float = Field(default=1.0, gt=0, le=1.0)
    max_concurrent: int = Field(default=1, ge=1, le=20)
    t_plus_1: bool = Field(default=True)


class TuningAdviseRequest(BaseModel):
    strategy: str
    params: dict[str, Any] = Field(default_factory=dict)
    goal: str = ""
    task_id: str | None = None
    summary: dict[str, Any] | None = None
    backtest_config: TuningBacktestConfig | None = None


class ParamChange(BaseModel):
    key: str
    from_value: Any = Field(alias="from")
    to: Any
    reason: str = ""

    model_config = {"populate_by_name": True}


class TuningAdviseResponse(BaseModel):
    analysis: str
    suggested_params: dict[str, Any]
    suggested_trade_params: dict[str, Any] = Field(default_factory=dict)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    trade_changes: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TuningQuickBacktestRequest(BaseModel):
    strategy: str
    params: dict[str, Any] = Field(default_factory=dict)
    backtest_config: TuningBacktestConfig
    objective: str = "composite"


class TuningQuickBacktestResponse(BaseModel):
    summary: dict[str, Any]
    score: float
    elapsed_seconds: float


class TuningVerifyRequest(BaseModel):
    strategy: str
    suggested_params: dict[str, Any] = Field(default_factory=dict)
    trade_params: dict[str, Any] = Field(default_factory=dict)
    verify_summary: dict[str, Any]
    goal: str = ""
    baseline_summary: dict[str, Any] | None = None
    prior_analysis: str = ""


class TuningVerifyResponse(BaseModel):
    verdict: str
    meets_goal: bool
    analysis: str
    comparison: str = ""
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggested_params: dict[str, Any] | None = None
    suggested_trade_params: dict[str, Any] | None = None


class TuningSessionCreate(BaseModel):
    strategy: str
    goal: str = ""
    objective: str = "composite"
    params: dict[str, Any] = Field(default_factory=dict)
    backtest_config: TuningBacktestConfig
    max_iterations: int = Field(default=5, ge=1, le=500)


class TuningTrialOut(BaseModel):
    id: str
    iteration: int
    params: dict[str, Any]
    summary: dict[str, Any] | None
    score: float | None
    llm_analysis: str | None
    elapsed_seconds: float | None


class TuningSessionOut(BaseModel):
    id: str
    strategy_name: str
    goal: str
    objective: str
    backtest_config: dict[str, Any]
    max_iterations: int
    status: str
    error: str | None
    best_trial_id: str | None
    created_at: datetime
    finished_at: datetime | None
    trials: list[TuningTrialOut] = Field(default_factory=list)


class TuningSessionCreateResponse(BaseModel):
    session_id: str
    status: str
