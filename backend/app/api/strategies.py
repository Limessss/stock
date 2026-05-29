"""策略模型 API：列表、详情、元信息与默认参数读写。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from model.strategies import STRATEGIES

from ..schemas.strategy import (
    StrategyConfigUpdate,
    StrategyDefaultsUpdate,
    StrategyDetail,
    StrategyListResponse,
    StrategyMetaUpdate,
)
from ..services.strategy_service import (
    build_strategy_detail,
    build_strategy_list,
    reset_strategy_defaults,
    reset_strategy_meta,
    save_strategy_config,
    save_strategy_defaults,
    save_strategy_meta,
)

router = APIRouter()


@router.get("/strategies", response_model=StrategyListResponse)
def list_strategies() -> StrategyListResponse:
    payload = build_strategy_list()
    return StrategyListResponse(**payload)


@router.get("/strategies/{name}", response_model=StrategyDetail)
def get_strategy_detail(name: str) -> StrategyDetail:
    if name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    return StrategyDetail(**build_strategy_detail(name))


@router.put("/strategies/{name}", response_model=StrategyDetail)
def update_strategy_config(name: str, body: StrategyConfigUpdate) -> StrategyDetail:
    if name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    try:
        save_strategy_config(
            name,
            label=body.label,
            description=body.description,
            is_default=body.is_default,
            params=body.params,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return StrategyDetail(**build_strategy_detail(name))


@router.put("/strategies/{name}/meta", response_model=StrategyDetail)
def update_strategy_meta(name: str, body: StrategyMetaUpdate) -> StrategyDetail:
    if name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    try:
        save_strategy_meta(
            name,
            label=body.label,
            description=body.description,
            is_default=body.is_default,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return StrategyDetail(**build_strategy_detail(name))


@router.put("/strategies/{name}/defaults", response_model=StrategyDetail)
def update_strategy_defaults(name: str, body: StrategyDefaultsUpdate) -> StrategyDetail:
    if name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    try:
        save_strategy_defaults(name, body.params)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return StrategyDetail(**build_strategy_detail(name))


@router.delete("/strategies/{name}/defaults", response_model=StrategyDetail)
def delete_strategy_defaults(name: str) -> StrategyDetail:
    if name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    reset_strategy_defaults(name)
    return StrategyDetail(**build_strategy_detail(name))


@router.delete("/strategies/{name}/meta", response_model=StrategyDetail)
def delete_strategy_meta(name: str) -> StrategyDetail:
    if name not in STRATEGIES:
        raise HTTPException(404, f"未知策略: {name}; 可选: {list(STRATEGIES)}")
    reset_strategy_meta(name)
    return StrategyDetail(**build_strategy_detail(name))
