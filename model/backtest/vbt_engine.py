"""VectorBT 单笔模拟实现。

与 simulate_legacy.simulate_one 接口对齐（输入 DataFrame + 信号 idx；输出 SimResult），
但内部利用 vectorbt 的向量化 + Numba JIT。

差异说明（vbt vs legacy）：
- vbt 的 sl_stop / tp_stop 默认基于 close；可同时传入 high/low 让 vbt 用 OHLC 检测触发，
  贴近 legacy 的 high≥tp / low≤sl 语义。
- vbt 的 stop_exit_price=StopMarket → 触发时默认按精确止损价成交；结果会再用 OHLC 修正跳空情形。
- 不支持 split_tp（分批止盈）；split_tp != None 时回退 legacy。
- 跌破 MA10 当日 close 退出（legacy 是次日开盘退出，存在 1 bar 差异）。
- max_hold：通过 entries.shift(max_hold) 构造的 exit 信号实现，按 close 卖出。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .limit_price import is_limit_down_unsellable, prev_close_of
from .simulate_legacy import (
    SimResult,
    resolve_stop_fill,
    resolve_take_profit_fill,
    simulate_one as simulate_one_legacy,
)

_VBT: Any = None


def _vbt():
    global _VBT
    if _VBT is None:
        import vectorbt as vbt  # type: ignore[import-not-found]
        _VBT = vbt
    return _VBT


def simulate_codes_vbt(
    df: pd.DataFrame,
    idxs: list[int],
    *,
    take_profit: float,
    stop_loss: float,
    max_hold: int,
    split_tp: float | None = None,
    use_ma10_exit: bool = True,
    code: str | None = None,
    name: str | None = None,
) -> list[SimResult]:
    """对一只股票内 N 个 entry idx 批量模拟，返回 list（与 idxs 同序）。

    有 code 时回退 legacy，以支持 ST/跌停顺延规则。
    """
    if not idxs:
        return []
    if split_tp is not None or code:
        from ..data.names import get_stock_name

        stock_name = name or (get_stock_name(code) if code else None)
        return [
            simulate_one_legacy(
                df, i,
                take_profit=take_profit, stop_loss=stop_loss,
                max_hold=max_hold, split_tp=split_tp,
                use_ma10_exit=use_ma10_exit,
                code=code,
                name=stock_name or None,
            )
            for i in idxs
        ]

    vbt = _vbt()
    n = len(idxs)
    T = len(df)

    # 入场 bar = signal_idx + 1
    entry_bars = [i + 1 for i in idxs]

    # 构造 entries / exits (T, n)
    entries = np.zeros((T, n), dtype=bool)
    exits = np.zeros((T, n), dtype=bool)

    # MA10 跌破信号（共用）
    if use_ma10_exit and "ma10" in df.columns:
        ma10_break = (df["close"].to_numpy() < df["ma10"].to_numpy() * 0.99)
        ma10_break = np.where(np.isnan(df["ma10"].to_numpy()), False, ma10_break)
    else:
        ma10_break = np.zeros(T, dtype=bool)

    for col, eb in enumerate(entry_bars):
        if eb >= T:
            continue
        entries[eb, col] = True
        # max_hold exit：到第 eb + max_hold bar 时退出
        td_bar = min(eb + max_hold, T - 1)
        if td_bar < T:
            exits[td_bar, col] = True
        # MA10 break：在 entry 之后的 bar 才生效
        # legacy 要求 j > sig_idx + 2（即 entry 后第 3 bar 起判断），这里也保留
        ma10_start = eb + 2
        if ma10_start < T:
            exits[ma10_start:, col] |= ma10_break[ma10_start:]

    # 广播 OHLCV 到 (T, n)
    cols = [f"e{i}" for i in range(n)]
    idx = pd.Index(df["date"], name="date")
    close_arr = df["close"].to_numpy()[:, None]
    open_arr = df["open"].to_numpy()[:, None]
    high_arr = df["high"].to_numpy()[:, None]
    low_arr = df["low"].to_numpy()[:, None]
    close_mat = pd.DataFrame(np.repeat(close_arr, n, axis=1), index=idx, columns=cols)
    open_mat = pd.DataFrame(np.repeat(open_arr, n, axis=1), index=idx, columns=cols)
    high_mat = pd.DataFrame(np.repeat(high_arr, n, axis=1), index=idx, columns=cols)
    low_mat = pd.DataFrame(np.repeat(low_arr, n, axis=1), index=idx, columns=cols)
    entries_df = pd.DataFrame(entries, index=idx, columns=cols)
    exits_df = pd.DataFrame(exits, index=idx, columns=cols)

    pf = vbt.Portfolio.from_signals(
        close=close_mat,
        entries=entries_df,
        exits=exits_df,
        open=open_mat,
        high=high_mat,
        low=low_mat,
        sl_stop=stop_loss,
        tp_stop=take_profit,
        stop_exit_price="StopMarket",  # 触发时按 stop price 成交（贴近 legacy）
        price=open_mat,           # 入场价 = 当日 open
        init_cash=1.0,
        size=1.0,
        size_type="value",
        accumulate=False,
        freq="1D",
    )

    trades = pf.trades.records_readable
    if trades is None or trades.empty:
        return [SimResult(executable=False) for _ in idxs]

    by_col: dict[str, pd.Series] = {}
    for _, row in trades.iterrows():
        col_name = row["Column"]
        if col_name not in by_col:
            by_col[col_name] = row

    results: list[SimResult] = []
    dates = pd.to_datetime(df["date"]).reset_index(drop=True)
    for col_idx, sig in enumerate(idxs):
        col_name = cols[col_idx]
        eb = entry_bars[col_idx]
        if eb >= T:
            results.append(SimResult(executable=False))
            continue
        if col_name not in by_col:
            results.append(SimResult(executable=False))
            continue
        rec = by_col[col_name]
        buy_price = float(rec["Avg Entry Price"])
        sell_price = float(rec["Avg Exit Price"])
        ret_pct = float(rec["Return"]) * 100.0
        ent_ts = pd.Timestamp(rec["Entry Timestamp"])
        ext_ts = pd.Timestamp(rec["Exit Timestamp"])

        # 找回 sell_idx（用于 max_up / max_dn / hold_days）
        ent_idx_arr = np.where(dates.dt.normalize() == ent_ts.normalize())[0]
        ext_idx_arr = np.where(dates.dt.normalize() == ext_ts.normalize())[0]
        ent_idx = int(ent_idx_arr[0]) if ent_idx_arr.size else eb
        ext_idx = int(ext_idx_arr[0]) if ext_idx_arr.size else min(T - 1, eb + max_hold)

        # max up / down 在持有期内
        seg = df.iloc[ent_idx: ext_idx + 1]
        if not seg.empty and buy_price > 0:
            max_up = (seg["high"].max() - buy_price) / buy_price * 100.0
            max_dn = (seg["low"].min() - buy_price) / buy_price * 100.0
        else:
            max_up = max_dn = 0.0

        # 推断 sell_reason，并按 OHLC 修正跳空止损/止盈成交价
        reason = _infer_reason(rec, buy_price, take_profit, stop_loss, max_hold,
                                ent_idx, ext_idx)
        exit_row = df.iloc[ext_idx]
        o = float(exit_row["open"])
        h = float(exit_row["high"])
        l = float(exit_row["low"])
        sl_px = buy_price * (1 - stop_loss)
        tp_px = buy_price * (1 + take_profit)

        if reason.startswith("止损"):
            sl_fill = resolve_stop_fill(o, h, l, sl_px)
            if sl_fill is not None:
                sell_price = sl_fill
                ret_pct = (sell_price - buy_price) / buy_price * 100.0
                if o <= sl_px:
                    reason = f"止损 -{stop_loss * 100:.0f}%(低开)"
        elif reason.startswith("止盈") and tp_fill is not None:
            tp_fill = resolve_take_profit_fill(o, h, l, tp_px)
            if tp_fill is not None:
                sell_price = tp_fill
                ret_pct = (sell_price - buy_price) / buy_price * 100.0
                if o >= tp_px:
                    reason = f"止盈 +{take_profit * 100:.0f}%(高开)"

        if code and is_limit_down_unsellable(
            prev_close_of(df, ext_idx),
            o,
            h,
            l,
            float(exit_row["close"]),
            code,
            name,
        ):
            leg = simulate_one_legacy(
                df, sig,
                take_profit=take_profit, stop_loss=stop_loss,
                max_hold=max_hold, use_ma10_exit=use_ma10_exit,
                code=code,
                name=name,
            )
            results.append(leg)
            continue

        results.append(SimResult(
            executable=True,
            buy_price=buy_price,
            buy_date=ent_ts.strftime("%Y-%m-%d"),
            sell_price=sell_price,
            sell_date=ext_ts.strftime("%Y-%m-%d"),
            sell_reason=reason,
            return_pct=ret_pct,
            max_up_pct=float(max_up),
            max_dn_pct=float(max_dn),
            hold_days=ext_idx - sig,
        ))
    return results


def _infer_reason(
    rec: pd.Series,
    buy_price: float,
    tp: float,
    sl: float,
    max_hold: int,
    ent_idx: int,
    ext_idx: int,
) -> str:
    """根据成交价 vs 止盈/止损价推断退出原因。"""
    sell = float(rec["Avg Exit Price"])
    if buy_price <= 0:
        return "未知"
    diff = (sell - buy_price) / buy_price
    # 浮点误差容忍；实际亏损超过止损幅度时仍视为止损（如低开穿透）
    eps = 1e-3
    if abs(diff - tp) < eps or diff > tp + eps:
        return f"止盈 +{tp * 100:.0f}%"
    if abs(diff + sl) < eps or diff <= -sl + eps:
        return f"止损 -{sl * 100:.0f}%"
    if (ext_idx - ent_idx) >= max_hold - 1:
        return f"持有{max_hold}日到期"
    return "跌破 MA10"


def simulate_one_vbt(
    df: pd.DataFrame,
    sig_idx: int,
    *,
    take_profit: float = 0.20,
    stop_loss: float = 0.07,
    max_hold: int = 20,
    split_tp: float | None = None,
    use_ma10_exit: bool = True,
) -> SimResult:
    """单笔接口（包装 simulate_codes_vbt）。"""
    res = simulate_codes_vbt(
        df, [sig_idx],
        take_profit=take_profit, stop_loss=stop_loss,
        max_hold=max_hold, split_tp=split_tp,
        use_ma10_exit=use_ma10_exit,
    )
    return res[0] if res else SimResult(executable=False)
