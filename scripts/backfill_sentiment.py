"""批量回填最近若干交易日的情绪周期缓存。"""
from __future__ import annotations

import argparse
import time

import pandas as pd
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, init_db
from backend.app.core.time_utils import utc_now
from backend.app.models.sentiment import SentimentDaily, SentimentLadderItem
from backend.app.services import sentiment_service
from model.data.market_overview import build_overview_sync, lookup_overview
from model.data.sentiment import calculate_local_sentiment_batch
from model.data.tdx_parser import parse_day_file


def _target_dates(days: int) -> list[str]:
    index_path = settings.raw_dir / "sh" / "lday" / "sh000001.day"  # type: ignore[operator]
    index_df = parse_day_file(index_path, min_records=1)
    if index_df is None or index_df.empty:
        raise RuntimeError(f"无法从 {index_path} 读取交易日历")
    dates = [pd.Timestamp(value).strftime("%Y-%m-%d") for value in index_df["date"]]
    return dates[-days:]


def _local_ladder(session, trade_date: str) -> list[dict]:
    items = session.scalars(
        select(SentimentLadderItem).where(SentimentLadderItem.trade_date == trade_date)
    ).all()
    return [
        {
            "code": item.code,
            "name": item.name,
            "board_count": item.board_count,
            "board_type": item.board_type,
            "limit_time": item.limit_time,
            "reason": item.reason,
            "themes": item.themes or [],
            "source": item.source,
        }
        for item in items
    ]


def backfill(days: int, *, local_only: bool = False) -> None:
    init_db()
    dates = _target_dates(days)
    print(f"目标交易日: {dates[0]} 至 {dates[-1]}，共 {len(dates)} 天", flush=True)

    session = SessionLocal()
    try:
        existing_local = set(
            session.scalars(
                select(SentimentDaily.trade_date).where(
                    SentimentDaily.trade_date.in_(dates),
                    SentimentDaily.local_complete.is_(True),
                )
            ).all()
        )
        missing = [date for date in dates if date not in existing_local]
        print(f"本地已完成 {len(existing_local)} 天，待计算 {len(missing)} 天", flush=True)

        overview = build_overview_sync(settings.raw_dir, settings.cache_dir)  # type: ignore[arg-type]
        print(f"市场总览已更新至 {overview['trade_date'].max()}", flush=True)
        results = calculate_local_sentiment_batch(settings.cache_dir, missing)  # type: ignore[arg-type]
        for index, date in enumerate(missing, start=1):
            result = results[date]
            if not result["complete"]:
                raise RuntimeError(f"{date} 未扫描到有效行情")
            daily = sentiment_service._ensure_daily(session, date)
            market = lookup_overview(overview, date) or {}
            daily.sh_change_pct = market.get("index_change_pct")
            daily.up_count = result["up_count"]
            daily.down_count = result["down_count"]
            daily.flat_count = result["flat_count"]
            daily.limit_up_count = result["limit_up_count"]
            daily.limit_down_count = result["limit_down_count"]
            daily.limit_down_stocks = result["limit_down_stocks"]
            daily.broken_board_count = result["broken_board_count"]
            daily.new_high_100_count = result["new_high_100_count"]
            daily.scanned_stock_count = result["scanned_stock_count"]
            daily.new_high_stocks = result["new_high_stocks"]
            daily.local_complete = True
            daily.sync_error = ""
            daily.updated_at = utc_now()
            sentiment_service._replace_ladder(session, date, result["ladder"])
            session.commit()
            if index == 1 or index % 10 == 0 or index == len(missing):
                print(f"本地写入进度: {index}/{len(missing)} ({date})", flush=True)

        if local_only:
            return

        pending_external = list(
            session.scalars(
                select(SentimentDaily).where(
                    SentimentDaily.trade_date.in_(dates),
                    SentimentDaily.local_complete.is_(True),
                    SentimentDaily.external_complete.is_(False),
                ).order_by(SentimentDaily.trade_date)
            ).all()
        )
        print(f"外部增强待同步 {len(pending_external)} 天", flush=True)
        for index, daily in enumerate(pending_external, start=1):
            try:
                result = sentiment_service._sync_external(
                    session,
                    daily,
                    _local_ladder(session, daily.trade_date),
                    force=False,
                )
                sentiment_service._auto_mark_three_board_origins(session, daily.trade_date)
                daily.updated_at = utc_now()
                session.commit()
                requests = result.get("network_requests", 0)
                print(
                    f"外部同步进度: {index}/{len(pending_external)} "
                    f"({daily.trade_date}, {daily.external_status}, 请求 {requests})",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                failed = session.get(SentimentDaily, daily.trade_date)
                if failed is not None:
                    failed.external_complete = False
                    failed.external_status = "error"
                    failed.sync_error = f"{type(exc).__name__}: {exc}"[:2000]
                    failed.updated_at = utc_now()
                    session.commit()
                print(f"外部同步失败: {daily.trade_date}: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(0.15)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180, help="最近交易日数量")
    parser.add_argument("--local-only", action="store_true", help="仅计算本地指标")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days 必须大于 0")
    backfill(args.days, local_only=args.local_only)


if __name__ == "__main__":
    main()
