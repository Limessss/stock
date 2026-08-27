"""model 层时间工具（不依赖 backend）。"""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
MARKET_CLOSE = time(15, 0)
MARKET_CLOSE_BUFFER = time(15, 5)


def utc_now_iso() -> str:
    """UTC ISO8601 字符串，供 manifest / meta 落盘。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def is_trading_session(trading_dates: list[str] | None = None) -> bool:
    """当前是否处于 A 股连续竞价时段（9:30–11:30、13:00–15:00）。"""
    now = beijing_now()
    today = now.strftime("%Y-%m-%d")
    if trading_dates is not None:
        if today not in trading_dates:
            return False
    elif now.weekday() >= 5:
        return False
    t = now.time()
    if time(9, 30) <= t <= time(11, 30):
        return True
    if time(13, 0) <= t <= MARKET_CLOSE:
        return True
    return False


def is_after_market_close(trade_date: str) -> bool:
    """指定交易日是否已过收盘缓冲（15:05 后视为可落盘）。"""
    now = beijing_now()
    today = now.strftime("%Y-%m-%d")
    if trade_date < today:
        return True
    if trade_date > today:
        return False
    return now.time() >= MARKET_CLOSE_BUFFER
