"""多因子分析：IC、分位收益、评分公式。"""
from .ic import DEFAULT_FACTORS, ic_table, rank_ic
from .quantile import quintile_stats
from .scoring import ScoringWeights, compute_score

__all__ = [
    "DEFAULT_FACTORS",
    "rank_ic",
    "ic_table",
    "quintile_stats",
    "ScoringWeights",
    "compute_score",
]
