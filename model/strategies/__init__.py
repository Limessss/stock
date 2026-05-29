"""选股策略：实现 Strategy 接口的各种形态识别算法。"""
import dataclasses

from .base import ScanResult, Strategy
from .breakout_washout import BreakoutParams, BreakoutResult, BreakoutWashoutStrategy
from .breakout_washout import tier_of as breakout_tier_of
from .qibao_dian import QibaoDianParams, QibaoDianResult, QibaoDianStrategy
from .qibao_dian import tier_of as qibao_dian_tier_of

# 全局策略注册表（前端可枚举可用策略）
STRATEGIES: dict[str, type[Strategy]] = {
    BreakoutWashoutStrategy.name: BreakoutWashoutStrategy,
    QibaoDianStrategy.name: QibaoDianStrategy,
}

_TIER_FN = {
    BreakoutWashoutStrategy.name: breakout_tier_of,
    QibaoDianStrategy.name: qibao_dian_tier_of,
}


def get_strategy(name: str, params: dict | None = None) -> Strategy:
    """根据 name 实例化策略；params 是一个 dict，会被转换为 strategy.params_cls。"""
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    if params:
        valid = {f.name for f in dataclasses.fields(cls.params_cls)}
        filtered = {k: v for k, v in params.items() if k in valid}
        p = cls.params_cls(**filtered)
    else:
        p = cls.params_cls()
    return cls(p)


def tier_of(strategy_name: str, score: float) -> str:
    """按策略名选择对应的分级函数。"""
    fn = _TIER_FN.get(strategy_name, breakout_tier_of)
    return fn(score)


__all__ = [
    "ScanResult",
    "Strategy",
    "BreakoutParams",
    "BreakoutResult",
    "BreakoutWashoutStrategy",
    "QibaoDianParams",
    "QibaoDianResult",
    "QibaoDianStrategy",
    "STRATEGIES",
    "get_strategy",
    "tier_of",
]
