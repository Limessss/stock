"""评分公式：基于回测验证的因子权重。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoringWeights:
    """各因子在综合评分公式里的权重。

    默认值与 model/strategies/breakout_washout.py 里 hard-coded 的一致，
    供前端展示和滑块调整，回测中重新映射到策略参数。
    """
    macd: float = 20.0
    breakout_pct: float = 1.5
    bull_ma_count: float = 2.5
    close_to_ma30_bonus: float = 80.0   # max(0, ratio-1) * weight
    pullback_pct: float = 1.5
    vol_ratio: float = 3.0
    limit_up_bonus: float = 10.0
    ma_spread_bonus_cap: float = 5.0
    ma_spread_bonus_weight: float = 3.0


def compute_score(
    macd: float,
    breakout_pct: float,
    bull: int,
    close_to_ma30: float,
    pullback_pct: float,
    vol_ratio: float,
    is_limit_up: bool,
    ma_spread_pct: float,
    weights: ScoringWeights | None = None,
) -> float:
    w = weights or ScoringWeights()
    return (
        macd * w.macd
        + breakout_pct * w.breakout_pct
        + bull * w.bull_ma_count
        + max(0.0, close_to_ma30 - 1.0) * w.close_to_ma30_bonus
        + pullback_pct * w.pullback_pct
        + vol_ratio * w.vol_ratio
        + (w.limit_up_bonus if is_limit_up else 0.0)
        + max(0.0, w.ma_spread_bonus_cap - ma_spread_pct) * w.ma_spread_bonus_weight
    )
