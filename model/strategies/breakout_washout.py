"""洗盘突破策略：寻找『前期横盘 → 试盘高点 → 缩量回踩 → 当日放量突破』的形态。

迁移自原 scan_breakout.py 的 scan_one 实现，逻辑完全一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..data.indicators import add_indicators, add_spread_column, bull_ma_count
from .base import ScanResult, Strategy


@dataclass
class BreakoutParams:
    min_history: int = 80
    consolidation_lookback: int = 60
    max_range_pct: float = 0.50
    ma_spread_max_pct: float = 0.12
    require_consolidation: bool = False
    test_search_start: int = 3
    test_search_end: int = 60
    min_pullback_pct: float = 0.015
    max_pullback_pct: float = 0.35
    min_test_vol_ratio: float = 1.10
    max_pullback_vol_ratio: float = 1.15
    quiet_days: int = 3
    breakout_vol_ratio: float = 1.05
    min_ma_bull_count: int = 2
    macd_hist_min: float = -0.05
    close_above_ma20: bool = True
    require_yang_line: bool = False
    require_ma5_up: bool = True
    require_pre_consolidation: bool = False
    min_breakout_pct: float = 0.005
    # 起爆点过滤
    max_close_ma30_ratio: float = 1.40
    max_close_low60_ratio: float = 2.50
    require_positive_macd_hist: bool = True
    max_close_over_washout: float = 1.35
    # K 线形态过滤
    min_day_change: float = 0.005
    min_body_to_range: float = 0.30
    max_upper_shadow_ratio: float = 1.50
    # 胜率优先模式（方案 B）
    winrate_mode: bool = False
    wr_max_close_to_ma30: float = 1.10
    wr_max_ma_spread_pct: float = 0.04
    wr_min_day_change: float = 0.02
    wr_max_day_change: float = 0.06
    wr_min_vol_ratio: float = 1.5
    wr_require_macd_positive: bool = True
    wr_exclude_limit_up: bool = True


@dataclass
class BreakoutResult(ScanResult):
    washout_high: float = 0.0
    test_date: str = ""
    pullback_pct: float = 0.0
    vol_ratio: float = 0.0
    ma_spread_pct: float = 0.0
    macd: float = 0.0
    dif: float = 0.0
    bull_ma_count: int = 0
    is_limit_up: bool = False
    close_to_ma30: float = 1.0
    close_to_low60: float = 1.0
    body_ratio: float = 0.0
    day_change_pct: float = 0.0


def _find_washout_high(
    df: pd.DataFrame, idx: int, params: BreakoutParams
) -> tuple[float, int, float] | None:
    start = idx - params.test_search_end
    end = idx - params.test_search_start
    if start < params.consolidation_lookback:
        return None

    window = df.iloc[start:end]
    if window.empty:
        return None

    peak_idx = int(window["high"].idxmax())
    peak_row = df.loc[peak_idx]
    washout_high = float(peak_row["high"])

    vol_ma = peak_row.get("vol_ma20")
    if pd.isna(vol_ma) or vol_ma <= 0:
        return None
    if peak_row["volume"] < vol_ma * params.min_test_vol_ratio:
        return None

    after = df.loc[peak_idx + 1: idx - 1]
    if len(after) < 2:
        return None

    trough_close = float(after["close"].min())
    pullback = (washout_high - trough_close) / washout_high
    if pullback < params.min_pullback_pct or pullback > params.max_pullback_pct:
        return None

    avg_pull_vol = float(after["volume"].mean())
    if avg_pull_vol > peak_row["volume"] * params.max_pullback_vol_ratio:
        return None

    if params.require_pre_consolidation:
        cons = df.iloc[peak_idx - params.consolidation_lookback: peak_idx]
        if len(cons) < 30:
            return None
        cmax, cmin = cons["close"].max(), cons["close"].min()
        if cmin <= 0:
            return None
        if (cmax - cmin) / cmin > params.max_range_pct:
            return None

    trough_low = float(after["low"].min())
    ma60 = peak_row.get("ma60")
    if pd.notna(ma60) and ma60 > 0 and trough_low < float(ma60) * 0.80:
        return None

    return washout_high, peak_idx, pullback


def _check_consolidation_ma_convergence(
    df: pd.DataFrame, peak_idx: int, params: BreakoutParams
) -> tuple[bool, float]:
    """要求 df 已包含 ma_spread_pct 列（向量化版本，比 apply axis=1 快 50-100 倍）。"""
    seg = df.iloc[peak_idx - params.consolidation_lookback: peak_idx]
    if len(seg) < 30:
        return False, float("nan")
    cmax, cmin = seg["close"].max(), seg["close"].min()
    if cmin <= 0 or (cmax - cmin) / cmin > params.max_range_pct:
        return False, float("nan")
    spreads = seg["ma_spread_pct"].dropna()
    if spreads.empty:
        return False, float("nan")
    min_spread = float(spreads.min())
    return min_spread <= params.ma_spread_max_pct, min_spread


class BreakoutWashoutStrategy(Strategy):
    name = "breakout_washout"
    label = "洗盘高点突破"
    params_cls = BreakoutParams
    description = (
        "寻找「前期横盘 → 试盘高点 → 缩量回踩 → 当日放量突破」的形态，"
        "适用于洗盘后突破类机会识别。"
    )
    features = (
        "在回看窗口内定位试盘高点与回踩幅度",
        "突破日校验量价、均线多头与 MACD",
        "可选胜率优先模式进一步收紧过滤",
        "支持 K 线形态与起爆位置过滤",
    )
    tier_rules = (
        "A：评分 ≥ 200",
        "B：评分 ≥ 130",
        "C：评分 ≥ 80",
        "D：评分 < 80",
    )

    def scan(
        self,
        code: str,
        df: pd.DataFrame,
        target_date: pd.Timestamp | None = None,
        indicators_ready: bool = False,
    ) -> BreakoutResult | None:
        params: BreakoutParams = self.params  # type: ignore[assignment]
        if not indicators_ready:
            df = add_indicators(df)
        elif "ma_spread_pct" not in df.columns:
            # 旧版 Parquet 缓存可能没有这一列；懒补全
            df = add_spread_column(df)
        if target_date is not None:
            mask = df["date"] == target_date
            if not mask.any():
                return None
            idx = int(df.index[mask][0])
        else:
            idx = len(df) - 1

        if idx < params.min_history:
            return None

        row = df.iloc[idx]
        if pd.isna(row["ma60"]):
            return None

        found = _find_washout_high(df, idx, params)
        if found is None:
            return None
        washout_high, peak_idx, pullback = found

        c = float(row["close"])
        if c <= washout_high * (1 + params.min_breakout_pct):
            return None
        if c > washout_high * params.max_close_over_washout:
            return None

        # 起爆点过滤
        if pd.notna(row["ma30"]) and row["ma30"] > 0:
            if c / float(row["ma30"]) > params.max_close_ma30_ratio:
                return None
        low60_start = max(0, idx - 60)
        low60 = float(df.iloc[low60_start: idx]["low"].min())
        if low60 > 0 and c / low60 > params.max_close_low60_ratio:
            return None

        cons_ok, min_ma_spread = _check_consolidation_ma_convergence(df, peak_idx, params)
        if params.require_consolidation and not cons_ok:
            return None
        if np.isnan(min_ma_spread):
            min_ma_spread = 0.10

        bull = bull_ma_count(row)
        if bull < params.min_ma_bull_count:
            return None
        if params.close_above_ma20 and (pd.isna(row["ma20"]) or c < row["ma20"]):
            return None

        vol_ma5 = row.get("vol_ma5")
        if pd.isna(vol_ma5) or vol_ma5 <= 0:
            return None
        vol_ratio = float(row["volume"] / vol_ma5)
        prev_close = float(df.iloc[idx - 1]["close"])
        day_chg = (c - prev_close) / prev_close if prev_close > 0 else 0.0
        is_limit_up = day_chg >= 0.095

        if day_chg < params.min_day_change:
            return None

        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        day_range = h - l
        if day_range <= 0:
            return None
        body = abs(c - o)
        body_ratio = body / day_range
        upper_shadow = h - max(o, c)
        if not is_limit_up:
            if body_ratio < params.min_body_to_range:
                return None
            if body > 0 and upper_shadow / body > params.max_upper_shadow_ratio:
                return None

        if vol_ratio < params.breakout_vol_ratio and not is_limit_up:
            return None

        if pd.isna(row["macd"]) or row["macd"] < params.macd_hist_min:
            return None
        if params.require_positive_macd_hist and row["macd"] <= 0:
            return None
        if row["dif"] < -0.01 * c:
            return None

        prev = df.iloc[idx - 1]
        macd_turn = (
            row["dif"] > row["dea"]
            or row["macd"] > prev["macd"]
            or (row["dif"] > 0 and row["macd"] > params.macd_hist_min)
        )
        if not macd_turn:
            return None

        if params.require_yang_line and row["close"] <= row["open"]:
            return None
        if params.require_ma5_up:
            ma5_up = row["ma5"] > df.iloc[idx - 5]["ma5"] if idx >= 5 else False
            if not ma5_up:
                return None

        breakout_pct = (c - washout_high) / washout_high * 100
        ma30 = float(row["ma30"]) if pd.notna(row["ma30"]) and row["ma30"] > 0 else c
        close_to_ma30 = c / ma30
        pull_v_pct = pullback * 100
        spread_v_pct = min_ma_spread * 100
        score = (
            float(row["macd"]) * 20
            + breakout_pct * 1.5
            + bull * 2.5
            + max(0.0, close_to_ma30 - 1.0) * 80
            + pull_v_pct * 1.5
            + vol_ratio * 3
            + (10.0 if is_limit_up else 0.0)
            + max(0.0, 5.0 - spread_v_pct) * 3
        )

        # 胜率优先模式严过滤
        if params.winrate_mode:
            if close_to_ma30 > params.wr_max_close_to_ma30:
                return None
            if min_ma_spread > params.wr_max_ma_spread_pct:
                return None
            if not (params.wr_min_day_change <= day_chg <= params.wr_max_day_change):
                return None
            if vol_ratio < params.wr_min_vol_ratio:
                return None
            if params.wr_require_macd_positive and float(row["macd"]) <= 0:
                return None
            if params.wr_exclude_limit_up and is_limit_up:
                return None

        return BreakoutResult(
            code=code,
            date=row["date"].strftime("%Y-%m-%d"),
            close=c,
            breakout_pct=breakout_pct,
            score=score,
            washout_high=washout_high,
            test_date=df.iloc[peak_idx]["date"].strftime("%Y-%m-%d"),
            pullback_pct=pullback * 100,
            vol_ratio=vol_ratio,
            ma_spread_pct=min_ma_spread * 100,
            macd=float(row["macd"]),
            dif=float(row["dif"]),
            bull_ma_count=bull,
            is_limit_up=is_limit_up,
            close_to_ma30=close_to_ma30,
            close_to_low60=c / low60 if low60 > 0 else 1.0,
            body_ratio=body_ratio,
            day_change_pct=day_chg * 100,
            extras={"peak_idx": peak_idx},
        )


def tier_of(score: float) -> str:
    if score >= 200:
        return "A"
    if score >= 130:
        return "B"
    if score >= 80:
        return "C"
    return "D"
