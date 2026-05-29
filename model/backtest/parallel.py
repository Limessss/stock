"""回测并行 worker。

放在独立模块里，方便 multiprocessing pickle / spawn 子进程时 import。
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from ..data.cache import DataCache
from ..data.indicators import add_spread_column
from ..data.names import get_stock_name
from ..data.tdx_parser import market_of
from ..strategies import get_strategy, tier_of
from .simulate_legacy import simulate_one


def _simulate_chunk(df: pd.DataFrame, idxs: list[int], cfg: dict, code: str | None = None) -> list:
    """根据 cfg['engine'] 选 simulate 实现。"""
    stock_name = get_stock_name(code) if code else ""
    if cfg.get("engine", "legacy") == "vectorbt":
        from .vbt_engine import simulate_codes_vbt
        return simulate_codes_vbt(
            df, idxs,
            take_profit=cfg["take_profit"], stop_loss=cfg["stop_loss"],
            max_hold=cfg["max_hold"], split_tp=cfg.get("split_tp"),
            code=code,
            name=stock_name or None,
        )
    return [
        simulate_one(
            df, i,
            take_profit=cfg["take_profit"], stop_loss=cfg["stop_loss"],
            max_hold=cfg["max_hold"], split_tp=cfg.get("split_tp"),
            t_plus_1=cfg.get("t_plus_1", True),
            code=code,
            name=stock_name or None,
        )
        for i in idxs
    ]


def _scan_one_code(
    code: str,
    df: pd.DataFrame,
    strategy,
    ts_start: pd.Timestamp,
    ts_end: pd.Timestamp,
    cfg: dict,
) -> list[dict]:
    in_range = (df["date"] >= ts_start) & (df["date"] <= ts_end)
    if not in_range.any():
        return []
    hits: list[tuple[int, object]] = []
    for idx in df.index[in_range].tolist():
        res = strategy.scan(code, df, df.iloc[idx]["date"], indicators_ready=True)
        if res is not None:
            hits.append((idx, res))
    if not hits:
        return []
    sims = _simulate_chunk(df, [h[0] for h in hits], cfg, code=code)
    out: list[dict] = []
    for (idx, res), sim in zip(hits, sims):
        if not sim.executable:
            continue
        days_since_test = (
            pd.Timestamp(res.date) - pd.Timestamp(getattr(res, "test_date", res.date))
        ).days
        out.append(dict(
            code=code,
            signal_date=res.date,
            tier=tier_of(cfg["strategy_name"], res.score),
            market=market_of(code),
            score=res.score,
            breakout_pct=res.breakout_pct,
            is_limit_up=getattr(res, "is_limit_up", False),
            vol_ratio=getattr(res, "vol_ratio", 0.0),
            macd=getattr(res, "macd", 0.0),
            dif=getattr(res, "dif", 0.0),
            pullback_pct=getattr(res, "pullback_pct", 0.0),
            ma_spread_pct=getattr(res, "ma_spread_pct", 0.0),
            days_since_test=days_since_test,
            close_to_ma30=getattr(res, "close_to_ma30", 1.0),
            close_to_low60=getattr(res, "close_to_low60", 1.0),
            body_ratio=getattr(res, "body_ratio", 0.0),
            day_change_pct=getattr(res, "day_change_pct", 0.0),
            bull_ma_count=getattr(res, "bull_ma_count", 0),
            buy_price=sim.buy_price,
            buy_date=sim.buy_date,
            sell_price=sim.sell_price,
            sell_date=sim.sell_date,
            sell_reason=sim.sell_reason,
            return_pct=sim.return_pct,
            max_up_pct=sim.max_up_pct,
            max_dn_pct=sim.max_dn_pct,
            hold_days=sim.hold_days,
        ))
    return out


_WORKER_STATE: dict[str, Any] = {}


def _ensure_worker_state(raw_dir: str, cache_dir: str, cfg: dict) -> tuple[DataCache, Any]:
    """worker 内复用同一个 DataCache + Strategy 实例。"""
    key = (raw_dir, cache_dir, cfg["strategy_name"], frozenset(cfg.get("strategy_params", {}).items()))
    state = _WORKER_STATE.get("state")
    if state is None or _WORKER_STATE.get("key") != key:
        cache = DataCache(Path(raw_dir), Path(cache_dir))
        strategy = get_strategy(cfg["strategy_name"], cfg.get("strategy_params", {}))
        _WORKER_STATE["state"] = (cache, strategy)
        _WORKER_STATE["key"] = key
    return _WORKER_STATE["state"]


def process_codes_chunk(args: tuple) -> list[dict]:
    """worker 入口：处理一批 code，返回 trades dict 列表。

    args = (codes_chunk, raw_dir_str, cache_dir_str, cfg_dict)
    cfg_dict 至少包含: start_date, end_date, take_profit, stop_loss, max_hold,
        split_tp, strategy_name, strategy_params。
    """
    codes_chunk, raw_dir, cache_dir, cfg = args
    cache, strategy = _ensure_worker_state(raw_dir, cache_dir, cfg)
    ts_start = pd.Timestamp(cfg["start_date"])
    ts_end = pd.Timestamp(cfg["end_date"])

    trades: list[dict] = []
    for code in codes_chunk:
        df = cache.load_no_cache(code)
        if df is None:
            continue
        if "ma_spread_pct" not in df.columns:
            add_spread_column(df, inplace=True)
        trades.extend(_scan_one_code(code, df, strategy, ts_start, ts_end, cfg))
    return trades
