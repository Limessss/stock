"""回测引擎主入口。

Phase 1：基于 simulate_legacy 实现完整的扫描+模拟+统计；
Phase 3a：multiprocessing 并行加速。
Phase 3b：把 simulate_legacy 替换为 VectorBT 的 Portfolio.from_signals。
"""
from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..data.cache import DataCache
from ..data.indicators import add_spread_column
from ..data.names import get_stock_name
from ..data.tdx_parser import market_of
from ..strategies import Strategy, get_strategy, tier_of
from .parallel import process_codes_chunk
from .position import apply_portfolio_simulation, portfolio_daily_nav, trades_to_ledger
from .simulate_legacy import SimResult, simulate_one

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    code: str
    signal_date: str
    tier: str
    market: str
    score: float
    breakout_pct: float
    is_limit_up: bool
    vol_ratio: float
    macd: float
    dif: float
    pullback_pct: float
    ma_spread_pct: float
    days_since_test: int
    close_to_ma30: float
    close_to_low60: float
    body_ratio: float
    day_change_pct: float
    bull_ma_count: int
    buy_price: float
    buy_date: str
    sell_price: float
    sell_date: str
    sell_reason: str
    return_pct: float
    max_up_pct: float
    max_dn_pct: float
    hold_days: int
    quantity: int = 0
    buy_amount: float = 0.0
    sell_amount: float = 0.0
    profit_amount: float = 0.0


@dataclass
class BacktestConfig:
    start_date: str
    end_date: str
    strategy_name: str = "breakout_washout"
    strategy_params: dict = field(default_factory=dict)
    take_profit: float = 0.20
    stop_loss: float = 0.07
    max_hold: int = 20
    split_tp: float | None = None
    max_codes: int | None = None  # 调试用：限制扫描股票数量
    num_workers: int | None = 8  # None 时 engine 内默认 8
    chunk_size: int = 100  # worker 一次处理几只股票（小=进度更平滑，大=调度开销低）
    engine: str = "legacy"  # "legacy"=手写循环（精确）；"vectorbt"=实验性（sl/tp 基于 close）
    initial_capital: float = 1_000_000.0  # 初始资金（元）
    position_pct: float = 1.0  # 单笔仓位占初始资金比例（1.0=全仓单笔）
    max_concurrent: int = 1  # 最大同时持仓只数（1=串行全仓，卖完才开下一仓）
    t_plus_1: bool = True  # A 股 T+1：买入当日不可卖出


@dataclass
class BacktestSummary:
    total_trades: int
    win_rate: float
    avg_return: float
    median_return: float
    big_win_rate: float    # 单笔 ≥ 20%
    big_loss_rate: float   # 单笔 ≤ -7%
    avg_hold_days: float
    sharpe: float = 0.0           # 年化夏普（按 trade-by-trade）
    max_drawdown_pct: float = 0.0 # 最大回撤（负数，单位 %）
    calmar: float = 0.0           # 年化收益 / |最大回撤|
    cagr_pct: float = 0.0         # 年化复合收益率（%）
    initial_capital: float = 0.0
    total_profit: float = 0.0     # 期末现金 - 初始资金
    final_capital: float = 0.0
    signal_count: int = 0         # 扫描命中且可模拟的信号数
    skipped_count: int = 0        # 因资金/持仓约束未成交
    max_concurrent: int = 0       # 最大同时持仓只数


def _resolve_workers(num_workers: int | None) -> int:
    """解析并行度。未指定时默认 8。"""
    if num_workers is not None:
        return max(1, num_workers)
    return 8


