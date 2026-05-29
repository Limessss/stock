"""信息系数（IC）相关分析。"""
from __future__ import annotations

import pandas as pd


# 默认参与分析的因子（字段名 → 中文标签）
DEFAULT_FACTORS: list[tuple[str, str]] = [
    ("score", "综合评分"),
    ("breakout_pct", "突破幅度%"),
    ("vol_ratio", "量比5"),
    ("macd", "MACD柱"),
    ("dif", "DIF"),
    ("pullback_pct", "回踩幅度%"),
    ("ma_spread_pct", "均线粘合%"),
    ("days_since_test", "试盘距今(日)"),
    ("close_to_ma30", "收盘/MA30"),
    ("close_to_low60", "收盘/60日低"),
    ("body_ratio", "实体/振幅"),
    ("day_change_pct", "当日涨幅%"),
    ("bull_ma_count", "多头组数"),
]


def rank_ic(x: pd.Series, y: pd.Series) -> float:
    """Spearman 秩相关系数（IC）。"""
    return float(x.rank().corr(y.rank()))


def ic_table(
    df: pd.DataFrame,
    factors: list[tuple[str, str]] | None = None,
    *,
    target_return: str = "return_pct",
    target_up: str = "max_up_pct",
) -> pd.DataFrame:
    """对 trades 数据计算每个因子相对于 return / max_up 的 IC，返回排序后的 DataFrame。"""
    factors = factors or DEFAULT_FACTORS
    rows = []
    for col, label in factors:
        if col not in df.columns:
            continue
        ic = rank_ic(df[col], df[target_return]) if target_return in df.columns else None
        ic_up = rank_ic(df[col], df[target_up]) if target_up in df.columns else None
        rows.append({
            "field": col,
            "label": label,
            "ic_return": round(ic, 4) if ic is not None else None,
            "ic_max_up": round(ic_up, 4) if ic_up is not None else None,
        })
    out = pd.DataFrame(rows)
    if not out.empty and "ic_return" in out.columns:
        out = out.reindex(
            out["ic_return"].abs().sort_values(ascending=False).index
        ).reset_index(drop=True)
    return out
