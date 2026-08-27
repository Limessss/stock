"""情绪周期 ORM。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from ..core.time_utils import utc_now


class SentimentDaily(Base):
    __tablename__ = "sentiment_daily"

    trade_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    sh_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    up_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    down_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_up_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_down_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    broken_board_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_high_100_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scanned_stock_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_high_stocks: Mapped[list] = mapped_column(JSON, default=list)
    limit_down_stocks: Mapped[list] = mapped_column(JSON, default=list)
    local_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    external_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    external_status: Mapped[str] = mapped_column(String(20), default="not_configured")
    sync_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ExternalApiSnapshot(Base):
    __tablename__ = "external_api_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "source", "endpoint", "trade_date", "params_hash", name="uq_external_snapshot"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    endpoint: Mapped[str] = mapped_column(String(64), index=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    params_hash: Mapped[str] = mapped_column(String(64))
    request_params: Mapped[dict] = mapped_column(JSON, default=dict)
    payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    parser_version: Mapped[int] = mapped_column(Integer, default=1)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SentimentTheme(Base):
    __tablename__ = "sentiment_theme"
    __table_args__ = (
        UniqueConstraint("trade_date", "category", "name", name="uq_sentiment_theme"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(100))
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(24), default="")
    source: Mapped[str] = mapped_column(String(24), default="manual")
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SentimentLadderItem(Base):
    __tablename__ = "sentiment_ladder_item"
    __table_args__ = (
        UniqueConstraint("trade_date", "code", name="uq_sentiment_ladder_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    board_count: Mapped[int] = mapped_column(Integer, default=1)
    board_type: Mapped[str] = mapped_column(String(24), default="")
    limit_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    themes: Mapped[list] = mapped_column(JSON, default=list)
    is_major_first_board: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(24), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SentimentFeedback(Base):
    __tablename__ = "sentiment_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    feedback_type: Mapped[str] = mapped_column(String(16), default="positive")
    content: Mapped[str] = mapped_column(Text, default="")
    linked_codes: Mapped[list] = mapped_column(JSON, default=list)
    linked_themes: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LeaderPanoramaConfig(Base):
    """龙头周期全景图的有序证券列表（单机单用户配置）。"""

    __tablename__ = "leader_panorama_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    instruments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