def run_backtest(
    cfg: BacktestConfig,
    strategy: Strategy,
    cache: DataCache,
    *,
    progress_cb: Callable[[int, int, int], None] | None = None,
) -> tuple[pd.DataFrame, BacktestSummary]:
    """跑回测，返回 (trades_df, summary)。

    progress_cb(done, total, accumulated_trades) — 每处理一批股票触发一次。
    根据 cfg.num_workers 选择串行或多进程：
      - 1 → 串行（调试 / 测试用）
      - None / 未指定 → 默认 8
      - >=2 → 多进程，每个 worker 处理 cfg.chunk_size 只股票
    """
    codes = cache.codes()
    if cfg.max_codes:
        codes = codes[: cfg.max_codes]
    if not codes:
        return pd.DataFrame(), _empty_summary()

    workers = _resolve_workers(cfg.num_workers)
    if workers > 1 and len(codes) >= cfg.chunk_size * 2:
        df_trades, summary = _run_parallel(cfg, cache, codes, workers, progress_cb)
        if df_trades.empty and len(codes) > 0:
            logger.warning("parallel backtest returned no trades; falling back to serial")
            return _run_serial(cfg, strategy, cache, codes, progress_cb)
        return df_trades, summary
    return _run_serial(cfg, strategy, cache, codes, progress_cb)


def simulate_batch(
    df: pd.DataFrame,
    idxs: list[int],
    cfg: BacktestConfig,
    code: str | None = None,
) -> list[SimResult]:
    """根据 cfg.engine 选 simulate 实现，对一只股票内多个 entry 批量返回 SimResult。"""
    if not idxs:
        return []
    stock_name = get_stock_name(code) if code else ""
    if cfg.engine == "vectorbt":
        from .vbt_engine import simulate_codes_vbt
        return simulate_codes_vbt(
            df, idxs,
            take_profit=cfg.take_profit, stop_loss=cfg.stop_loss,
            max_hold=cfg.max_hold, split_tp=cfg.split_tp,
            code=code,
            name=stock_name or None,
        )
    return [
        simulate_one(
            df, i,
            take_profit=cfg.take_profit, stop_loss=cfg.stop_loss,
            max_hold=cfg.max_hold, split_tp=cfg.split_tp,
            t_plus_1=cfg.t_plus_1,
            code=code,
            name=stock_name or None,
        )
        for i in idxs
    ]


def _run_serial(
    cfg: BacktestConfig,
    strategy: Strategy,
    cache: DataCache,
    codes: list[str],
    progress_cb: Callable[[int, int, int], None] | None,
) -> tuple[pd.DataFrame, BacktestSummary]:
    ts_start = pd.Timestamp(cfg.start_date)
    ts_end = pd.Timestamp(cfg.end_date)
    trades: list[Trade] = []
    total = len(codes)
    for i, code in enumerate(codes, 1):
        df = cache.load_no_cache(code)
        if df is None:
            continue
        if "ma_spread_pct" not in df.columns:
            add_spread_column(df, inplace=True)
        in_range = (df["date"] >= ts_start) & (df["date"] <= ts_end)
        if not in_range.any():
            continue
        # Step 1: 收集 hits
        hits: list[tuple[int, object]] = []
        for idx in df.index[in_range].tolist():
            res = strategy.scan(code, df, df.iloc[idx]["date"], indicators_ready=True)
            if res is not None:
                hits.append((idx, res))
        if not hits:
            if progress_cb and i % 50 == 0:
                progress_cb(i, total, len(trades))
            continue
        # Step 2: 批量 simulate（vbt 引擎可一次性向量化所有 hits）
        sims = simulate_batch(df, [h[0] for h in hits], cfg, code=code)
        for (idx, res), sim in zip(hits, sims):
            if not sim.executable:
                continue
            days_since_test = (
                pd.Timestamp(res.date) - pd.Timestamp(getattr(res, "test_date", res.date))
            ).days
            trades.append(Trade(
                code=code, signal_date=res.date, tier=tier_of(cfg.strategy_name, res.score),
                market=market_of(code), score=res.score, breakout_pct=res.breakout_pct,
                is_limit_up=getattr(res, "is_limit_up", False),
                vol_ratio=getattr(res, "vol_ratio", 0.0),
                macd=getattr(res, "macd", 0.0), dif=getattr(res, "dif", 0.0),
                pullback_pct=getattr(res, "pullback_pct", 0.0),
                ma_spread_pct=getattr(res, "ma_spread_pct", 0.0),
                days_since_test=days_since_test,
                close_to_ma30=getattr(res, "close_to_ma30", 1.0),
                close_to_low60=getattr(res, "close_to_low60", 1.0),
                body_ratio=getattr(res, "body_ratio", 0.0),
                day_change_pct=getattr(res, "day_change_pct", 0.0),
                bull_ma_count=getattr(res, "bull_ma_count", 0),
                buy_price=sim.buy_price, buy_date=sim.buy_date,
                sell_price=sim.sell_price, sell_date=sim.sell_date,
                sell_reason=sim.sell_reason, return_pct=sim.return_pct,
                max_up_pct=sim.max_up_pct, max_dn_pct=sim.max_dn_pct,
                hold_days=sim.hold_days,
            ))
        if progress_cb and i % 50 == 0:
            progress_cb(i, total, len(trades))
    if progress_cb:
        progress_cb(total, total, len(trades))
    if not trades:
        return pd.DataFrame(), _empty_summary()
    df_trades = pd.DataFrame([asdict(t) for t in trades])
    return _finalize_trades(df_trades, cfg)


