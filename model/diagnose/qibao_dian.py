"""起爆点策略个股诊断（全量规则评估，与洗盘突破诊断一致）。"""
from __future__ import annotations

import pandas as pd

from ..data.indicators import add_indicators
from ..strategies.qibao_dian import (
    QibaoDianParams,
    QibaoDianStrategy,
    _avg,
    _pct,
)
from .check import DiagnoseReport, RuleResult, _f, _ok

_DOWNSTREAM_RULES = (
    "试盘高点定位",
    "洗盘天数",
    "突破幅度",
    "昨收未提前突破",
    "试盘涨幅 ≥",
    "回踩幅度",
    "均线数据",
    "均线多头结构",
    "均线离散度 ≤",
    "MA20/MA30 上行",
    "洗盘低点抬升",
    "量能均值",
    "放量确认",
    "缩量比 ≤",
    "试盘活跃度",
    "策略综合命中",
)


def _append_skips(rules: list[RuleResult], note: str) -> None:
    existing = {r.name for r in rules}
    for name in _DOWNSTREAM_RULES:
        if name not in existing:
            rules.append(RuleResult(name, "skip", note=note))


def _indicators(row: pd.Series) -> dict[str, float | None]:
    return {
        "ma5": _f(row.get("ma5")),
        "ma10": _f(row.get("ma10")),
        "ma20": _f(row.get("ma20")),
        "ma30": _f(row.get("ma30")),
        "ma60": _f(row.get("ma60")),
        "dif": _f(row.get("dif")),
        "dea": _f(row.get("dea")),
        "macd": _f(row.get("macd")),
    }


def _finalize(
    code_u: str,
    row: pd.Series,
    rules: list[RuleResult],
    indicators: dict[str, float | None],
    params: QibaoDianParams,
    df: pd.DataFrame,
) -> DiagnoseReport:
    final_pass = all(r.status == "pass" for r in rules if r.status != "skip")
    strategy = QibaoDianStrategy(params)
    res = strategy.scan(code_u, df, row["date"], indicators_ready=True)
    if "策略综合命中" not in {r.name for r in rules}:
        if res is not None:
            rules.append(
                RuleResult(
                    "策略综合命中",
                    "pass",
                    value=f"模式 {res.mode}",
                    note=f"评分 {res.score:.2f}",
                )
            )
        else:
            rules.append(RuleResult("策略综合命中", "fail", note="策略 scan 未命中"))
    score = round(res.score, 2) if res is not None else None
    return DiagnoseReport(
        code=code_u,
        date=str(row["date"].date()),
        close=float(row["close"]),
        indicators=indicators,
        rules=rules,
        final_status="pass" if (final_pass and res is not None) else "fail",
        score=score,
    )


