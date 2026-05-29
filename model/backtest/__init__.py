"""回测引擎：基于 VectorBT 的向量化回测封装。"""
from .engine import BacktestConfig, BacktestSummary, Trade, run_backtest
from .simulate_legacy import SimResult, simulate_one

__all__ = [
    "BacktestConfig",
    "BacktestSummary",
    "Trade",
    "SimResult",
    "simulate_one",
    "run_backtest",
]
