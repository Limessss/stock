"""可纳入 AI 调优的交易/回测执行参数。"""
from __future__ import annotations

from typing import Any

TUNABLE_TRADE_KEYS: tuple[str, ...] = (
    "take_profit",
    "stop_loss",
    "max_hold",
    "split_tp",
    "position_pct",
    "max_concurrent",
)

TRADE_PARAM_SCHEMA: dict[str, dict[str, Any]] = {
    "take_profit": {
        "type": "float",
        "default": 0.20,
        "min": 0.01,
        "max": 2.0,
        "label": "止盈比例",
        "desc": "单笔盈利达到该比例时卖出（如 0.20 = +20%）",
    },
    "stop_loss": {
        "type": "float",
        "default": 0.07,
        "min": 0.01,
        "max": 0.5,
        "label": "止损比例",
        "desc": "单笔亏损达到该比例时卖出（如 0.07 = -7%）",
    },
    "max_hold": {
        "type": "int",
        "default": 20,
        "min": 1,
        "max": 120,
        "label": "最长持有天数",
        "desc": "超过该交易日数强制平仓",
    },
    "split_tp": {
        "type": "float|null",
        "default": None,
        "min": 0.0,
        "max": 1.0,
        "label": "分批止盈",
        "desc": "先卖出一部分的盈利阈值；null 表示不分批",
    },
    "position_pct": {
        "type": "float",
        "default": 1.0,
        "min": 0.01,
        "max": 1.0,
        "label": "单笔仓位比例",
        "desc": "单笔最多使用初始资金的比例（1.0=尽量满仓）",
    },
    "max_concurrent": {
        "type": "int",
        "default": 1,
        "min": 1,
        "max": 20,
        "label": "最大同时持仓",
        "desc": "1=串行全仓；>1 允许多股同时持仓",
    },
}


def default_trade_params() -> dict[str, Any]:
    return {k: TRADE_PARAM_SCHEMA[k]["default"] for k in TUNABLE_TRADE_KEYS}


def extract_trade_params(backtest_config: dict[str, Any] | None) -> dict[str, Any]:
    """从完整 backtest_config 提取可调交易参数。"""
    base = default_trade_params()
    if not backtest_config:
        return base
    out = dict(base)
    for key in TUNABLE_TRADE_KEYS:
        if key in backtest_config:
            out[key] = backtest_config[key]
    return out


def validate_trade_params(
    raw: dict[str, Any] | None,
    *,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """校验并裁剪 LLM 建议的交易参数，返回完整参数集。"""
    merged_base = dict(base or default_trade_params())
    if not raw or not isinstance(raw, dict):
        return merged_base

    out = dict(merged_base)
    for key in TUNABLE_TRADE_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        spec = TRADE_PARAM_SCHEMA[key]
        if key == "split_tp":
            if val is None or val == "":
                out[key] = None
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            if fval <= 0:
                out[key] = None
            else:
                out[key] = min(float(spec["max"]), max(float(spec["min"]), fval))
            continue
        if spec["type"] == "int":
            try:
                ival = int(val)
            except (TypeError, ValueError):
                continue
            out[key] = min(int(spec["max"]), max(int(spec["min"]), ival))
        else:
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            out[key] = min(float(spec["max"]), max(float(spec["min"]), fval))
    return out


def merge_trade_into_backtest_config(
    backtest_config: dict[str, Any],
    trade_params: dict[str, Any],
) -> dict[str, Any]:
    return {**backtest_config, **trade_params}


def format_trade_param_for_prompt(key: str) -> str:
    spec = TRADE_PARAM_SCHEMA[key]
    return (
        f"- {key}（{spec['label']}，类型 {spec['type']}，默认 {spec['default']}；"
        f"说明：{spec['desc']}）"
    )


def trade_param_schema_lines() -> list[str]:
    return [format_trade_param_for_prompt(k) for k in TUNABLE_TRADE_KEYS]