def _run_parallel(
    cfg: BacktestConfig,
    cache: DataCache,
    codes: list[str],
    workers: int,
    progress_cb: Callable[[int, int, int], None] | None,
) -> tuple[pd.DataFrame, BacktestSummary]:
    raw_dir = str(cache.raw_dir)
    cache_dir = str(cache.cache_dir)
    cfg_dict = asdict(cfg)
    chunks = [codes[i: i + cfg.chunk_size] for i in range(0, len(codes), cfg.chunk_size)]
    total = len(codes)
    done = 0
    all_trades: list[dict] = []
    if progress_cb:
        progress_cb(0, total, 0)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_codes_chunk, (chunk, raw_dir, cache_dir, cfg_dict)): len(chunk)
            for chunk in chunks
        }
        for fut in as_completed(futures):
            chunk_len = futures[fut]
            try:
                trades_chunk = fut.result()
            except Exception:
                logger.exception("parallel backtest worker failed")
                trades_chunk = []
            all_trades.extend(trades_chunk)
            done += chunk_len
            if progress_cb:
                progress_cb(min(done, total), total, len(all_trades))
    if not all_trades:
        return pd.DataFrame(), _empty_summary()
    df_trades = pd.DataFrame(all_trades)
    return _finalize_trades(df_trades, cfg)


def _finalize_trades(
    df_trades: pd.DataFrame, cfg: BacktestConfig
) -> tuple[pd.DataFrame, BacktestSummary]:
    df_trades, port_stats = apply_portfolio_simulation(
        df_trades,
        initial_capital=cfg.initial_capital,
        position_pct=cfg.position_pct,
        max_concurrent=cfg.max_concurrent,
        t_plus_1=cfg.t_plus_1,
    )
    return df_trades, _summarize(df_trades, cfg.initial_capital, port_stats)


def _summarize(
    df: pd.DataFrame,
    initial_capital: float = 0.0,
    port_stats: dict | None = None,
) -> BacktestSummary:
    ps = port_stats or {}
    if df.empty:
        return _empty_summary(ps)
    rets = df["return_pct"]
    risk = _compute_risk_metrics(df)
    ic = initial_capital or 0.0
    total_profit = float(ps.get("total_profit", 0.0))
    final_capital = float(ps.get("final_cash", ic + total_profit))
    if total_profit == 0.0 and "profit_amount" in df.columns:
        total_profit = round(final_capital - ic, 2)
    return BacktestSummary(
        total_trades=len(df),
        win_rate=float((rets > 0).mean() * 100),
        avg_return=float(rets.mean()),
        median_return=float(rets.median()),
        big_win_rate=float((rets >= 20).mean() * 100),
        big_loss_rate=float((rets <= -7).mean() * 100),
        avg_hold_days=float(df["hold_days"].mean()),
        sharpe=risk["sharpe"],
        max_drawdown_pct=risk["max_drawdown_pct"],
        calmar=risk["calmar"],
        cagr_pct=risk["cagr_pct"],
        initial_capital=ic,
        total_profit=total_profit,
        final_capital=final_capital,
        signal_count=int(ps.get("signal_count", len(df))),
        skipped_count=int(ps.get("skipped_count", 0)),
        max_concurrent=int(ps.get("max_concurrent", 0)),
    )


