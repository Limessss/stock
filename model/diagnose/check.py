"""个股诊断：把策略每条规则的判定结果以结构化数据返回，前端用于展示 PASS/FAIL 列表。

不依赖打印输出；逐条规则收集 (name, status, value, threshold, note)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..data.indicators import add_indicators, bull_ma_count
from ..strategies.breakout_washout import (
    BreakoutParams,
    BreakoutWashoutStrategy,
    _find_washout_high,
)


@dataclass
class RuleResult:
    name: str          # 规则中文名
    status: str        # "pass" | "fail" | "warn" | "skip"
    value: Any = None  # 实际数值（数字或字符串）
    threshold: Any = None
    note: str = ""


@dataclass
class DiagnoseReport:
    code: str
    date: str
    close: float
    indicators: dict[str, float]
    rules: list[RuleResult]
    final_status: str       # "pass" | "fail"
    score: float | None = None


def _ok(name: str, value, threshold, *, op: str = ">=", note: str = "") -> RuleResult:
    """对比 value 与 threshold，返回 PASS/FAIL；支持 op = >=/<=/==/range。"""
    if op == ">=":
        passed = value is not None and value >= threshold
    elif op == "<=":
        passed = value is not None and value <= threshold
    elif op == "==":
        passed = value == threshold
    elif op == "range":
        lo, hi = threshold
        passed = value is not None and lo <= value <= hi
    else:
        raise ValueError(f"unknown op: {op}")
    return RuleResult(name, "pass" if passed else "fail", value=value, threshold=threshold, note=note)


def diagnose_breakout(
    code: str,
    df: pd.DataFrame,
    *,
    target_date: pd.Timestamp | None = None,
    params: BreakoutParams | None = None,
) -> DiagnoseReport:
    """对单股 + 单交易日，逐条评估 BreakoutWashoutStrategy 的规则。"""
    params = params or BreakoutParams()
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

    # ----- 0. 历史长度 -----
    rules.append(_ok("历史交易日 ≥", idx + 1, params.min_history, op=">="))

    # ----- 1. 洗盘高点定位 -----
    found = _find_washout_high(df, idx, params)
    if found is None:
        rules.append(RuleResult("洗盘高点定位", "fail", note="窗口内未找到符合条件的高点"))
        return _finalize(code_u, row, df, idx, rules, params, found)
    washout_high, peak_idx, pullback = found
    rules.append(RuleResult(
        "洗盘高点定位", "pass",
        value=f"试盘日 {df.iloc[peak_idx]['date'].date()} 高点 {washout_high:.2f}",
        note=f"回撤 {pullback*100:.2f}%",
    ))

    # ----- 2. 突破 -----
    c = float(row["close"])
    breakout_pct = (c - washout_high) / washout_high * 100
    rules.append(_ok("突破幅度 ≥", round(breakout_pct, 2), params.min_breakout_pct * 100, op=">="))
    rules.append(_ok("收盘/洗盘高点 ≤", round(c / washout_high, 3),
                     params.max_close_over_washout, op="<="))

    # ----- 3. 起爆点 -----
    if pd.notna(row["ma30"]) and row["ma30"] > 0:
        rules.append(_ok("close/MA30 ≤", round(c / float(row["ma30"]), 3),
                         params.max_close_ma30_ratio, op="<="))
    low60 = float(df.iloc[max(0, idx - 60): idx]["low"].min())
    if low60 > 0:
        rules.append(_ok("close/60日低 ≤", round(c / low60, 3),
                         params.max_close_low60_ratio, op="<="))

    # ----- 4. 均线 -----
    bull = bull_ma_count(row)
    rules.append(_ok("多头组数 ≥", bull, params.min_ma_bull_count, op=">="))
    if params.close_above_ma20:
        rules.append(_ok("收盘 ≥ MA20", c, round(float(row["ma20"]), 2) if pd.notna(row["ma20"]) else None,
                         op=">="))

    # ----- 5. 量价 -----
    vol_ma5 = row.get("vol_ma5")
    if pd.notna(vol_ma5) and vol_ma5 > 0:
        vol_ratio = float(row["volume"] / vol_ma5)
        rules.append(_ok("量比5 ≥", round(vol_ratio, 2), params.breakout_vol_ratio, op=">="))
    else:
        rules.append(RuleResult("量比5 ≥", "skip", note="vol_ma5 缺失"))

    # ----- 6. K 线形态 -----
    prev_close = float(df.iloc[idx - 1]["close"])
    day_chg = (c - prev_close) / prev_close if prev_close > 0 else 0
    is_limit_up = day_chg >= 0.095
    rules.append(_ok("当日涨幅 ≥", round(day_chg * 100, 2), params.min_day_change * 100, op=">="))
    o, h, l = float(row["open"]), float(row["high"]), float(row["low"])
    day_range = max(h - l, 1e-9)
    body = abs(c - o)
    body_ratio = body / day_range
    if not is_limit_up:
        rules.append(_ok("实体/振幅 ≥", round(body_ratio, 2), params.min_body_to_range, op=">="))
        if body > 0:
            us_ratio = (h - max(o, c)) / body
            rules.append(_ok("上影/实体 ≤", round(us_ratio, 2), params.max_upper_shadow_ratio, op="<="))
    else:
        rules.append(RuleResult("K 线形态", "skip", note="涨停板豁免"))

    # ----- 7. MACD -----
    macd = float(row["macd"]) if pd.notna(row["macd"]) else None
    if macd is not None:
        if params.require_positive_macd_hist:
            rules.append(_ok("MACD柱 > 0", round(macd, 4), 0, op=">="))
        else:
            rules.append(_ok("MACD柱 ≥", round(macd, 4), params.macd_hist_min, op=">="))

    # ----- 8. 最终 -----
    final_pass = all(r.status == "pass" for r in rules if r.status != "skip")

    # 调用策略本身确认是否能产生 ScanResult，并取出 score
    strategy = BreakoutWashoutStrategy(params)
    res = strategy.scan(code_u, df, row["date"], indicators_ready=True)
    score = res.score if res is not None else None

    return DiagnoseReport(
        code=code_u,
        date=str(row["date"].date()),
        close=c,
        indicators={
            "ma5": _f(row.get("ma5")),
            "ma10": _f(row.get("ma10")),
            "ma20": _f(row.get("ma20")),
            "ma30": _f(row.get("ma30")),
            "ma60": _f(row.get("ma60")),
            "dif": _f(row.get("dif")),
            "dea": _f(row.get("dea")),
            "macd": _f(row.get("macd")),
        },
        rules=rules,
        final_status="pass" if (final_pass and res is not None) else "fail",
        score=round(score, 2) if score is not None else None,
    )


def _finalize(code, row, df, idx, rules, params, found):
    return DiagnoseReport(
        code=code,
        date=str(row["date"].date()),
        close=float(row["close"]),
        indicators={},
        rules=rules,
        final_status="fail",
        score=None,
    )


def _f(v) -> float | None:
    if v is None or (isinstance(v, float) and (np.isnan(v))):
        return None
    return round(float(v), 4)
