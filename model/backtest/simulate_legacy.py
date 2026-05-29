"""逐笔模拟（旧版手写实现）。

迁移自原 backtest.py 的 simulate_one：
- 次日开盘买入
- 触发：止盈 / 止损 / 分批止盈 / 跌破 MA10 / 持有到期
- 止损/离场遇「开盘跌停且全天无法卖出」时顺延至下一可卖日
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .limit_price import (
    count_consecutive_limit_down,
    is_limit_down_unsellable,
    prev_close_of,
)


@dataclass
class SimResult:
    executable: bool
    buy_price: float = 0.0
    buy_date: str = ""
    sell_price: float = 0.0
    sell_date: str = ""
    sell_reason: str = ""
    return_pct: float = 0.0
    max_up_pct: float = 0.0
    max_dn_pct: float = 0.0
    hold_days: int = 0


def resolve_stop_fill(open_px: float, high_px: float, low_px: float, stop_px: float) -> float | None:
    """止损触发时的 realistic 成交价（不含跌停顺延）。"""
    if low_px > stop_px:
        return None
    if open_px <= stop_px:
        return open_px
    return stop_px


def resolve_take_profit_fill(open_px: float, high_px: float, low_px: float, tp_px: float) -> float | None:
    """止盈触发时的 realistic 成交价。"""
    if high_px < tp_px:
        return None
    if open_px >= tp_px:
        return open_px
    return tp_px


def _bar_ohlc(row: pd.Series) -> tuple[float, float, float, float]:
    return float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])


def _can_sell_bar(
    df: pd.DataFrame,
    bar_idx: int,
    code: str | None,
    name: str | None = None,
) -> bool:
    o, h, l, c = _bar_ohlc(df.iloc[bar_idx])
    prev_c = prev_close_of(df, bar_idx)
    return not is_limit_down_unsellable(prev_c, o, h, l, c, code, name)


def _sell_at_open(
    df: pd.DataFrame,
    start_idx: int,
    end_limit: int,
    code: str | None,
    name: str | None = None,
) -> tuple[int, float, int] | None:
    """从 start_idx 起找第一个可卖出的交易日，按开盘价成交。返回 (idx, price, defer_days)。"""
    defer = 0
    for k in range(start_idx, min(len(df), end_limit + 1)):
        if not _can_sell_bar(df, k, code, name):
            defer += 1
            continue
        return k, float(df.iloc[k]["open"]), defer
    return None


def _sell_at_close(
    df: pd.DataFrame,
    start_idx: int,
    end_limit: int,
    code: str | None,
    name: str | None = None,
) -> tuple[int, float, int] | None:
    defer = 0
    for k in range(start_idx, min(len(df), end_limit + 1)):
        if not _can_sell_bar(df, k, code, name):
            defer += 1
            continue
        return k, float(df.iloc[k]["close"]), defer
    return None


def _defer_suffix(defer_days: int, df: pd.DataFrame, sell_idx: int, code: str | None, name: str | None) -> str:
    if defer_days <= 0:
        return ""
    streak = count_consecutive_limit_down(df, max(0, sell_idx - 1), code, name)
    if streak >= 2 or defer_days >= 2:
        return f"(连续跌停顺延{defer_days}日)"
    return f"(跌停顺延{defer_days}日)"


def simulate_one(
    df: pd.DataFrame,
    sig_idx: int,
    *,
    take_profit: float = 0.20,
    stop_loss: float = 0.07,
    max_hold: int = 20,
    split_tp: float | None = None,
    use_ma10_exit: bool = True,
    t_plus_1: bool = True,
    code: str | None = None,
    name: str | None = None,
    max_defer_days: int = 20,
) -> SimResult:
    """
    从信号次日开盘买入，逐日处理止盈/止损/破 MA10/到期。

    Args:
      code: 股票代码，用于涨跌幅限制
      name: 股票名称，用于 ST/*ST 识别（5% 限制）
      max_defer_days: 跌停无法卖出时最多顺延交易日数
    """
    n = len(df)
    buy_idx = sig_idx + 1
    if buy_idx >= n:
        return SimResult(executable=False)

    buy_row = df.iloc[buy_idx]
    buy_price = float(buy_row["open"])
    if buy_price <= 0:
        return SimResult(executable=False)

    if t_plus_1:
        base_end_idx = min(n - 1, buy_idx + max_hold)
        exit_start = buy_idx + 1
    else:
        base_end_idx = min(n - 1, sig_idx + max_hold)
        exit_start = buy_idx

    tp_full_px = buy_price * (1 + take_profit)
    sl_px = buy_price * (1 - stop_loss)
    tp_split_px = buy_price * (1 + split_tp) if split_tp else None

    high_peak = buy_price
    low_trough = buy_price
    split_filled = False
    split_fill_px = 0.0

    sell_price = float(df.iloc[base_end_idx]["close"])
    sell_idx = base_end_idx
    sell_reason = f"持有{max_hold}日到期"
    sold = False
    pending_stop = False
    defer_days = 0

    j = exit_start
    while j <= base_end_idx and j < n:
        r = df.iloc[j]
        o, h, l, c = _bar_ohlc(r)
        high_peak = max(high_peak, h)
        low_trough = min(low_trough, l)
        end_limit = min(n - 1, base_end_idx + max_defer_days)

        if pending_stop:
            if not _can_sell_bar(df, j, code, name):
                defer_days += 1
                j += 1
                if j > end_limit:
                    break
                continue
            sell_price = o
            sell_idx = j
            sell_reason = (
                f"止损 -{stop_loss * 100:.0f}%"
                + _defer_suffix(defer_days, df, sell_idx, code, name)
            )
            sold = True
            break

        sl_fill = resolve_stop_fill(o, h, l, sl_px)
        if sl_fill is not None:
            if not _can_sell_bar(df, j, code, name):
                pending_stop = True
                defer_days += 1
                j += 1
                continue
            sell_price = sl_fill
            sell_idx = j
            sell_reason = f"止损 -{stop_loss * 100:.0f}%"
            if o <= sl_px:
                sell_reason += "(低开)"
            sold = True
            break

        if tp_split_px and not split_filled and h >= tp_split_px:
            split_filled = True
            split_fill_px = resolve_take_profit_fill(o, h, l, tp_split_px) or tp_split_px

        tp_fill = resolve_take_profit_fill(o, h, l, tp_full_px)
        if tp_fill is not None:
            if not _can_sell_bar(df, j, code, name):
                hit = _sell_at_open(df, j + 1, end_limit, code, name)
                if hit is None:
                    break
                sell_idx, sell_price, extra = hit
                defer_days += extra
                sell_reason = (
                    f"止盈 +{take_profit * 100:.0f}%"
                    + _defer_suffix(defer_days, df, sell_idx, code, name)
                )
            else:
                sell_price = tp_fill
                sell_idx = j
                sell_reason = f"止盈 +{take_profit * 100:.0f}%"
                if o >= tp_full_px:
                    sell_reason += "(高开)"
            sold = True
            break

        ma10_min_idx = buy_idx + 1 if t_plus_1 else buy_idx + 2
        if (
            use_ma10_exit
            and pd.notna(r.get("ma10"))
            and c < float(r["ma10"]) * 0.99
            and j >= ma10_min_idx
        ):
            hit = _sell_at_open(df, j + 1, end_limit, code, name)
            if hit is not None:
                sell_idx, sell_price, extra = hit
                defer_days += extra
                sell_reason = "跌破 MA10" + _defer_suffix(defer_days, df, sell_idx, code, name)
                sold = True
            break

        j += 1

    if not sold:
        end_limit = min(n - 1, base_end_idx + max_defer_days)
        hit = _sell_at_close(df, base_end_idx, end_limit, code, name)
        if hit is not None:
            sell_idx, sell_price, extra = hit
            defer_days += extra
            sell_reason = (
                f"持有{max_hold}日到期"
                + _defer_suffix(defer_days, df, sell_idx, code, name)
            )
        else:
            sell_idx = min(n - 1, end_limit)
            sell_price = float(df.iloc[sell_idx]["close"])
            sell_reason = f"持有{max_hold}日到期(强制)"

    if split_filled:
        final_ret = (
            0.5 * (split_fill_px - buy_price) / buy_price
            + 0.5 * (sell_price - buy_price) / buy_price
        )
        sell_reason = f"分批: 半仓+{split_tp * 100:.0f}% / 半仓{sell_reason}"  # type: ignore[union-attr]
    else:
        final_ret = (sell_price - buy_price) / buy_price
    max_up = (high_peak - buy_price) / buy_price
    max_dn = (low_trough - buy_price) / buy_price

    return SimResult(
        executable=True,
        buy_price=buy_price,
        buy_date=buy_row["date"].strftime("%Y-%m-%d"),
        sell_price=float(sell_price),
        sell_date=df.iloc[sell_idx]["date"].strftime("%Y-%m-%d"),
        sell_reason=sell_reason,
        return_pct=final_ret * 100,
        max_up_pct=max_up * 100,
        max_dn_pct=max_dn * 100,
        hold_days=sell_idx - sig_idx,
    )
