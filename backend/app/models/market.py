"""指数行情与市场汇总 ORM。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from ..core.time_utils import utc_now


class MarketIndexDaily(Base):
    """指数日 K 线（含 OHLCV，供行情卡片与 K 线图复用）。"""

    __tablename__ = "market_index_daily"
    __table_args__ = (UniqueConstraint("trade_date", "index_code", name="uq_market_index_daily"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    index_code: Mapped[str] = mapped_column(String(16), index=True)
    index_name: Mapped[str] = mapped_column(String(32), default="")
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_amt: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_source: Mapped[str] = mapped_column(String(32), default="a-stock-data-http")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MarketDailySummary(Base):
    """全市场日汇总（涨跌家数、总成交额）。"""

    __tablename__ = "market_daily_summary"

    trade_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    up_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    down_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_source: Mapped[str] = mapped_column(String(32), default="a-stock-data-http")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
