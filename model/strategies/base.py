"""策略接口基类。

所有策略只需返回 ScanResult（命中）或 None（未命中）。
后端会循环遍历所有股票调 scan(...)；回测引擎据此构造 VectorBT 信号矩阵。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ScanResult:
    code: str
    date: str             # YYYY-MM-DD
    close: float
    breakout_pct: float
    score: float
    extras: dict[str, Any] = field(default_factory=dict)


class Strategy(ABC):
    """策略抽象基类。

    name: 策略英文 id（路由/数据库使用）
    label: 中文展示名
    params_cls: 该策略的参数 dataclass 类型，前端会据此动态渲染表单
    description: 策略说明（策略模型页展示）
    features: 核心逻辑要点
    tier_rules: 评分分级说明
    """

    name: str = "unknown"
    label: str = "未命名策略"
    params_cls: type = type(None)
    description: str = ""
    features: tuple[str, ...] = ()
    tier_rules: tuple[str, ...] = ()

    def __init__(self, params: Any | None = None) -> None:
        self.params = params or (self.params_cls() if self.params_cls is not type(None) else None)

    @abstractmethod
    def scan(
        self,
        code: str,
        df: pd.DataFrame,
        target_date: pd.Timestamp | None = None,
        indicators_ready: bool = False,
    ) -> ScanResult | None:
        """对单只股票在指定交易日（或最后一日）扫描信号。"""
        raise NotImplementedError
