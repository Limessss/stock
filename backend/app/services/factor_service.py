"""因子分析 service。

从 SQLite 读取指定任务的 trades，调用 model.factor_analysis 计算 IC + 分位收益。
"""
from __future__ import annotations

import pandas as pd

from model.factor_analysis.ic import DEFAULT_FACTORS, ic_table
from model.factor_analysis.quantile import quintile_stats

from ..core.database import session_scope
from ..models.backtest import BacktestTask, BacktestTrade


def load_trades_df(task_id: str) -> pd.DataFrame | None:
    """加载指定 task 的 trades 为 DataFrame；任务不存在返回 None。"""
    with session_scope() as s:
        if s.get(BacktestTask, task_id) is None:
            return None
        rows = s.query(BacktestTrade).filter(BacktestTrade.task_id == task_id).all()
        if not rows:
            return pd.DataFrame()
        records = [
            {
                "score": r.score,
                "breakout_pct": r.breakout_pct,
                "vol_ratio": r.vol_ratio,
                "macd": r.macd,
                "dif": r.dif,
                "pullback_pct": r.pullback_pct,
                "ma_spread_pct": r.ma_spread_pct,
                "days_since_test": r.days_since_test,
                "close_to_ma30": r.close_to_ma30,
                "close_to_low60": r.close_to_low60,
                "body_ratio": r.body_ratio,
                "day_change_pct": r.day_change_pct,
                "bull_ma_count": r.bull_ma_count,
                "is_limit_up": int(bool(r.is_limit_up)),
                "return_pct": r.return_pct,
                "max_up_pct": r.max_up_pct,
                "max_dn_pct": r.max_dn_pct,
                "hold_days": r.hold_days,
            }
            for r in rows
        ]
    return pd.DataFrame(records)


def analyze(task_id: str, *, target: str = "return_pct", quantile_n: int = 5) -> dict | None:
    df = load_trades_df(task_id)
    if df is None:
        return None
    if df.empty:
        return {"task_id": task_id, "total_trades": 0, "ic": [], "quantiles": []}

    ic_df = ic_table(df)
    ic_rows = [
        {
            "field": r.field,
            "label": r.label,
            "ic_return": r.ic_return if pd.notna(r.ic_return) else None,
            "ic_max_up": r.ic_max_up if pd.notna(r.ic_max_up) else None,
        }
        for r in ic_df.itertuples(index=False)
    ]

    quantiles = []
    for col, label in DEFAULT_FACTORS:
        if col not in df.columns:
            continue
        q = quintile_stats(df, col, target=target, n=quantile_n)
        if q.empty:
            continue
        quantiles.append({
            "field": col,
            "label": label,
            "quantiles": [
                {
                    "quantile": str(row.quantile),
                    "count": int(row.count),
                    "mean": float(row.mean),
                    "median": float(row.median),
                    "win_rate": float(row.win_rate),
                    "big_win_rate": float(row.big_win_rate),
                }
                for row in q.itertuples(index=False)
            ],
        })

    return {
        "task_id": task_id,
        "total_trades": int(len(df)),
        "ic": ic_rows,
        "quantiles": quantiles,
    }
