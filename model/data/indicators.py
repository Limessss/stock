"""技术指标计算。"""
from __future__ import annotations

import pandas as pd


_MA_COLS = ("ma5", "ma10", "ma20", "ma30", "ma60")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在 df 上追加均线、MACD、成交量均线、ma_spread_pct 等列。"""
    df = df.copy()
    for period in (5, 10, 20, 30, 60):
        df[f"ma{period}"] = df["close"].rolling(period, min_periods=period).mean()

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["dif"] = ema12 - ema26
    df["dea"] = df["dif"].ewm(span=9, adjust=False).mean()
    df["macd"] = 2 * (df["dif"] - df["dea"])

    df["vol_ma20"] = df["volume"].rolling(20, min_periods=20).mean()
    df["vol_ma5"] = df["volume"].rolling(5, min_periods=5).mean()

    # 向量化 ma_spread_pct：每行五条均线的 (max-min)/close
    add_spread_column(df, inplace=True)
    return df


def add_spread_column(df: pd.DataFrame, *, inplace: bool = False) -> pd.DataFrame:
    """添加 ma_spread_pct 列（如缺失）。返回 df（inplace=True 时返回同对象）。

    对旧 Parquet 缓存（没有 ma_spread_pct）懒补全用。
    """
    if "ma_spread_pct" in df.columns:
        return df
    if not inplace:
        df = df.copy()
    mas = df[list(_MA_COLS)]
    df["ma_spread_pct"] = (mas.max(axis=1) - mas.min(axis=1)) / df["close"]
    return df


def ma_spread_pct(row: pd.Series) -> float:
    """(保留兼容) 单行版本。"""
    mas = [row.get(c) for c in _MA_COLS]
    if any(pd.isna(m) for m in mas):
        return float("nan")
    close = row["close"]
    if close <= 0:
        return float("nan")
    return (max(mas) - min(mas)) / close  # type: ignore[arg-type]


def bull_ma_count(row: pd.Series) -> int:
    """统计多头排列的均线对数（MA5>MA10, MA10>MA20, MA20>MA30, MA30>MA60）。"""
    pairs = [(5, 10), (10, 20), (20, 30), (30, 60)]
    cnt = 0
    for a, b in pairs:
        ma_a, ma_b = row.get(f"ma{a}"), row.get(f"ma{b}")
        if pd.notna(ma_a) and pd.notna(ma_b) and ma_a > ma_b:
            cnt += 1
    return cnt
