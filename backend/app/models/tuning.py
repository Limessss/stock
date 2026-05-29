"""参数调优任务 ORM。"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class TuningStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class TuningSession(Base):
    __tablename__ = "tuning_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64))
    goal: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(String(32), default="composite")
    backtest_config: Mapped[dict] = mapped_column(JSON, default=dict)
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(16), default=TuningStatus.pending.value)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_trial_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    trials: Mapped[list["TuningTrial"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class TuningTrial(Base):
    __tablename__ = "tuning_trial"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("tuning_session.id"))
    iteration: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    session: Mapped[TuningSession] = relationship(back_populates="trials")
