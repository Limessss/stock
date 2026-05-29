"""AI 参数调优 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from model.strategies import STRATEGIES

from ..schemas.tuning import (
    TuningAdviseRequest,
    TuningAdviseResponse,
    TuningQuickBacktestRequest,
    TuningQuickBacktestResponse,
    TuningSessionCreate,
    TuningSessionCreateResponse,
    TuningSessionOut,
    TuningTrialOut,
    TuningVerifyRequest,
    TuningVerifyResponse,
)
from ..services.backtest_service import get_task
from ..services.llm_service import LlmNotConfiguredError
from ..services.strategy_service import build_strategy_detail, resolve_strategy_params
from ..services.tuning_runner import (
    advise,
    apply_best_params,
    create_session,
    get_session,
    quick_backtest,
    verify_advise,
)

router = APIRouter()


def _session_to_out(session) -> TuningSessionOut:
    trials = sorted(session.trials, key=lambda t: t.iteration)
    return TuningSessionOut(
        id=session.id,
        strategy_name=session.strategy_name,
        goal=session.goal,
        objective=session.objective,
        backtest_config=session.backtest_config or {},
        max_iterations=session.max_iterations,
        status=session.status,
        error=session.error,
        best_trial_id=session.best_trial_id,
        created_at=session.created_at,
        finished_at=session.finished_at,
        trials=[
            TuningTrialOut(
                id=t.id,
                iteration=t.iteration,
                params=t.params,
                summary=t.summary,
                score=t.score,
                llm_analysis=t.llm_analysis,
                elapsed_seconds=t.elapsed_seconds,
            )
            for t in trials
        ],
    )


@router.post("/tuning/advise", response_model=TuningAdviseResponse)
def tuning_advise(req: TuningAdviseRequest) -> TuningAdviseResponse:
    if req.strategy not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {req.strategy}")
    summary = req.summary
    if req.task_id:
        task = get_task(req.task_id)
        if task is None:
            raise HTTPException(404, f"回测任务不存在: {req.task_id}")
        summary = task.summary
    try:
        result = advise(
            strategy_name=req.strategy,
            params=req.params,
            goal=req.goal,
            summary=summary,
            backtest_config=req.backtest_config.model_dump() if req.backtest_config else None,
        )
    except LlmNotConfiguredError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"大模型调用失败: {e}") from e
    return TuningAdviseResponse(**result)


@router.post("/tuning/quick-backtest", response_model=TuningQuickBacktestResponse)
def tuning_quick_backtest(req: TuningQuickBacktestRequest) -> TuningQuickBacktestResponse:
    if req.strategy not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {req.strategy}")
    try:
        result = quick_backtest(
            strategy_name=req.strategy,
            params=resolve_strategy_params(req.strategy, req.params),
            backtest_config=req.backtest_config.model_dump(),
            objective=req.objective,
        )
    except Exception as e:
        raise HTTPException(500, f"回测失败: {e}") from e
    return TuningQuickBacktestResponse(**result)


@router.post("/tuning/verify", response_model=TuningVerifyResponse)
def tuning_verify(req: TuningVerifyRequest) -> TuningVerifyResponse:
    if req.strategy not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {req.strategy}")
    try:
        result = verify_advise(
            strategy_name=req.strategy,
            suggested_params=req.suggested_params,
            trade_params=req.trade_params,
            verify_summary=req.verify_summary,
            goal=req.goal,
            baseline_summary=req.baseline_summary,
            prior_analysis=req.prior_analysis,
        )
    except LlmNotConfiguredError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"大模型调用失败: {e}") from e
    return TuningVerifyResponse(**result)


@router.post("/tuning/sessions", response_model=TuningSessionCreateResponse)
def start_tuning_session(req: TuningSessionCreate) -> TuningSessionCreateResponse:
    if req.strategy not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {req.strategy}")
    try:
        session_id = create_session(
            strategy_name=req.strategy,
            goal=req.goal,
            objective=req.objective,
            params=resolve_strategy_params(req.strategy, req.params),
            backtest_config=req.backtest_config.model_dump(),
            max_iterations=req.max_iterations,
        )
    except LlmNotConfiguredError as e:
        raise HTTPException(400, str(e)) from e
    return TuningSessionCreateResponse(session_id=session_id, status="pending")


@router.get("/tuning/sessions/{session_id}", response_model=TuningSessionOut)
def fetch_tuning_session(session_id: str) -> TuningSessionOut:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    return _session_to_out(session)


@router.post("/tuning/sessions/{session_id}/apply")
def apply_tuning_session(session_id: str) -> dict:
    try:
        params = apply_best_params(session_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    session = get_session(session_id)
    detail = build_strategy_detail(session.strategy_name) if session else {}
    return {"ok": True, "strategy": session.strategy_name if session else "", "params": params, "label": detail.get("label", "")}