def _aggregate_daily(df: pd.DataFrame) -> pd.Series:
    """按 sell_date 聚合：当日所有 trades 取**均值** return_pct（百分点单位）。

    这是「单日多笔等权」的直观假设；所有指标都基于此序列。
    """
    df = df.sort_values("sell_date").copy()
    df["sell_dt"] = pd.to_datetime(df["sell_date"], errors="coerce")
    df = df.dropna(subset=["sell_dt"])
    if df.empty:
        return pd.Series(dtype=float)
    return df.groupby(df["sell_dt"].dt.normalize())["return_pct"].mean()


def _compute_risk_metrics(df: pd.DataFrame) -> dict:
    """每笔等权（无复利杠杆）→ 计算夏普、最大回撤、Calmar、CAGR。

    净值曲线：累加 daily 均值 return_pct（百分点单位）。
    避免日内复利累乘带来虚高 CAGR/Calmar；曲线代表「每日等权下注 1 单位本金」的累计盈亏。
    """
    daily_pct = _aggregate_daily(df)
    if daily_pct.empty or len(daily_pct) < 2:
        return {"sharpe": 0.0, "max_drawdown_pct": 0.0, "calmar": 0.0, "cagr_pct": 0.0}

    cum_pct = daily_pct.cumsum()  # 累加百分点（不复利）
    daily_decimal = daily_pct / 100.0
    std = float(daily_decimal.std(ddof=0))
    sharpe = float(daily_decimal.mean() / std * np.sqrt(252)) if std > 0 else 0.0

    drawdown_pct = cum_pct - cum_pct.cummax()
    max_dd_pct = float(drawdown_pct.min())  # 单位：百分点（负数）

    span_days = max((daily_pct.index[-1] - daily_pct.index[0]).days, 1)
    total_return_pct = float(cum_pct.iloc[-1])  # 累计百分点
    cagr_pct = total_return_pct * 365.0 / span_days
    calmar = float(cagr_pct / abs(max_dd_pct)) if max_dd_pct < 0 else 0.0

    return {
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "calmar": calmar,
        "cagr_pct": cagr_pct,
    }


def compute_extended_metrics(df: pd.DataFrame, *, initial_capital: float = 0.0) -> dict:
    """详细指标：含月度热力图 + 净值曲线点（用于 /metrics 端点）。"""
    if df.empty:
        return {"sharpe": 0.0, "max_drawdown_pct": 0.0, "calmar": 0.0, "cagr_pct": 0.0,
                "monthly": [], "equity_curve": [], "initial_capital": initial_capital,
                "total_profit": 0.0, "final_capital": initial_capital}

    use_money = (
        initial_capital > 0
        and "profit_amount" in df.columns
        and df["profit_amount"].abs().sum() > 0
    )

    if use_money:
        return _compute_extended_metrics_money(df, initial_capital)

    daily_pct = _aggregate_daily(df)
    if daily_pct.empty:
        return {"sharpe": 0.0, "max_drawdown_pct": 0.0, "calmar": 0.0, "cagr_pct": 0.0,
                "monthly": [], "equity_curve": [], "initial_capital": initial_capital,
                "total_profit": 0.0, "final_capital": initial_capital}

    risk = _compute_risk_metrics(df)
    cum_pct = daily_pct.cumsum()  # 累计百分点

    # 月度：当月单日均值的总和（也是百分点累加）
    monthly_pct = daily_pct.groupby([daily_pct.index.year, daily_pct.index.month]).sum()
    monthly = [
        {"year": int(y), "month": int(m), "return_pct": float(v)}
        for (y, m), v in monthly_pct.items()
    ]

    # 前端仍以 nav 形式呈现：nav = 1 + cum_pct/100
    equity = [
        {"date": d.strftime("%Y-%m-%d"), "nav": 1.0 + float(v) / 100.0}
        for d, v in cum_pct.items()
    ]

    total_profit = float(df["profit_amount"].sum()) if "profit_amount" in df.columns else 0.0
    return {
        **risk,
        "monthly": monthly,
        "equity_curve": equity,
        "initial_capital": initial_capital,
        "total_profit": total_profit,
        "final_capital": initial_capital + total_profit,
    }


