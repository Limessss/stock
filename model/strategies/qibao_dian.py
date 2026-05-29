"""起爆点策略：前期试盘高点 → 缩量洗盘 → 放量突破。

迁移自 Codex find_wash_breakout.py 的 scan_one 实现，逻辑保持一致。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..data.indicators import add_indicators
from .base import ScanResult, Strategy


@dataclass
class QibaoDianParams:
    min_history: int = 90
    min_wash_days: int = 5
    max_wash_days: int = 65
    min_break_pct: float = 0.005
    max_break_pct: float = 0.18
    min_probe_gain: float = 0.12
    min_pullback_pct: float = 0.035
    max_pullback_pct: float = 0.55
    max_ma_spread: float = 0.22
    min_today_vol_ratio: float = 1.25
    release_lookback: int = 20
    min_release_vol_ratio: float = 1.80
    min_release_high_to_test: float = 0.90
    max_shrink_ratio: float = 1.00
    min_test_activity: float = 0.90
    enable_strong_breakout: bool = True
    strong_min_wash_days: int = 3
    strong_min_pct_chg: float = 0.08
    strong_min_break_pct: float = 0.06
    strong_max_break_pct: float = 0.30
    strong_min_vol_ratio: float = 0.80
    strong_max_ma_spread: float = 0.75
    strong_max_shrink_ratio: float = 1.80
    strong_min_close_pos: float = 0.70


@dataclass
class QibaoDianResult(ScanResult):
    washout_high: float = 0.0
    test_date: str = ""
    wash_days: int = 0
    pullback_pct: float = 0.0
    vol_ratio: float = 0.0
    ma_spread_pct: float = 0.0
    release_date: str = ""
    release_vol_ratio: float = 0.0
    release_high_to_test: float = 0.0
    vol_shrink_ratio: float = 0.0
    mode: str = "normal"
    day_change_pct: float = 0.0
    close_to_ma30: float = 1.0
    is_limit_up: bool = False


def _pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b - 1.0


def _avg(values: list[float], start: int, end: int) -> float | None:
    start = max(0, start)
    end = min(len(values) - 1, end)
    if start > end:
        return None
    chunk = values[start : end + 1]
    if not chunk:
        return None
    return sum(chunk) / len(chunk)


def _scan_one(
    df: pd.DataFrame,
    i: int,
    params: QibaoDianParams,
) -> QibaoDianResult | None:
    """核心扫描逻辑，与 find_wash_breakout.scan_one 一致。"""
    if i < params.min_history:
        return None

    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    vols = df["volume"].tolist()

    today_close = closes[i]
    yesterday_close = closes[i - 1]
    if today_close <= yesterday_close:
        return None

    start = max(0, i - params.max_wash_days - 45)
    end = i - params.min_wash_days
    if start > end:
        return None

    test_idx = max(range(start, end + 1), key=lambda x: highs[x])
    test_high = highs[test_idx]
    wash_start = test_idx + 1
    wash_end = i - 1
    wash_days = wash_end - wash_start + 1
    if (
        wash_days < params.min_wash_days
        and not (params.enable_strong_breakout and wash_days >= params.strong_min_wash_days)
    ) or wash_days > params.max_wash_days:
        return None

    breakout_pct_ratio = _pct(today_close, test_high)
    pct_chg = _pct(today_close, yesterday_close)
    today_high = highs[i]
    today_low = lows[i]
    day_range = today_high - today_low
    close_pos = (today_close - today_low) / day_range if day_range > 0 else 1.0
    strong_price_action = (
        params.enable_strong_breakout
        and wash_days >= params.strong_min_wash_days
        and pct_chg >= params.strong_min_pct_chg
        and breakout_pct_ratio >= params.strong_min_break_pct
        and breakout_pct_ratio <= params.strong_max_break_pct
        and close_pos >= params.strong_min_close_pos
    )
    if breakout_pct_ratio < params.min_break_pct or (
        breakout_pct_ratio > params.max_break_pct and not strong_price_action
    ):
        return None
    if yesterday_close >= test_high * (1.0 + params.min_break_pct * 0.5) and not strong_price_action:
        return None

    base_start = max(0, test_idx - 45)
    base_low = min(lows[base_start : test_idx + 1])
    probe_gain = _pct(test_high, base_low)
    if probe_gain < params.min_probe_gain:
        return None

    wash_low = min(lows[wash_start : i])
    pullback_pct_ratio = _pct(test_high, wash_low)
    if pullback_pct_ratio < params.min_pullback_pct or pullback_pct_ratio > params.max_pullback_pct:
        return None

    row = df.iloc[i]
    ma5 = row.get("ma5")
    ma10 = row.get("ma10")
    ma20 = row.get("ma20")
    ma30 = row.get("ma30")
    ma60 = row.get("ma60")
    if any(pd.isna(v) for v in (ma5, ma10, ma20, ma30, ma60)):
        return None
    ma5, ma10, ma20, ma30, ma60 = float(ma5), float(ma10), float(ma20), float(ma30), float(ma60)

    if not (
        today_close > ma5 > ma10 * 0.97
        and today_close > ma20
        and today_close > ma30
        and today_close > ma60
    ):
        return None

    ma_values = [ma5, ma10, ma20, ma30, ma60]
    ma_spread = max(ma_values) / min(ma_values) - 1.0
    if ma_spread > params.max_ma_spread and not (
        strong_price_action and ma_spread <= params.strong_max_ma_spread
    ):
        return None

    if i < 5:
        return None
    ma20_5d = df.iloc[i - 5].get("ma20")
    ma30_5d = df.iloc[i - 5].get("ma30")
    if (
        pd.isna(ma20_5d)
        or pd.isna(ma30_5d)
        or ma20 < float(ma20_5d) * 0.995
        or ma30 < float(ma30_5d) * 0.995
    ):
        return None

    last_wash_low = min(lows[max(wash_start, i - 12) : i])
    early_wash_low = min(lows[wash_start : min(i, wash_start + max(3, wash_days // 2))])
    if last_wash_low < early_wash_low * 0.94:
        return None

    vol20_prev = _avg(vols, i - 20, i - 1)
    test_vol = _avg(vols, max(test_idx - 1, 0), min(test_idx + 1, i - 1))
    late_wash_vol = _avg(vols, max(wash_start, i - 8), i - 1)
    if not vol20_prev or not test_vol or not late_wash_vol:
        return None

    vol_ratio_today = vols[i] / vol20_prev if vol20_prev else 0.0
    vol_shrink_ratio = late_wash_vol / test_vol if test_vol else 999.0
    strong_breakout = (
        strong_price_action
        and vol_ratio_today >= params.strong_min_vol_ratio
        and ma_spread <= params.strong_max_ma_spread
        and vol_shrink_ratio <= params.strong_max_shrink_ratio
    )

    release_start = max(wash_start, i - params.release_lookback)
    release_end = i - 1
    release_idx = -1
    release_vol_ratio = 0.0
    release_high_to_test = 0.0
    if release_start <= release_end:
        for j in range(release_start, release_end + 1):
            vavg = _avg(vols, j - 20, j - 1)
            if not vavg:
                continue
            ratio = vols[j] / vavg
            high_to_test = highs[j] / test_high
            if high_to_test >= params.min_release_high_to_test and ratio > release_vol_ratio:
                release_idx = j
                release_vol_ratio = ratio
                release_high_to_test = high_to_test

    has_volume_confirmation = (
        vol_ratio_today >= params.min_today_vol_ratio
        or release_vol_ratio >= params.min_release_vol_ratio
        or strong_breakout
    )
    if not has_volume_confirmation:
        return None
    if vol_shrink_ratio > params.max_shrink_ratio and not strong_breakout:
        return None

    test_avg20 = _avg(vols, test_idx - 20, test_idx - 1)
    if test_avg20 and test_vol < test_avg20 * params.min_test_activity and not strong_breakout:
        return None

    mode = "strong" if strong_breakout else "normal"
    score = (
        breakout_pct_ratio * 100
        + min(vol_ratio_today, 4.0) * 8
        + min(release_vol_ratio, 4.0) * 3
        + max(0.0, 1.0 - vol_shrink_ratio) * 12
        + max(0.0, 0.18 - ma_spread) * 60
        + (8 if strong_breakout else 0)
        - max(0.0, pullback_pct_ratio - 0.25) * 20
    )

    is_limit_up = pct_chg >= 0.095
    close_to_ma30 = today_close / ma30 if ma30 > 0 else 1.0
    test_date_str = df.iloc[test_idx]["date"].strftime("%Y-%m-%d")
    release_date_str = (
        df.iloc[release_idx]["date"].strftime("%Y-%m-%d") if release_idx >= 0 else ""
    )

    return QibaoDianResult(
        code="",
        date=row["date"].strftime("%Y-%m-%d"),
        close=today_close,
        breakout_pct=breakout_pct_ratio * 100,
        score=score,
        washout_high=test_high,
        test_date=test_date_str,
        wash_days=wash_days,
        pullback_pct=pullback_pct_ratio * 100,
        vol_ratio=vol_ratio_today,
        ma_spread_pct=ma_spread * 100,
        release_date=release_date_str,
        release_vol_ratio=release_vol_ratio,
        release_high_to_test=release_high_to_test,
        vol_shrink_ratio=vol_shrink_ratio,
        mode=mode,
        day_change_pct=pct_chg * 100,
        close_to_ma30=close_to_ma30,
        is_limit_up=is_limit_up,
        extras={"test_idx": test_idx, "release_idx": release_idx},
    )


class QibaoDianStrategy(Strategy):
    name = "qibao_dian"
    label = "起爆点"
    params_cls = QibaoDianParams
    description = (
        "识别「前期试盘高点 → 缩量洗盘 → 放量突破」的起爆形态，"
        "强调试盘涨幅、洗盘结构与放量确认。"
    )
    features = (
        "动态搜索试盘高点并统计洗盘天数",
        "校验突破幅度、回踩幅度与均线多头结构",
        "支持强势突破分支放宽部分阈值",
        "结合当日量比与释放日放量确认信号",
    )
    tier_rules = (
        "A：评分 ≥ 60",
        "B：评分 ≥ 45",
        "C：评分 ≥ 30",
        "D：评分 < 30",
    )

    def scan(
        self,
        code: str,
        df: pd.DataFrame,
        target_date: pd.Timestamp | None = None,
        indicators_ready: bool = False,
    ) -> QibaoDianResult | None:
        params: QibaoDianParams = self.params  # type: ignore[assignment]
        if not indicators_ready:
            df = add_indicators(df)
        if target_date is not None:
            mask = df["date"] == target_date
            if not mask.any():
                return None
            idx = int(df.index[mask][0])
        else:
            idx = len(df) - 1

        result = _scan_one(df, idx, params)
        if result is None:
            return None
        return QibaoDianResult(
            **{**result.__dict__, "code": code},
        )


def tier_of(score: float) -> str:
    """起爆点评分分级（与 breakout_washout 量纲不同）。"""
    if score >= 60:
        return "A"
    if score >= 45:
        return "B"
    if score >= 30:
        return "C"
    return "D"
