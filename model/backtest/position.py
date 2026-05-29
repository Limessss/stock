"""组合级资金约束模拟。

在扫描+单笔 simulate 之后，按时间顺序回放买/卖事件：
- 维护可用现金与持仓占用
- 同日先卖后买（释放现金后再开新仓）
- 同一股票持仓未平前不再开新仓
- 同一股票当日卖出后，不再以当日开盘价重新买入（避免「11.44 卖完又 10.84 买」的时序矛盾）
- 单笔预算 = min(可用现金, 初始资金 × position_pct)，A 股 100 股整手
- max_concurrent：最大同时持仓只数（默认 1 = 全仓串行，卖完才开下一仓）
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

LOT_SIZE = 100
PORTFOLIO_RULES_VERSION = "2"  # v2: 当日待平仓票禁止同日开盘价再买入


def calc_lot_quantity(budget: float, price: float) -> int:
    """给定预算与单价，返回可买股数（整百）。"""
    if budget <= 0 or price <= 0:
        return 0
    lots = math.floor(budget / price / LOT_SIZE)
    return int(lots * LOT_SIZE)


def _to_date_str(d: object) -> str:
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return ""
    if isinstance(d, pd.Timestamp):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def _trade_key(row: dict) -> str:
    return f"{row['code']}|{row['signal_date']}"


def _effective_sell_date(buy_date: object, sell_date: object, *, t_plus_1: bool) -> str:
    """T+1：卖出日不得早于买入日的下一自然日（组合回放兜底）。"""
    bd = _to_date_str(buy_date)
    sd = _to_date_str(sell_date)
    if not bd or not sd:
        return sd
    if t_plus_1 and sd <= bd:
        return (pd.Timestamp(bd) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return sd


def apply_portfolio_simulation(
    df: pd.DataFrame,
    *,
    initial_capital: float,
    position_pct: float,
    max_concurrent: int = 1,
    t_plus_1: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """组合回放，返回 (实际成交 trades, 统计信息)。"""
    stats: dict[str, Any] = {
        "initial_capital": initial_capital,
        "position_pct": position_pct,
        "signal_count": 0,
        "executed_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {
            "no_cash": 0,
            "same_code": 0,
            "zero_lot": 0,
            "max_concurrent": 0,
            "same_day_reentry": 0,
            "same_day_exit_conflict": 0,
        },
        "final_cash": initial_capital,
        "peak_cash_used": 0.0,
        "max_concurrent": 0,
    }
    if df.empty or initial_capital <= 0:
        return df.iloc[0:0].copy(), stats

    stats["signal_count"] = len(df)
    candidates = df.sort_values(
        ["buy_date", "score"], ascending=[True, False]
    ).reset_index(drop=True).to_dict("records")

    cash = float(initial_capital)
    held_codes: set[str] = set()
    code_sold_on: dict[str, str] = {}  # code -> 最近卖出日（禁止同日再买入）
    open_pos: dict[str, dict] = {}  # trade_key -> enriched row
    executed: list[dict] = []
    peak_concurrent = 0

    events: list[tuple[str, str, dict, int]] = []
    for row in candidates:
        bd = _to_date_str(row["buy_date"])
        sd = _effective_sell_date(bd, row["sell_date"], t_plus_1=t_plus_1)
        # phase: 0=平旧仓 1=开仓 2=平当日新仓（买卖同日，T+1 下应不会出现）
        events.append(("sell", sd, row, 0 if sd != bd else 2))
        events.append(("buy", bd, row, 1))
    events.sort(
        key=lambda e: (
            _to_date_str(e[1]),
            e[3],
            0 if e[0] == "sell" else 1,
            -float(e[2].get("score") or 0),
            e[2]["code"],
        )
    )

    cap_per_trade = initial_capital * position_pct
    max_conc = max(1, int(max_concurrent))

    current_day = ""
    exiting_today: set[str] = set()

    for action, _date, row, _phase in events:
        day = _to_date_str(_date)
        if day != current_day:
            current_day = day
            exiting_today = {
                pos["code"]
                for pos in open_pos.values()
                if _effective_sell_date(
                    pos["buy_date"], pos["sell_date"], t_plus_1=t_plus_1
                ) == day
            }

        key = _trade_key(row)
        code = row["code"]

        if action == "buy":
            if key in open_pos:
                continue
            buy_date_str = _to_date_str(row["buy_date"])
            if code in exiting_today:
                stats["skipped_count"] += 1
                stats["skipped_reasons"]["same_day_exit_conflict"] += 1
                continue
            if code_sold_on.get(code) == buy_date_str:
                # 当日已卖出该票，不能再以开盘价买入（时序矛盾）
                stats["skipped_count"] += 1
                stats["skipped_reasons"]["same_day_reentry"] += 1
                continue
            if code in held_codes:
                stats["skipped_count"] += 1
                stats["skipped_reasons"]["same_code"] += 1
                continue
            if len(open_pos) >= max_conc:
                stats["skipped_count"] += 1
                stats["skipped_reasons"]["max_concurrent"] += 1
                continue
            budget = min(cash, cap_per_trade)
            buy_price = float(row["buy_price"])
            qty = calc_lot_quantity(budget, buy_price)
            if qty <= 0:
                stats["skipped_count"] += 1
                stats["skipped_reasons"]["zero_lot"] += 1
                continue
            buy_amount = round(qty * buy_price, 2)
            if buy_amount > cash + 1e-6:
                stats["skipped_count"] += 1
                stats["skipped_reasons"]["no_cash"] += 1
                continue

            cash = round(cash - buy_amount, 2)
            stats["peak_cash_used"] = max(stats["peak_cash_used"], initial_capital - cash)

            sell_price = float(row["sell_price"])
            sell_amount = round(qty * sell_price, 2)
            profit_amount = round(sell_amount - buy_amount, 2)
            return_pct = (profit_amount / buy_amount * 100) if buy_amount > 0 else 0.0

            enriched = dict(row)
            enriched.update(
                quantity=qty,
                buy_amount=buy_amount,
                sell_amount=sell_amount,
                profit_amount=profit_amount,
                return_pct=return_pct,
                sell_date=_effective_sell_date(buy_date_str, row["sell_date"], t_plus_1=t_plus_1),
            )
            open_pos[key] = enriched
            held_codes.add(code)
            peak_concurrent = max(peak_concurrent, len(open_pos))

        else:  # sell
            pos = open_pos.get(key)
            if pos is None:
                continue
            if t_plus_1 and _to_date_str(_date) <= _to_date_str(pos["buy_date"]):
                continue
            open_pos.pop(key, None)
            held_codes.discard(code)
            sell_day = _to_date_str(_date)
            code_sold_on[code] = sell_day
            cash = round(cash + pos["sell_amount"], 2)
            executed.append(pos)

    stats["executed_count"] = len(executed)
    stats["final_cash"] = cash
    stats["total_profit"] = round(cash - initial_capital, 2)
    stats["max_concurrent"] = peak_concurrent

    if not executed:
        return pd.DataFrame(), stats
    out = pd.DataFrame(executed)
    out = out.sort_values(["buy_date", "code"]).reset_index(drop=True)
    return out, stats


def apply_position_sizing(
    df: pd.DataFrame,
    *,
    initial_capital: float,
    position_pct: float,
    max_concurrent: int = 1,
    t_plus_1: bool = True,
) -> pd.DataFrame:
    """兼容入口：走组合级约束。"""
    result, _ = apply_portfolio_simulation(
        df,
        initial_capital=initial_capital,
        position_pct=position_pct,
        max_concurrent=max_concurrent,
        t_plus_1=t_plus_1,
    )
    return result


def enrich_trade_row(
    row: dict,
    *,
    initial_capital: float,
    position_pct: float,
) -> dict:
    """旧接口保留：单条独立 sizing（ledger 补算旧数据时用）。"""
    budget = initial_capital * position_pct
    buy_price = float(row["buy_price"])
    qty = calc_lot_quantity(budget, buy_price)
    if qty <= 0:
        row.update(quantity=0, buy_amount=0.0, sell_amount=0.0, profit_amount=0.0)
        return row
    buy_amount = round(qty * buy_price, 2)
    return_pct = float(row["return_pct"])
    profit_amount = round(buy_amount * return_pct / 100.0, 2)
    sell_amount = round(buy_amount + profit_amount, 2)
    row.update(
        quantity=qty,
        buy_amount=buy_amount,
        sell_amount=sell_amount,
        profit_amount=profit_amount,
    )
    return row


def _ledger_event_order(x: dict) -> tuple:
    """同日流水：先卖后买，与组合资金回放及「卖完才有现金买」一致。"""
    d = _to_date_str(x["date"])
    phase = 0 if x["action"] == "sell" else 1
    return (d, phase, x["code"])


def trades_to_ledger(df: pd.DataFrame) -> list[dict]:
    """把成交记录展开为按时间排序的买/卖流水。"""
    if df.empty:
        return []

    rows: list[dict] = []
    for r in df.to_dict("records"):
        code = r["code"]
        qty = int(r.get("quantity") or 0)
        if qty <= 0:
            continue
        sig = r["signal_date"]
        rows.append({
            "date": r["buy_date"],
            "action": "buy",
            "code": code,
            "signal_date": sig,
            "price": float(r["buy_price"]),
            "quantity": qty,
            "amount": float(r.get("buy_amount") or 0),
            "profit_amount": None,
            "sell_reason": None,
        })
        rows.append({
            "date": r["sell_date"],
            "action": "sell",
            "code": code,
            "signal_date": sig,
            "buy_date": r["buy_date"],
            "price": float(r["sell_price"]),
            "quantity": qty,
            "amount": float(r.get("sell_amount") or 0),
            "profit_amount": float(r.get("profit_amount") or 0),
            "sell_reason": r.get("sell_reason"),
        })

    rows.sort(key=_ledger_event_order)
    return rows


def portfolio_daily_nav(ledger: list[dict], initial_capital: float) -> list[dict]:
    """从流水重建每日组合总权益（现金 + 未平仓持仓成本）。

    仅用现金会在满仓时误显示为「净值归零」；持仓期间按买入成本计入权益，
    卖出后现金回流，曲线与真实组合盈亏一致。
    """
    if not ledger or initial_capital <= 0:
        return []

    cash = float(initial_capital)
    open_cost: dict[str, float] = {}
    by_date: dict[str, float] = {}

    for ev in sorted(ledger, key=_ledger_event_order):
        d = _to_date_str(ev["date"])
        code = ev["code"]
        if ev["action"] == "buy":
            amt = float(ev["amount"])
            cash = round(cash - amt, 2)
            open_cost[code] = open_cost.get(code, 0.0) + amt
        else:
            cash = round(cash + float(ev["amount"]), 2)
            open_cost.pop(code, None)

        equity = round(cash + sum(open_cost.values()), 2)
        by_date[d] = equity

    if not by_date:
        return []

    start = pd.Timestamp(min(by_date.keys()))
    end = pd.Timestamp(max(by_date.keys()))
    last_equity = float(initial_capital)
    points: list[dict] = []
    for day in pd.date_range(start, end, freq="D"):
        ds = day.strftime("%Y-%m-%d")
        if ds in by_date:
            last_equity = by_date[ds]
        points.append({
            "date": ds,
            "nav": last_equity / initial_capital,
            "equity": last_equity,
            "cash": by_date.get(ds, None),
        })
    return points
