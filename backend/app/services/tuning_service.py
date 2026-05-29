"""策略参数调优：回测评估与打分。"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from model.backtest.engine import BacktestConfig, BacktestSummary, run_backtest
from model.strategies import get_strategy

from .cache_service import get_cache
from .strategy_service import resolve_strategy_params


def score_summary(summary: BacktestSummary | dict[str, Any], objective: str = "composite") -> float:
    if isinstance(summary, BacktestSummary):
        s = asdict(summary)
    else:
        s = summary

    trades = int(s.get("total_trades") or 0)
    if trades < 5:
        return -999.0

    win_rate = float(s.get("win_rate") or 0)
    sharpe = float(s.get("sharpe") or 0)
    cagr = float(s.get("cagr_pct") or 0)
    mdd = float(s.get("max_drawdown_pct") or 0)
    calmar = float(s.get("calmar") or 0)

    if objective == "win_rate":
        return win_rate
    if objective == "sharpe":
        return sharpe
    if objective == "calmar":
        return calmar
    # composite
    return sharpe * 0.35 + win_rate * 0.25 + cagr * 0.2 + calmar * 0.1 - mdd * 0.15


def build_backtest_config(
    *,
    strategy_name: str,
    params: dict[str, Any],
    backtest_config: dict[str, Any],
    start_date: str | None = None,
    end_date: str | None = None,
) -> BacktestConfig:
    """从调参/回测 API 配置构建引擎 BacktestConfig（与回测页一致）。"""
    resolved = resolve_strategy_params(strategy_name, params)
    val_start = backtest_config.get("val_start_date")
    val_end = backtest_config.get("val_end_date")
    eval_start = start_date or val_start or backtest_config["start_date"]
    eval_end = end_date or val_end or backtest_config["end_date"]
    split_tp = backtest_config.get("split_tp")
    return BacktestConfig(
        start_date=eval_start,
        end_date=eval_end,
        strategy_name=strategy_name,
        strategy_params=resolved,
        take_profit=float(backtest_config.get("take_profit", 0.20)),
        stop_loss=float(backtest_config.get("stop_loss", 0.07)),
        max_hold=int(backtest_config.get("max_hold", 20)),
        split_tp=float(split_tp) if split_tp is not None else None,
        max_codes=backtest_config.get("max_codes"),
        num_workers=backtest_config.get("num_workers"),
        engine=str(backtest_config.get("engine", "legacy")),
        initial_capital=float(backtest_config.get("initial_capital", 1_000_000.0)),
        position_pct=float(backtest_config.get("position_pct", 1.0)),
        max_concurrent=int(backtest_config.get("max_concurrent", 1)),
        t_plus_1=bool(backtest_config.get("t_plus_1", True)),
    )


def evaluate_params(
    *,
    strategy_name: str,
    params: dict[str, Any],
    backtest_config: dict[str, Any],
    objective: str = "composite",
) -> tuple[dict[str, Any], float]:
    cfg = build_backtest_config(
        strategy_name=strategy_name,
        params=params,
        backtest_config=backtest_config,
    )
    strategy = get_strategy(strategy_name, cfg.strategy_params)
    cache = get_cache()
    df, summary = run_backtest(cfg, strategy, cache)
    summary_dict = asdict(summary)
    summary_dict["trade_rows"] = len(df)
    score = score_summary(summary_dict, objective)
    return summary_dict, score
