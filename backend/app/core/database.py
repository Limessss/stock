"""SQLAlchemy 2 同步引擎 + Session 工厂。

单机单用户场景，sync 引擎已足够（FastAPI 的异步路由里会自动放到线程池执行）。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


engine = create_engine(
    settings.db_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},  # 允许在不同线程中共享连接
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Iterator[Session]:
    """供后台线程使用的 with-style session。"""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Iterator[Session]:
    """FastAPI 依赖注入用。"""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def init_db() -> None:
    """启动时创建所有未存在的表，并补齐新增列。"""
    # 触发 model 类被导入以注册到 metadata
    from ..models import backtest, tuning  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """SQLite 增量补列（无 Alembic 时的轻量迁移）。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        if "backtest_task" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("backtest_task")}
            if "initial_capital" not in existing:
                conn.execute(text(
                    "ALTER TABLE backtest_task ADD COLUMN initial_capital FLOAT DEFAULT 1000000.0"
                ))
            if "position_pct" not in existing:
                conn.execute(text(
                    "ALTER TABLE backtest_task ADD COLUMN position_pct FLOAT DEFAULT 1.0"
                ))
            if "max_concurrent" not in existing:
                conn.execute(text(
                    "ALTER TABLE backtest_task ADD COLUMN max_concurrent INTEGER DEFAULT 1"
                ))
            if "t_plus_1" not in existing:
                conn.execute(text(
                    "ALTER TABLE backtest_task ADD COLUMN t_plus_1 BOOLEAN DEFAULT 1"
                ))

        if "backtest_trade" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("backtest_trade")}
            adds = [
                ("quantity", "INTEGER DEFAULT 0"),
                ("buy_amount", "FLOAT DEFAULT 0.0"),
                ("sell_amount", "FLOAT DEFAULT 0.0"),
                ("profit_amount", "FLOAT DEFAULT 0.0"),
            ]
            for col, typedef in adds:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE backtest_trade ADD COLUMN {col} {typedef}"))
