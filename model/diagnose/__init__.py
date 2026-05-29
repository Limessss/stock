"""个股诊断：对指定股票/日期，逐条规则给出 PASS/FAIL。"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..strategies import STRATEGIES, get_strategy
from .check import DiagnoseReport, RuleResult, diagnose_breakout
from .qibao_dian import diagnose_qibao_dian

__all__ = ["DiagnoseReport", "RuleResult", "diagnose_breakout", "diagnose_qibao_dian", "diagnose"]


def diagnose(
    code: str,
    df: pd.DataFrame,
    *,
    strategy_name: str = "breakout_washout",
    strategy_params: dict[str, Any] | None = None,
    target_date: pd.Timestamp | None = None,
) -> DiagnoseReport:
    """按策略名路由到对应诊断实现。"""
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}; 可选: {list(STRATEGIES)}")

    strategy = get_strategy(strategy_name, strategy_params or {})
    if strategy_name == "breakout_washout":
        return diagnose_breakout(
            code,
            df,
            target_date=target_date,
            params=strategy.params,  # type: ignore[arg-type]
        )
    if strategy_name == "qibao_dian":
        return diagnose_qibao_dian(
            code,
            df,
            target_date=target_date,
            params=strategy.params,  # type: ignore[arg-type]
        )
    raise ValueError(f"策略 {strategy_name} 尚未实现诊断")
