"""分位收益分析（5 分位）。"""
from __future__ import annotations

import pandas as pd


def quintile_stats(
    df: pd.DataFrame,
    factor: str,
    *,
    target: str = "return_pct",
    n: int = 5,
) -> pd.DataFrame:
    """对 factor 列做 n 分位，统计每位的 笔数 / 平均 / 中位 / 胜率 / 大赚率。"""
    if factor not in df.columns or target not in df.columns:
        return pd.DataFrame()
    sub = df[[factor, target]].dropna()
    if sub.empty:
        return pd.DataFrame()
    bins = min(n, sub[factor].nunique())
    if bins < 2:
        return pd.DataFrame()
    try:
        sub = sub.assign(
            q=pd.qcut(sub[factor], bins, labels=[f"Q{i+1}" for i in range(bins)], duplicates="drop")
        )
    except ValueError:
        return pd.DataFrame()
    g = sub.groupby("q", observed=True)[target].agg(
        count="count",
        mean="mean",
        median="median",
        win_rate=lambda x: (x > 0).mean() * 100,
        big_win_rate=lambda x: (x >= 20).mean() * 100,
    )
    return g.round(2).reset_index().rename(columns={"q": "quantile"})
