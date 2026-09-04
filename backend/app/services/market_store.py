"""指数行情数据库读写与按需同步。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from model.data.a_stock_market import (
    INDEX_SPECS,
    eastmoney_index_kline,
    fetch_market_day,
    fetch_market_stats,
    get_trading_calendar,
    recalc_index_change,
    tdx_index_amount_sum,
    tencent_index_kline,
)
from model.data.time_util import is_after_market_close

from ..core.config import settings
from ..core.time_utils import as_utc_aware, utc_now
from ..models.market import MarketDailySummary, MarketIndexDaily

INDEX_CODES = {s["code"] for s in INDEX_SPECS}
REQUIRED_INDEX_COUNT = len(INDEX_SPECS)
BEIJING = ZoneInfo("Asia/Shanghai")


def is_day_complete(session: Session, trade_date: str) -> bool:
    """当日四指数 close 均已入库视为完整。"""
    count = session.scalar(
        select(func.count())
        .select_from(MarketIndexDaily)
        .where(
            MarketIndexDaily.trade_date == trade_date,
            MarketIndexDaily.close.isnot(None),
        )
    )
    return int(count or 0) >= REQUIRED_INDEX_COUNT


def save_market_day(session: Session, payload: dict) -> None:
    """写入或更新某日指数 K 线与市场汇总。"""
    trade_date = payload["trade_date"]
    now = utc_now()
    source = payload.get("data_source") or "a-stock-data-http"
    indices = payload.get("indices") or []

    session.execute(
        delete(MarketIndexDaily).where(MarketIndexDaily.trade_date == trade_date)
    )
    for idx in indices:
        if idx.get("code") not in INDEX_CODES:
            continue
        session.add(
            MarketIndexDaily(
                trade_date=trade_date,
                index_code=idx["code"],
                index_name=idx.get("name") or "",
                open=idx.get("open"),
                high=idx.get("high"),
                low=idx.get("low"),
                close=idx.get("close"),
                prev_close=idx.get("prev_close"),
                change_amt=idx.get("change_amt"),
                change_pct=idx.get("change_pct"),
                volume=idx.get("volume"),
                amount=idx.get("amount"),
                data_source=source,
                fetched_at=now,
            )
        )

    summary = session.get(MarketDailySummary, trade_date)
    if summary is None:
        summary = MarketDailySummary(trade_date=trade_date)
        session.add(summary)
    if payload.get("up_count") is not None:
        summary.up_count = payload.get("up_count")
    if payload.get("down_count") is not None:
        summary.down_count = payload.get("down_count")
    if payload.get("flat_count") is not None:
        summary.flat_count = payload.get("flat_count")
    if payload.get("total_amount") is not None:
        summary.total_amount = payload.get("total_amount")
    summary.data_source = source
    summary.fetched_at = now


def summary_needs_refresh(session: Session, trade_date: str) -> bool:
    """指数已有但涨跌家数缺失时需补拉。"""
    summary = session.get(MarketDailySummary, trade_date)
    if summary is None:
        return True
    return (
        summary.up_count is None
        or summary.down_count is None
        or summary.total_amount is None
    )


def amount_needs_refresh(session: Session, trade_date: str) -> bool:
    """识别历史上误存为两市合计的单市场成交额。"""
    if not is_after_market_close(trade_date):
        return False
    summary = session.get(MarketDailySummary, trade_date)
    if summary is None or summary.total_amount is None:
        return False
    expected = tdx_index_amount_sum(trade_date, settings.raw_dir)
    if expected is None or expected <= 0:
        return False
    return abs(float(summary.total_amount) - expected) / expected >= 0.05


def _market_close_utc(trade_date: str) -> datetime:
    """交易日 15:05 北京时间对应的 UTC 时刻。"""
    local = datetime.strptime(trade_date, "%Y-%m-%d").replace(
        hour=15, minute=5, second=0, microsecond=0, tzinfo=BEIJING
    )
    return local.astimezone(ZoneInfo("UTC"))


def needs_post_close_refresh(session: Session, trade_date: str) -> bool:
    """若数据在收盘前入库，收盘后需重新拉取正式收盘数据。"""
    if not is_day_complete(session, trade_date):
        return False
    if not is_after_market_close(trade_date):
        return False

    summary = session.get(MarketDailySummary, trade_date)
    if summary is None or summary.fetched_at is None:
        return True

    return as_utc_aware(summary.fetched_at) < _market_close_utc(trade_date)


def needs_official_refresh(session: Session, trade_date: str) -> bool:
    """库内收盘价与官方日 K 偏差较大时重拉（修正盘中快照误入库）。"""
    if not is_day_complete(session, trade_date):
        return False
    if not is_after_market_close(trade_date):
        return False

    stored = session.scalar(
        select(MarketIndexDaily.close).where(
            MarketIndexDaily.trade_date == trade_date,
            MarketIndexDaily.index_code == "SH000001",
            MarketIndexDaily.close.isnot(None),
        )
    )
    if stored is None:
        return False

    official_close = _official_index_close(
        next(s for s in INDEX_SPECS if s["code"] == "SH000001"), trade_date
    )
    if official_close is None:
        return False

    return abs(float(stored) - official_close) >= 0.5


def _official_index_close(spec: dict[str, str], trade_date: str) -> float | None:
    bar = eastmoney_index_kline(spec["secid"], trade_date)
    if bar is None:
        bar = tencent_index_kline(spec["tencent_symbol"], trade_date)
    if not bar or bar.get("close") is None:
        return None
    return float(bar["close"])


def needs_change_refresh(session: Session, trade_date: str) -> bool:
    """库内涨跌幅与官方上一日收盘价推算不一致时重拉。"""
    if not is_day_complete(session, trade_date):
        return False
    if not is_after_market_close(trade_date):
        return False

    calendar = get_trading_calendar()
    prior = [d for d in calendar if d < trade_date]
    if not prior:
        return False
    prev_date = prior[-1]

    spec = next(s for s in INDEX_SPECS if s["code"] == "SH000001")
    row = session.scalar(
        select(MarketIndexDaily)
        .where(
            MarketIndexDaily.trade_date == trade_date,
            MarketIndexDaily.index_code == "SH000001",
        )
        .limit(1)
    )
    if row is None or row.close is None or row.change_pct is None:
        return False

    prev_close = _official_index_close(spec, prev_date)
    if prev_close is None:
        return False

    _, expected_pct, _ = recalc_index_change(float(row.close), prev_close)
    if expected_pct is None:
        return False
    return abs(float(row.change_pct) - expected_pct) >= 0.05


def refresh_market_stats(session: Session, trade_date: str) -> None:
    """仅补拉并更新涨跌家数、成交额汇总。"""
    cache_dir = settings.cache_dir
    stats = fetch_market_stats(
        trade_date,
        cache_dir=cache_dir,
        raw_dir=settings.raw_dir,
    )
    if stats.up_count is None and stats.down_count is None and stats.total_amount is None:
        return

    summary = session.get(MarketDailySummary, trade_date)
    if summary is None:
        summary = MarketDailySummary(trade_date=trade_date)
        session.add(summary)

    if stats.up_count is not None:
        summary.up_count = stats.up_count
    if stats.down_count is not None:
        summary.down_count = stats.down_count
    if stats.total_amount is not None:
        summary.total_amount = stats.total_amount
    summary.fetched_at = utc_now()
    session.commit()


def fetch_and_save(session: Session, trade_date: str) -> dict:
    """从 HTTP 拉取并入库。"""
    cache_dir = settings.cache_dir
    payload = fetch_market_day(
        trade_date,
        cache_dir=cache_dir,
        raw_dir=settings.raw_dir,
    )
    if any(i.get("close") is not None for i in payload.get("indices", [])):
        save_market_day(session, payload)
        session.commit()
    return payload


def ensure_market_day(session: Session, trade_date: str) -> tuple[bool, bool]:
    """确保某日数据在库中。返回 (是否已完整, 是否新拉取)。"""
    fetched = False
    if not is_day_complete(session, trade_date):
        fetch_and_save(session, trade_date)
        fetched = True
    elif needs_post_close_refresh(session, trade_date):
        fetch_and_save(session, trade_date)
        fetched = True
    elif needs_official_refresh(session, trade_date):
        fetch_and_save(session, trade_date)
        fetched = True
    elif needs_change_refresh(session, trade_date):
        fetch_and_save(session, trade_date)
        fetched = True
    elif amount_needs_refresh(session, trade_date):
        refresh_market_stats(session, trade_date)
        fetched = True
    elif summary_needs_refresh(session, trade_date):
        refresh_market_stats(session, trade_date)
        fetched = True
    return is_day_complete(session, trade_date), fetched


def load_market_day(session: Session, trade_date: str) -> dict | None:
    """从数据库读取某日行情。"""
    rows = session.scalars(
        select(MarketIndexDaily)
        .where(MarketIndexDaily.trade_date == trade_date)
        .order_by(MarketIndexDaily.index_code)
    ).all()
    if not rows:
        return None

    summary = session.get(MarketDailySummary, trade_date)
    indices = [
        {
            "code": r.index_code,
            "name": r.index_name,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "prev_close": r.prev_close,
            "change_amt": r.change_amt,
            "change_pct": r.change_pct,
            "volume": r.volume,
            "amount": r.amount,
        }
        for r in rows
    ]
    return {
        "trade_date": trade_date,
        "indices": indices,
        "up_count": summary.up_count if summary else None,
        "down_count": summary.down_count if summary else None,
        "flat_count": summary.flat_count if summary else None,
        "total_amount": summary.total_amount if summary else None,
        "data_source": rows[0].data_source if rows else "database",
    }


def load_index_kline(
    session: Session,
    index_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """从数据库读取指数 K 线序列。"""
    stmt = (
        select(MarketIndexDaily)
        .where(MarketIndexDaily.index_code == index_code)
        .order_by(MarketIndexDaily.trade_date)
    )
    if start_date:
        stmt = stmt.where(MarketIndexDaily.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(MarketIndexDaily.trade_date <= end_date)

    rows = session.scalars(stmt).all()
    return [
        {
            "trade_date": r.trade_date,
            "code": r.index_code,
            "name": r.index_name,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "prev_close": r.prev_close,
            "change_amt": r.change_amt,
            "change_pct": r.change_pct,
            "volume": r.volume,
            "amount": r.amount,
        }
        for r in rows
    ]


def count_stored_days(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(MarketDailySummary)) or 0
    )
