"""外部 Agent 的复盘报告：追加保存，独立于手工复盘笔记。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from ..core.time_utils import utc_now


class AiReview(Base):
    __tablename__ = "ai_review"
    __table_args__ = (
        UniqueConstraint("agent_name", "submission_id", name="uq_ai_review_submission"),
        Index("ix_ai_review_timeline", "trade_date", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    model: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    content_markdown: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    linked_codes: Mapped[list] = mapped_column(JSON, default=list)
    data_sources: Mapped[list] = mapped_column(JSON, default=list)
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submission_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
