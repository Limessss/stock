"""参数调优 Session 后台执行。"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Any

from ..core.database import session_scope
from ..models.tuning import TuningSession, TuningStatus, TuningTrial
from ..data.trade_params import (
    extract_trade_params,
    merge_trade_into_backtest_config,
    validate_trade_params,
)
from .llm_service import LlmNotConfiguredError, chat_json, is_llm_configured
from .strategy_service import resolve_strategy_params, save_strategy_defaults, validate_strategy_params
from .tuning_prompt import build_advise_prompt, build_verify_prompt, default_params_for
from .tuning_service import evaluate_params, score_summary


def create_session(
    *,
    strategy_name: str,
    goal: str,
    objective: str,
    params: dict[str, Any],
    backtest_config: dict[str, Any],
    max_iterations: int,
) -> str:
    session_id = str(uuid.uuid4())
    with session_scope() as s:
        row = TuningSession(
            id=session_id,
            strategy_name=strategy_name,
            goal=goal,
            objective=objective,
            backtest_config={**backtest_config, "initial_params": params},
            max_iterations=max_iterations,
            status=TuningStatus.pending.value,
        )
        s.add(row)
    thread = threading.Thread(
        target=_run_session,
        args=(session_id,),
        daemon=True,
        name=f"tuning-{session_id[:8]}",
    )
    thread.start()
    return session_id


def get_session(session_id: str) -> TuningSession | None:
    with session_scope() as s:
        row = s.get(TuningSession, session_id)
        if row is None:
            return None
        s.refresh(row)
        for t in row.trials:
            s.expunge(t)
        s.expunge(row)
    return row


def apply_best_params(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        raise ValueError("Session 不存在")
    if not session.best_trial_id:
        raise ValueError("尚无最优 trial")
    trial = next((t for t in session.trials if t.id == session.best_trial_id), None)
    if trial is None:
        raise ValueError("最优 trial 不存在")
    return save_strategy_defaults(session.strategy_name, trial.params)


def advise(
    *,
    strategy_name: str,
    params: dict[str, Any],
    goal: str,
    summary: dict[str, Any] | None,
    backtest_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not is_llm_configured():
        raise LlmNotConfiguredError("未配置大模型，请先在系统设置中配置大模型提供商")

    current = resolve_strategy_params(strategy_name, params or None)
    current_trade = extract_trade_params(backtest_config)
    system, user = build_advise_prompt(
        strategy_name=strategy_name,
        current_params=current,
        trade_params=current_trade,
        summary=summary,
        goal=goal,
    )
    raw = chat_json(system=system, user=user)
    suggested = raw.get("suggested_params") or current
    if not isinstance(suggested, dict):
        suggested = current
    merged = {**current, **suggested}
    validated = validate_strategy_params(strategy_name, merged)
    suggested_trade_raw = raw.get("suggested_trade_params")
    validated_trade = validate_trade_params(
        suggested_trade_raw if isinstance(suggested_trade_raw, dict) else None,
        base=current_trade,
    )
    return {
        "analysis": str(raw.get("analysis") or ""),
        "suggested_params": validated,
        "suggested_trade_params": validated_trade,
        "changes": raw.get("changes") or [],
        "trade_changes": raw.get("trade_changes") or [],
        "risks": raw.get("risks") or [],
    }


def quick_backtest(
    *,
    strategy_name: str,
    params: dict[str, Any],
    backtest_config: dict[str, Any],
    objective: str = "composite",
) -> dict[str, Any]:
    """用指定参数同步跑一次回测，供顾问建议后的验证。"""
    t0 = time.perf_counter()
    summary, score = evaluate_params(
        strategy_name=strategy_name,
        params=params,
        backtest_config=backtest_config,
        objective=objective,
    )
    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "summary": summary,
        "score": score,
        "elapsed_seconds": elapsed,
    }


def verify_advise(
    *,
    strategy_name: str,
    suggested_params: dict[str, Any],
    trade_params: dict[str, Any],
    verify_summary: dict[str, Any],
    goal: str,
    baseline_summary: dict[str, Any] | None,
    prior_analysis: str,
) -> dict[str, Any]:
    """将验证回测结果提交大模型检验是否达成调参目标。"""
    if not is_llm_configured():
        raise LlmNotConfiguredError("未配置大模型，请先在系统设置中配置大模型提供商")

    resolved = resolve_strategy_params(strategy_name, suggested_params)
    system, user = build_verify_prompt(
        strategy_name=strategy_name,
        suggested_params=resolved,
        trade_params=trade_params,
        verify_summary=verify_summary,
        goal=goal,
        baseline_summary=baseline_summary,
        prior_analysis=prior_analysis,
    )
    raw = chat_json(system=system, user=user)
    further = raw.get("suggested_params")
    validated_further = None
    if isinstance(further, dict) and further:
        merged = {**resolved, **further}
        validated_further = validate_strategy_params(strategy_name, merged)

    further_trade = raw.get("suggested_trade_params")
    validated_trade = None
    if isinstance(further_trade, dict) and further_trade:
        validated_trade = validate_trade_params(further_trade, base=trade_params)

    return {
        "verdict": str(raw.get("verdict") or "未知"),
        "meets_goal": bool(raw.get("meets_goal", False)),
        "analysis": str(raw.get("analysis") or ""),
        "comparison": str(raw.get("comparison") or ""),
        "highlights": raw.get("highlights") or [],
        "risks": raw.get("risks") or [],
        "suggested_params": validated_further,
        "suggested_trade_params": validated_trade,
    }


def _run_session(session_id: str) -> None:
    try:
        with session_scope() as s:
            session = s.get(TuningSession, session_id)
            if session is None:
                return
            session.status = TuningStatus.running.value
            strategy_name = session.strategy_name
            cfg = dict(session.backtest_config or {})
            goal = session.goal
            objective = session.objective
            max_iter = session.max_iterations
            params = dict(cfg.get("initial_params") or default_params_for(strategy_name))
            trade_params = extract_trade_params(cfg)

        trials_history: list[dict[str, Any]] = []
        best_score = float("-inf")
        best_trial_id: str | None = None

        for i in range(max_iter):
            summary: dict[str, Any] | None = None
            score: float | None = None
            analysis = ""
            t0 = time.perf_counter()

            try:
                if i == 0:
                    trial_params = params
                else:
                    if not is_llm_configured():
                        raise LlmNotConfiguredError("未配置大模型")
                    system, user = build_advise_prompt(
                        strategy_name=strategy_name,
                        current_params=params,
                        trade_params=trade_params,
                        summary=trials_history[-1].get("summary") if trials_history else None,
                        goal=goal,
                        trials=trials_history,
                    )
                    raw = chat_json(system=system, user=user)
                    analysis = str(raw.get("analysis") or "")
                    suggested = raw.get("suggested_params") or params
                    merged = {**params, **suggested} if isinstance(suggested, dict) else params
                    trial_params = validate_strategy_params(strategy_name, merged)
                    suggested_trade = raw.get("suggested_trade_params")
                    if isinstance(suggested_trade, dict) and suggested_trade:
                        trade_params = validate_trade_params(suggested_trade, base=trade_params)
                        cfg = merge_trade_into_backtest_config(cfg, trade_params)

                summary, score = evaluate_params(
                    strategy_name=strategy_name,
                    params=trial_params,
                    backtest_config=cfg,
                    objective=objective,
                )
                params = trial_params
            except Exception as e:
                with session_scope() as s:
                    sess = s.get(TuningSession, session_id)
                    if sess:
                        sess.status = TuningStatus.error.value
                        sess.error = str(e)
                        sess.finished_at = datetime.utcnow()
                return

            elapsed = round(time.perf_counter() - t0, 2)
            trial_id = str(uuid.uuid4())
            with session_scope() as s:
                trial = TuningTrial(
                    id=trial_id,
                    session_id=session_id,
                    iteration=i + 1,
                    params=params,
                    summary=summary,
                    score=score,
                    llm_analysis=analysis or None,
                    elapsed_seconds=elapsed,
                )
                s.add(trial)
                if score is not None and score > best_score:
                    best_score = score
                    best_trial_id = trial_id
                sess = s.get(TuningSession, session_id)
                if sess:
                    sess.best_trial_id = best_trial_id

            trials_history.append(
                {
                    "iteration": i + 1,
                    "params": params,
                    "trade_params": trade_params,
                    "summary": summary,
                    "score": score,
                }
            )

        with session_scope() as s:
            sess = s.get(TuningSession, session_id)
            if sess:
                sess.status = TuningStatus.done.value
                sess.finished_at = datetime.utcnow()
                sess.best_trial_id = best_trial_id
    except Exception as e:
        with session_scope() as s:
            sess = s.get(TuningSession, session_id)
            if sess:
                sess.status = TuningStatus.error.value
                sess.error = str(e)
                sess.finished_at = datetime.utcnow()
