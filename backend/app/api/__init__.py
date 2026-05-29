"""HTTP/WebSocket 路由层。"""
from fastapi import APIRouter

from . import backtest, data, diagnose, factor, health, scan, settings, strategies, tuning

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(strategies.router, tags=["strategies"])
api_router.include_router(tuning.router, tags=["tuning"])
api_router.include_router(scan.router, tags=["scan"])
api_router.include_router(diagnose.router, tags=["diagnose"])
api_router.include_router(data.router, tags=["data"])
api_router.include_router(backtest.router, tags=["backtest"])
api_router.include_router(factor.router, tags=["factor"])

# WebSocket 路由不挂 /api 前缀
ws_router = backtest.ws_router