def _compute_extended_metrics_money(df: pd.DataFrame, initial_capital: float) -> dict:
    """基于组合现金流的净值曲线（按流水逐日回放现金余额）。"""
    ledger = trades_to_ledger(df)
    nav_points = portfolio_daily_nav(ledger, initial_capital)
    if not nav_points:
        return {"sharpe": 0.0, "max_drawdown_pct": 0.0, "calmar": 0.0, "cagr_pct": 0.0,
                "monthly": [], "equity_curve": [], "initial_capital": initial_capital,
                "total_profit": 0.0, "final_capital": initial_capital}

    nav_df = pd.DataFrame(nav_points)
    nav_df["dt"] = pd.to_datetime(nav_df["date"])
    nav_df = nav_df.sort_values("dt")
    equity_series = nav_df.set_index("dt")["equity"]

    daily_ret = equity_series.pct_change().dropna()
    std = float(daily_ret.std(ddof=0))
    sharpe = float(daily_ret.mean() / std * np.sqrt(252)) if std > 0 else 0.0

    cummax = equity_series.cummax()
    drawdown = (equity_series - cummax) / cummax.replace(0, np.nan)
    max_dd_pct = float(drawdown.min() * 100)
    if np.isnan(max_dd_pct):
        max_dd_pct = 0.0

    span_days = max((nav_df["dt"].iloc[-1] - nav_df["dt"].iloc[0]).days, 1)
    final_capital = float(equity_series.iloc[-1])
    total_profit = round(final_capital - initial_capital, 2)
    total_return_pct = (final_capital / initial_capital - 1) * 100 if initial_capital > 0 else 0.0
    cagr_pct = total_return_pct * 365.0 / span_days
    calmar = float(cagr_pct / abs(max_dd_pct)) if max_dd_pct < 0 else 0.0

    nav_df["year"] = nav_df["dt"].dt.year
    nav_df["month"] = nav_df["dt"].dt.month
    monthly = []
    for (y, m), grp in nav_df.groupby(["year", "month"]):
        month_start = float(grp["equity"].iloc[0])
        month_end = float(grp["equity"].iloc[-1])
        ret = (month_end / month_start - 1) * 100 if month_start > 0 else 0.0
        monthly.append({"year": int(y), "month": int(m), "return_pct": float(ret)})

    equity = [
        {"date": row["date"], "nav": float(row["nav"])}
        for _, row in nav_df.iterrows()
    ]

    return {
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "calmar": calmar,
        "cagr_pct": cagr_pct,
        "monthly": monthly,
        "equity_curve": equity,
        "initial_capital": initial_capital,
        "total_profit": total_profit,
        "final_capital": final_capital,
    }


def _empty_summary(port_stats: dict | None = None) -> BacktestSummary:
    ps = port_stats or {}
    ic = float(ps.get("initial_capital", 0.0))
    return BacktestSummary(
        0, 0, 0, 0, 0, 0, 0,
        initial_capital=ic,
        final_capital=float(ps.get("final_cash", ic)),
        signal_count=int(ps.get("signal_count", 0)),
        skipped_count=int(ps.get("skipped_count", 0)),
    )