def diagnose_qibao_dian(
    code: str,
    df: pd.DataFrame,
    *,
    target_date: pd.Timestamp | None = None,
    params: QibaoDianParams | None = None,
) -> DiagnoseReport:
    params = params or QibaoDianParams()
    df = add_indicators(df)
    if target_date is not None:
        mask = df["date"] == target_date
        if not mask.any():
            raise ValueError(f"date not in data: {target_date}")
        idx = int(df.index[mask][0])
    else:
        idx = len(df) - 1

    row = df.iloc[idx]
    code_u = code.upper()
    rules: list[RuleResult] = []
    indicators = _indicators(row)

    rules.append(_ok("历史交易日 ≥", idx + 1, params.min_history, op=">="))
    if idx + 1 < params.min_history:
        _append_skips(rules, "历史数据不足，后续规则跳过")
        return _finalize(code_u, row, rules, indicators, params, df)

    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    vols = df["volume"].tolist()

    today_close = closes[idx]
    yesterday_close = closes[idx - 1]
    is_yang = today_close > yesterday_close
    rules.append(
        RuleResult(
            "当日收阳",
            "pass" if is_yang else "fail",
            value=round(today_close, 2),
            threshold=round(yesterday_close, 2),
            note="收盘需高于昨收",
        )
    )

    start = max(0, idx - params.max_wash_days - 45)
    end = idx - params.min_wash_days
    if start > end:
        rules.append(RuleResult("试盘搜索窗口", "fail", note="可用搜索区间为空"))
        _append_skips(rules, "试盘窗口无效，后续规则跳过")
        return _finalize(code_u, row, rules, indicators, params, df)

    test_idx = max(range(start, end + 1), key=lambda x: highs[x])
    test_high = highs[test_idx]
    test_date = df.iloc[test_idx]["date"].strftime("%Y-%m-%d")
    wash_start = test_idx + 1
    wash_end = idx - 1
    wash_days = wash_end - wash_start + 1

    rules.append(
        RuleResult(
            "试盘高点定位",
            "pass",
            value=f"试盘日 {test_date} 高点 {test_high:.2f}",
            note=f"洗盘 {wash_days} 日",
        )
    )

    strong_wash_ok = params.enable_strong_breakout and wash_days >= params.strong_min_wash_days
    wash_days_ok = (
        wash_days >= params.min_wash_days or strong_wash_ok
    ) and wash_days <= params.max_wash_days
    rules.append(
        RuleResult(
            "洗盘天数",
            "pass" if wash_days_ok else "fail",
            value=wash_days,
            threshold=f"{params.min_wash_days}~{params.max_wash_days}",
            note="强势分支可放宽最少天数" if params.enable_strong_breakout else "",
        )
    )

    breakout_pct_ratio = _pct(today_close, test_high)
    pct_chg = _pct(today_close, yesterday_close)
    today_high = highs[idx]
    today_low = lows[idx]
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

    break_ok = breakout_pct_ratio >= params.min_break_pct and (
        breakout_pct_ratio <= params.max_break_pct or strong_price_action
    )
    rules.append(
        RuleResult(
            "突破幅度",
            "pass" if break_ok else "fail",
            value=round(breakout_pct_ratio * 100, 2),
            threshold=f"{params.min_break_pct * 100:.1f}%~{params.max_break_pct * 100:.1f}%",
            note="强势分支可放宽上限",
        )
    )

    pre_break_ok = not (
        yesterday_close >= test_high * (1.0 + params.min_break_pct * 0.5) and not strong_price_action
    )
    rules.append(
        RuleResult(
            "昨收未提前突破",
            "pass" if pre_break_ok else "fail",
            value=round(yesterday_close, 2),
            threshold=round(test_high * (1.0 + params.min_break_pct * 0.5), 2),
        )
    )

    base_start = max(0, test_idx - 45)
    base_low = min(lows[base_start : test_idx + 1])
    probe_gain = _pct(test_high, base_low)
    rules.append(_ok("试盘涨幅 ≥", round(probe_gain * 100, 2), params.min_probe_gain * 100, op=">="))

    wash_low = min(lows[wash_start:idx]) if wash_start <= idx - 1 else test_high
    pullback_pct_ratio = _pct(test_high, wash_low)
    rules.append(
        _ok(
            "回踩幅度",
            round(pullback_pct_ratio * 100, 2),
            (params.min_pullback_pct * 100, params.max_pullback_pct * 100),
            op="range",
        )
    )

    ma5, ma10, ma20, ma30, ma60 = row.get("ma5"), row.get("ma10"), row.get("ma20"), row.get("ma30"), row.get("ma60")
    ma_missing = any(pd.isna(v) for v in (ma5, ma10, ma20, ma30, ma60))
    if ma_missing:
        rules.append(RuleResult("均线数据", "fail", note="MA5/10/20/30/60 存在缺失"))
        _append_skips(rules, "均线数据缺失，后续规则跳过")
        return _finalize(code_u, row, rules, indicators, params, df)
    rules.append(RuleResult("均线数据", "pass"))
    ma5, ma10, ma20, ma30, ma60 = float(ma5), float(ma10), float(ma20), float(ma30), float(ma60)

    ma_struct_ok = (
        today_close > ma5 > ma10 * 0.97
        and today_close > ma20
        and today_close > ma30
        and today_close > ma60
    )
    rules.append(
        RuleResult(
            "均线多头结构",
            "pass" if ma_struct_ok else "fail",
            value=round(today_close / ma30, 3) if ma30 else None,
            note="收盘需站上均线组且 MA5>MA10",
        )
    )

    ma_values = [ma5, ma10, ma20, ma30, ma60]
    ma_spread = max(ma_values) / min(ma_values) - 1.0
    spread_ok = ma_spread <= params.max_ma_spread or (
        strong_price_action and ma_spread <= params.strong_max_ma_spread
    )
    rules.append(
        RuleResult(
            "均线离散度 ≤",
            "pass" if spread_ok else "fail",
            value=round(ma_spread * 100, 2),
            threshold=round(params.max_ma_spread * 100, 2),
            note="强势分支上限更宽",
        )
    )

    if idx < 5:
        rules.append(RuleResult("MA20/MA30 上行", "fail", note="历史不足 5 日"))
    else:
        ma20_5d = df.iloc[idx - 5].get("ma20")
        ma30_5d = df.iloc[idx - 5].get("ma30")
        slope_ok = not (
            pd.isna(ma20_5d)
            or pd.isna(ma30_5d)
            or ma20 < float(ma20_5d) * 0.995
            or ma30 < float(ma30_5d) * 0.995
        )
        rules.append(RuleResult("MA20/MA30 上行", "pass" if slope_ok else "fail"))

    if wash_start <= idx - 1:
        last_wash_low = min(lows[max(wash_start, idx - 12) : idx])
        early_wash_low = min(lows[wash_start : min(idx, wash_start + max(3, wash_days // 2))])
        wash_shape_ok = last_wash_low >= early_wash_low * 0.94
        rules.append(
            RuleResult(
                "洗盘低点抬升",
                "pass" if wash_shape_ok else "fail",
                value=round(last_wash_low, 2),
                threshold=round(early_wash_low * 0.94, 2),
            )
        )
    else:
        rules.append(RuleResult("洗盘低点抬升", "fail", note="无有效洗盘区间"))

    vol20_prev = _avg(vols, idx - 20, idx - 1)
    test_vol = _avg(vols, max(test_idx - 1, 0), min(test_idx + 1, idx - 1))
    late_wash_vol = _avg(vols, max(wash_start, idx - 8), idx - 1)
    if not vol20_prev or not test_vol or not late_wash_vol:
        rules.append(RuleResult("量能均值", "fail", note="vol20/试盘/洗盘均量计算失败"))
        _append_skips(rules, "量能数据不足，后续规则跳过")
        return _finalize(code_u, row, rules, indicators, params, df)
    rules.append(RuleResult("量能均值", "pass"))

    vol_ratio_today = vols[idx] / vol20_prev if vol20_prev else 0.0
    vol_shrink_ratio = late_wash_vol / test_vol if test_vol else 999.0
    strong_breakout = (
        strong_price_action
        and vol_ratio_today >= params.strong_min_vol_ratio
        and ma_spread <= params.strong_max_ma_spread
        and vol_shrink_ratio <= params.strong_max_shrink_ratio
    )

    release_start = max(wash_start, idx - params.release_lookback)
    release_end = idx - 1
    release_vol_ratio = 0.0
    if release_start <= release_end:
        for j in range(release_start, release_end + 1):
            vavg = _avg(vols, j - 20, j - 1)
            if not vavg:
                continue
            ratio = vols[j] / vavg
            high_to_test = highs[j] / test_high
            if high_to_test >= params.min_release_high_to_test and ratio > release_vol_ratio:
                release_vol_ratio = ratio

    vol_confirm_ok = (
        vol_ratio_today >= params.min_today_vol_ratio
        or release_vol_ratio >= params.min_release_vol_ratio
        or strong_breakout
    )
    rules.append(
        RuleResult(
            "放量确认",
            "pass" if vol_confirm_ok else "fail",
            value=f"当日量比 {vol_ratio_today:.2f} / 释放量比 {release_vol_ratio:.2f}",
            threshold=f"≥{params.min_today_vol_ratio} 或 ≥{params.min_release_vol_ratio}",
        )
    )

    shrink_ok = vol_shrink_ratio <= params.max_shrink_ratio or strong_breakout
    rules.append(
        RuleResult(
            "缩量比 ≤",
            "pass" if shrink_ok else "fail",
            value=round(vol_shrink_ratio, 3),
            threshold=params.max_shrink_ratio,
        )
    )

    test_avg20 = _avg(vols, test_idx - 20, test_idx - 1)
    activity_ok = not (
        test_avg20 and test_vol < test_avg20 * params.min_test_activity and not strong_breakout
    )
    rules.append(
        RuleResult(
            "试盘活跃度",
            "pass" if activity_ok else "fail",
            value=round(test_vol / test_avg20, 3) if test_avg20 else None,
            threshold=params.min_test_activity,
        )
    )

    return _finalize(code_u, row, rules, indicators, params, df)
