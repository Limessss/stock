"""LLM 调参 Prompt 构建。"""
from __future__ import annotations

import json
from typing import Any

from model.strategies import STRATEGIES

from ..data.param_labels import format_param_for_prompt
from ..data.trade_params import trade_param_schema_lines
from .strategy_service import build_strategy_detail, get_effective_defaults

_TRADE_JSON_HINT = (
    "suggested_trade_params(对象，交易执行参数完整集，字段："
    "take_profit、stop_loss、max_hold、split_tp、position_pct、max_concurrent；"
    "split_tp 无分批时为 null)"
)


def build_advise_prompt(
    *,
    strategy_name: str,
    current_params: dict[str, Any],
    trade_params: dict[str, Any] | None = None,
    summary: dict[str, Any] | None,
    goal: str,
    trials: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    detail = build_strategy_detail(strategy_name)
    param_lines = [
        format_param_for_prompt(k, v)
        for k, v in detail["params_schema"].items()
    ]
    trade_lines = trade_param_schema_lines()

    system = (
        "你是 A 股量化策略参数调优顾问。"
        "根据回测指标与策略逻辑，给出保守、可解释的参数调整建议。"
        "可同时优化「策略信号参数」与「交易执行参数（止盈/止损/持仓/仓位）」。"
        "必须输出 JSON，字段："
        "analysis(字符串)、"
        "suggested_params(对象，策略信号参数完整集)、"
        f"{_TRADE_JSON_HINT}、"
        "changes(数组，策略参数变更，每项含 key/from/to/reason)、"
        "trade_changes(数组，交易参数变更，格式同 changes)、risks(字符串数组)。"
        "不要编造不存在的字段；数值类型须与 schema 一致。"
    )

    user_parts = [
        f"## 策略\n名称：{detail['label']} ({strategy_name})\n说明：{detail['description']}",
        f"## 核心逻辑\n" + "\n".join(f"- {x}" for x in detail["features"]),
        "## 策略信号参数 schema\n" + "\n".join(param_lines),
        f"## 当前策略参数\n```json\n{json.dumps(current_params, ensure_ascii=False, indent=2)}\n```",
        "## 交易执行参数 schema\n" + "\n".join(trade_lines),
    ]
    if trade_params:
        user_parts.append(
            f"## 当前交易参数\n```json\n{json.dumps(trade_params, ensure_ascii=False, indent=2)}\n```"
        )
    if summary:
        user_parts.append(
            f"## 最近回测结果\n```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"
        )
    if trials:
        user_parts.append(
            f"## 历史尝试\n```json\n{json.dumps(trials[-5:], ensure_ascii=False, indent=2)}\n```"
        )
    user_parts.append(f"## 用户目标\n{goal or '在控制回撤的前提下提高综合表现'}")
    user_parts.append(
        "请给出 suggested_params 与 suggested_trade_params（均在当前值基础上输出完整参数集）。"
    )

    return system, "\n\n".join(user_parts)


def build_verify_prompt(
    *,
    strategy_name: str,
    suggested_params: dict[str, Any],
    trade_params: dict[str, Any],
    verify_summary: dict[str, Any],
    goal: str,
    baseline_summary: dict[str, Any] | None,
    prior_analysis: str,
) -> tuple[str, str]:
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    detail = build_strategy_detail(strategy_name)
    param_lines = [
        format_param_for_prompt(k, v)
        for k, v in detail["params_schema"].items()
    ]
    trade_lines = trade_param_schema_lines()

    system = (
        "你是 A 股量化策略调优检验顾问。"
        "根据「AI 建议参数」与「验证回测结果」，判断调参是否达到用户目标，并给出客观评述。"
        "必须输出 JSON，字段："
        "verdict(字符串，取值为 达成/部分达成/未达成)、meets_goal(布尔)、"
        "analysis(字符串，综合评述)、comparison(字符串，与基线回测对比；无基线则说明绝对表现)、"
        "highlights(字符串数组，关键发现)、risks(字符串数组)、"
        "suggested_params(对象或 null，若需微调策略参数则输出完整集，否则 null)、"
        "suggested_trade_params(对象或 null，若需微调交易参数则输出完整集，否则 null)。"
        "不要编造不存在的参数字段。"
    )

    user_parts = [
        f"## 策略\n名称：{detail['label']} ({strategy_name})",
        "## 策略信号参数 schema\n" + "\n".join(param_lines),
        f"## AI 建议策略参数\n```json\n{json.dumps(suggested_params, ensure_ascii=False, indent=2)}\n```",
        "## 交易执行参数 schema\n" + "\n".join(trade_lines),
        f"## 验证所用交易参数\n```json\n{json.dumps(trade_params, ensure_ascii=False, indent=2)}\n```",
    ]
    if prior_analysis:
        user_parts.append(f"## 先前 AI 分析\n{prior_analysis}")
    if baseline_summary:
        user_parts.append(
            f"## 基线回测（调参前）\n```json\n{json.dumps(baseline_summary, ensure_ascii=False, indent=2)}\n```"
        )
    user_parts.append(
        f"## 验证回测（建议参数）\n```json\n{json.dumps(verify_summary, ensure_ascii=False, indent=2)}\n```"
    )
    user_parts.append(f"## 用户目标\n{goal or '在控制回撤的前提下提高综合表现'}")
    user_parts.append("请检验回测结果是否达成目标，并给出 verdict 与后续建议。")

    return system, "\n\n".join(user_parts)


def default_params_for(strategy_name: str) -> dict[str, Any]:
    return dict(get_effective_defaults(strategy_name))
