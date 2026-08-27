"""行情总览服务（数据库持久化 + HTTP 按需同步）。"""

from __future__ import annotations



import pandas as pd

from sqlalchemy.orm import Session



from model.data.a_stock_market import get_trading_calendar, resolve_trade_date



from . import market_store





def _overview_from_data(

    requested: str,

    trade_date: str,

    adjusted: bool,

    data: dict | None,

) -> dict:

    indices = (data or {}).get("indices") or []

    sh_index = next((i for i in indices if i.get("code") == "SH000001"), None)

    ready = bool(indices) and any(i.get("close") is not None for i in indices)



    return {

        "requested_date": requested,

        "trade_date": trade_date,

        "is_non_trading_day": adjusted,

        "ready": ready,

        "indices": indices,

        "index_name": "上证指数",

        "index_close": sh_index.get("close") if sh_index else None,

        "index_change_pct": sh_index.get("change_pct") if sh_index else None,

        "index_change_amt": sh_index.get("change_amt") if sh_index else None,

        "up_count": (data or {}).get("up_count"),

        "down_count": (data or {}).get("down_count"),

        "flat_count": (data or {}).get("flat_count"),

        "total_amount": (data or {}).get("total_amount"),

        "data_source": (data or {}).get("data_source") or "database",

    }





def ensure_market_days(session: Session, requested_dates: list[str]) -> dict[str, dict]:

    """检查并补齐数据库中的行情（非交易日对齐上一交易日）。"""

    trading_dates = get_trading_calendar()

    results: dict[str, dict] = {}



    for req in requested_dates:

        norm = pd.Timestamp(req).strftime("%Y-%m-%d")

        trade_date, adjusted = resolve_trade_date(norm, trading_dates)

        complete, fetched = market_store.ensure_market_day(session, trade_date)

        data = market_store.load_market_day(session, trade_date)

        results[norm] = {

            **_overview_from_data(norm, trade_date, adjusted, data),

            "synced": fetched,

            "complete": complete,

        }

    return results





def get_market_overview(session: Session, requested_date: str) -> dict:

    return get_market_overviews(session, [requested_date])[requested_date]





def get_market_overviews(session: Session, requested_dates: list[str]) -> dict[str, dict]:

    synced = ensure_market_days(session, requested_dates)

    return {k: {kk: vv for kk, vv in v.items() if kk not in ("synced", "complete")} for k, v in synced.items()}





def sync_today(session: Session, requested_date: str | None = None) -> dict:

    """打开网页时同步：检查当日（或非交易日上一交易日）并自动拉取。"""

    if requested_date:

        target = pd.Timestamp(requested_date).strftime("%Y-%m-%d")

    else:

        target = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d")



    result = ensure_market_days(session, [target])

    item = result[target]

    return {

        "requested_date": target,

        "trade_date": item["trade_date"],

        "is_non_trading_day": item["is_non_trading_day"],

        "complete": item["complete"],

        "fetched": item["synced"],

        "ready": item["ready"],

    }





def get_index_kline(

    session: Session,

    index_code: str,

    start_date: str | None = None,

    end_date: str | None = None,

) -> list[dict]:

    return market_store.load_index_kline(session, index_code, start_date, end_date)





def get_status(session: Session) -> dict:

    return {

        "running": False,

        "ready": True,

        "building": False,

        "error": None,

        "date_count": market_store.count_stored_days(session),

    }

