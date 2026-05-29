"""回测任务 + 成交记录 ORM 模型。"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class BacktestTask(Base):
    __tablename__ = "backtest_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 策略 & 参数
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_params: Mapped[dict] = mapped_column(JSON, default=dict)

    # 回测参数
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    take_profit: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    max_hold: Mapped[int] = mapped_column(Integer)
    split_tp: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    position_pct: Mapped[float] = mapped_column(Float, default=1.0)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=1)
    t_plus_1: Mapped[bool] = mapped_column(Boolean, default=True)

    # 状态
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.pending.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 汇总指标
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)

    trades: Mapped[list["BacktestTrade"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backtest_task.id", ondelete="CASCADE"), index=True
    )

    code: Mapped[str] = mapped_column(String(16), index=True)
    signal_date: Mapped[str] = mapped_column(String(10), index=True)
    market: Mapped[str] = mapped_column(String(16))
    tier: Mapped[str] = mapped_column(String(4))
    score: Mapped[float] = mapped_column(Float)
    breakout_pct: Mapped[float] = mapped_column(Float)
    is_limit_up: Mapped[bool] = mapped_column(Boolean, default=False)
    vol_ratio: Mapped[float] = mapped_column(Float)
    macd: Mapped[float] = mapped_column(Float)
    dif: Mapped[float] = mapped_column(Float)
    pullback_pct: Mapped[float] = mapped_column(Float)
    ma_spread_pct: Mapped[float] = mapped_column(Float)
    days_since_test: Mapped[int] = mapped_column(Integer)
    close_to_ma30: Mapped[float] = mapped_column(Float)
    close_to_low60: Mapped[float] = mapped_column(Float)
    body_ratio: Mapped[float] = mapped_column(Float)
    day_change_pct: Mapped[float] = mapped_column(Float)
    bull_ma_count: Mapped[int] = mapped_column(Integer)

    buy_price: Mapped[float] = mapped_column(Float)
    buy_date: Mapped[str] = mapped_column(String(10))
    sell_price: Mapped[float] = mapped_column(Float)
    sell_date: Mapped[str] = mapped_column(String(10))
    sell_reason: Mapped[str] = mapped_column(String(64))
    return_pct: Mapped[float] = mapped_column(Float)
    max_up_pct: Mapped[float] = mapped_column(Float)
    max_dn_pct: Mapped[float] = mapped_column(Float)
    hold_days: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    buy_amount: Mapped[float] = mapped_column(Float, default=0.0)
    sell_amount: Mapped[float] = mapped_column(Float, default=0.0)
    profit_amount: Mapped[float] = mapped_column(Float, default=0.0)

    task: Mapped["BacktestTask"] = relationship(back_populates="trades")
