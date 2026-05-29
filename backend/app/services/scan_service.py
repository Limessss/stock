"""扫描业务编排：遍历所有缓存 + 运行策略 + 排序。"""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from model.data.tdx_parser import market_of
from model.strategies import get_strategy, tier_of

from .cache_service import get_cache
from .name_service import enrich_names, get_name


def run_scan(
    strategy_name: str,
    strategy_params: dict[str, Any],
    target_date: str | None,
    limit: int | None = None,
    sort_by: str = "score",
    desc: bool = True,
    max_codes: int | None = None,
) -> dict[str, Any]:
    """对所有缓存中的股票，在指定交易日跑一次扫描，返回排序后的命中列表。

    target_date=None 表示用每只股票的最后一个交易日。
    max_codes 用于调试/小样本快速验证。
    """
    cache = get_cache()
    codes = cache.codes()
    if max_codes:
        codes = codes[:max_codes]

    if not codes:
        return {
            "rows": [],
            "total": 0,
            "took_ms": 0,
            "warning": "缓存为空，请先调用 POST /api/data/build 构建缓存",
        }

    strategy = get_strategy(strategy_name, strategy_params)
    ts = pd.Timestamp(target_date) if target_date else None

    t0 = time.perf_counter()
    rows: list[dict[str, Any]] = []
    scanned = 0
    for code in codes:
        df = cache.load_no_cache(code)
        if df is None:
            continue
        scanned += 1
        try:
            res = strategy.scan(code, df, ts, indicators_ready=True)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "scan failed for %s: %s", code, exc, exc_info=True
            )
            continue
        if res is None:
            continue

        days_since_test = 0
        test_date = getattr(res, "test_date", None)
        if test_date:
            try:
                days_since_test = (pd.Timestamp(res.date) - pd.Timestamp(test_date)).days
            except Exception:
                days_since_test = 0

        rows.append({
            "code": res.code,
            "name": get_name(res.code),
            "market": market_of(res.code),
            "tier": tier_of(strategy_name, res.score),
            "date": res.date,
            "close": round(res.close, 2),
            "score": round(res.score, 2),
            "breakout_pct": round(res.breakout_pct, 2),
            "is_limit_up": getattr(res, "is_limit_up", False),
            "washout_high": round(getattr(res, "washout_high", 0.0), 2),
            "test_date": test_date,
            "days_since_test": days_since_test,
            "pullback_pct": round(getattr(res, "pullback_pct", 0.0), 2),
            "vol_ratio": round(getattr(res, "vol_ratio", 0.0), 2),
            "ma_spread_pct": round(getattr(res, "ma_spread_pct", 0.0), 2),
            "macd": round(getattr(res, "macd", 0.0), 4),
            "dif": round(getattr(res, "dif", 0.0), 4),
            "close_to_ma30": round(getattr(res, "close_to_ma30", 1.0), 3),
            "day_change_pct": round(getattr(res, "day_change_pct", 0.0), 2),
            "bull_ma_count": getattr(res, "bull_ma_count", 0),
            "mode": getattr(res, "mode", ""),
        })

    rows.sort(key=lambda r: r.get(sort_by, 0) or 0, reverse=desc)
    if limit:
        rows = rows[:limit]

    missing = list({r["code"] for r in rows if not r["name"]})
    if missing:
        enriched = enrich_names(missing)
        for r in rows:
            if not r["name"]:
                r["name"] = enriched.get(r["code"].upper(), "")

    took_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "rows": rows,
        "total": len(rows),
        "scanned": scanned,
        "took_ms": took_ms,
        "strategy": strategy_name,
        "target_date": target_date,
    }
