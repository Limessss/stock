"""回测 schemas。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..core.time_utils import UtcDateTime


class BacktestRequest(BaseModel):
    name: str | None = Field(default=None, description="任务名（可空，便于历史中区分）")
    strategy: str = "breakout_washout"
    params: dict[str, Any] = Field(default_factory=dict)
    start_date: str = Field(description="YYYY-MM-DD")
    end_date: str = Field(description="YYYY-MM-DD")
    take_profit: float = Field(default=0.20, gt=0)
    stop_loss: float = Field(default=0.07, gt=0)
    max_hold: int = Field(default=20, ge=1, le=120)
    split_tp: float | None = Field(default=None, description="分批止盈，如 0.05；None 表示不分批")
    max_codes: int | None = Field(default=None, description="调试用：仅扫描前 N 只股票")
    num_workers: int | None = Field(default=8, ge=1, le=32, description="并行进程数，默认 8")
    engine: str = Field(default="legacy", description="模拟引擎：'legacy'（精确）或 'vectorbt'（实验性，sl/tp 基于 close）")
    initial_capital: float = Field(default=1_000_000.0, gt=0, description="初始资金（元）")
    position_pct: float = Field(default=1.0, gt=0, le=1.0, description="单笔仓位占初始资金比例，1.0=每笔用满")
    max_concurrent: int = Field(default=1, ge=1, le=20, description="最大同时持仓只数，1=串行全仓")
    t_plus_1: bool = Field(default=True, description="A 股 T+1：买入当日不可卖出")


class BacktestSummary(BaseModel):
    total_trades: int
    win_rate: float
    avg_return: float
    median_return: float
    big_win_rate: float
    big_loss_rate: float
    avg_hold_days: float
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    calmar: float = 0.0
    cagr_pct: float = 0.0
    initial_capital: float = 0.0
    total_profit: float = 0.0
    final_capital: float = 0.0
    signal_count: int = 0
    skipped_count: int = 0
    max_concurrent: int = 0


class MonthlyReturn(BaseModel):
    year: int
    month: int
    return_pct: float


class EquityPoint(BaseModel):
    date: str
    nav: float


class BacktestMetrics(BaseModel):
    sharpe: float
    max_drawdown_pct: float
    calmar: float
    cagr_pct: float
    monthly: list[MonthlyReturn]
    equity_curve: list[EquityPoint]
    initial_capital: float = 0.0
    total_profit: float = 0.0
    final_capital: float = 0.0


class BacktestTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str | None
    strategy_name: str
    strategy_params: dict
    start_date: str
    end_date: str
    take_profit: float
    stop_loss: float
    max_hold: int
    split_tp: float | None
    initial_capital: float = 1_000_000.0
    position_pct: float = 1.0
    max_concurrent: int = 1
    t_plus_1: bool = True
    status: str
    progress: int
    total: int
    error: str | None
    created_at: UtcDateTime
    started_at: UtcDateTime | None
    finished_at: UtcDateTime | None
    elapsed_seconds: float | None
    summary: dict | None
    trade_count: int


class BacktestCreateResponse(BaseModel):
    task_id: str
    status: str = "pending"


class BacktestListResponse(BaseModel):
    tasks: list[BacktestTaskOut]


class BacktestTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str = ""
    signal_date: str
    market: str
    tier: str
    score: float
    breakout_pct: float
    is_limit_up: bool
    vol_ratio: float
    macd: float
    dif: float
    pullback_pct: float
    ma_spread_pct: float
    days_since_test: int
    close_to_ma30: float
    close_to_low60: float
    body_ratio: float
    day_change_pct: float
    bull_ma_count: int
    buy_price: float
    buy_date: str
    sell_price: float
    sell_date: str
    sell_reason: str
    return_pct: float
    max_up_pct: float
    max_dn_pct: float
    hold_days: int
    quantity: int = 0
    buy_amount: float = 0.0
    sell_amount: float = 0.0
    profit_amount: float = 0.0


class LedgerRow(BaseModel):
    date: str
    action: str  # buy | sell
    code: str
    name: str = ""
    signal_date: str
    buy_date: str | None = None  # 卖出行携带对应买入日，便于 K 线双标记
    price: float
    quantity: int
    amount: float
    profit_amount: float | None = None
    sell_reason: str | None = None


class LedgerPage(BaseModel):
    rows: list[LedgerRow]
    total: int
    page: int
    page_size: int
    initial_capital: float = 0.0
    total_profit: float = 0.0
    final_capital: float = 0.0


class TradesPage(BaseModel):
    rows: list[BacktestTradeOut]
    total: int
    page: int
    page_size: int
