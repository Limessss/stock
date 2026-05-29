"""A 股涨跌停价与卖出可成交性（回测用）。

规则要点：
- ST/*ST：±5%；主板 ±10%；创业板/科创板 ±20%；北交所 ±30%
- 名称缺失时，可按当日涨跌幅反推限制（近似识别 ST）
- 连续一字跌停：每日跌停价 = 前收 × (1 - limit_pct)，逐日顺延卖出
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

_ST_PREFIX = re.compile(r"^(S\*ST|SST|\*ST|ST)")


@dataclass(frozen=True)
class LimitContext:
    code: str | None = None
    name: str | None = None


def normalize_code(code: str | None) -> str:
    if not code:
        return ""
    return code.upper().replace("SH", "").replace("SZ", "").strip()


def is_st_name(name: str | None) -> bool:
    if not name:
        return False
    return bool(_ST_PREFIX.match(name.strip()))


def board_limit_pct(code: str | None) -> float:
    """板块默认涨跌幅（非 ST）。"""
    digits = normalize_code(code)
    if not digits:
        return 0.10
    if digits.startswith(("688", "300", "301")):
        return 0.20
    if digits.startswith(("83", "87", "43", "82", "88", "920")):
        return 0.30
    return 0.10


def _infer_limit_pct_from_change(prev_close: float, ref_px: float) -> float | None:
    """从实际涨跌幅反推限制（用于无名称时的 ST 识别）。"""
    if prev_close <= 0:
        return None
    chg = (ref_px - prev_close) / prev_close
    candidates = (0.05, 0.10, 0.20, 0.30)
    for pct in candidates:
        if abs(abs(chg) - pct) < 0.012:
            return pct
    return None


def limit_pct(
    code: str | None = None,
    name: str | None = None,
    *,
    prev_close: float | None = None,
    ref_px: float | None = None,
) -> float:
    """涨跌幅限制。ST 优先；否则按板块；名称缺失时可按价格变动推断。"""
    if is_st_name(name):
        return 0.05
    base = board_limit_pct(code)
    if prev_close is not None and ref_px is not None:
        inferred = _infer_limit_pct_from_change(prev_close, ref_px)
        if inferred is not None and inferred < base:
            return inferred
    return base


def price_tol(prev_close: float) -> float:
    return max(0.01, round(prev_close * 0.001, 4))


def limit_down_price(
    prev_close: float,
    code: str | None = None,
    name: str | None = None,
    *,
    ref_px: float | None = None,
) -> float:
    if prev_close <= 0:
        return 0.0
    pct = limit_pct(code, name, prev_close=prev_close, ref_px=ref_px or prev_close)
    return round(prev_close * (1 - pct), 2)


def limit_up_price(
    prev_close: float,
    code: str | None = None,
    name: str | None = None,
    *,
    ref_px: float | None = None,
) -> float:
    if prev_close <= 0:
        return 0.0
    pct = limit_pct(code, name, prev_close=prev_close, ref_px=ref_px or prev_close)
    return round(prev_close * (1 + pct), 2)


def prev_close_of(df: pd.DataFrame, bar_idx: int) -> float:
    if bar_idx <= 0:
        return float(df.iloc[0]["close"])
    return float(df.iloc[bar_idx - 1]["close"])


def is_one_word_limit_down(
    prev_close: float,
    open_px: float,
    high_px: float,
    low_px: float,
    close_px: float,
    code: str | None = None,
    name: str | None = None,
) -> bool:
    """一字/封死跌停：全天最高价未打开跌停价。"""
    if prev_close <= 0:
        return False
    ref = close_px if close_px > 0 else open_px
    ld = limit_down_price(prev_close, code, name, ref_px=ref)
    if ld <= 0:
        return False
    tol = price_tol(prev_close)
    if open_px > ld + tol:
        return False
    return high_px <= ld + tol


def is_limit_down_unsellable(
    prev_close: float,
    open_px: float,
    high_px: float,
    low_px: float,
    close_px: float,
    code: str | None = None,
    name: str | None = None,
) -> bool:
    """无法有效卖出：一字跌停，或开盘在跌停附近且收盘仍封跌停。"""
    if prev_close <= 0:
        return False
    ref = close_px if close_px > 0 else open_px
    ld = limit_down_price(prev_close, code, name, ref_px=ref)
    if ld <= 0:
        return False
    tol = price_tol(prev_close)

    if is_one_word_limit_down(prev_close, open_px, high_px, low_px, close_px, code, name):
        return True

    # 曾短暂打开但收在跌停：排队卖不出，顺延
    if open_px <= ld + tol and close_px <= ld + tol and high_px <= ld + tol * 2:
        return True

    return False


def count_consecutive_limit_down(
    df: pd.DataFrame,
    bar_idx: int,
    code: str | None = None,
    name: str | None = None,
) -> int:
    """截至 bar_idx（含）连续一字跌停天数。"""
    streak = 0
    for k in range(bar_idx, -1, -1):
        if k <= 0:
            break
        prev_c = prev_close_of(df, k)
        o, h, l, c = (
            float(df.iloc[k]["open"]),
            float(df.iloc[k]["high"]),
            float(df.iloc[k]["low"]),
            float(df.iloc[k]["close"]),
        )
        if is_one_word_limit_down(prev_c, o, h, l, c, code, name):
            streak += 1
        else:
            break
    return streak
