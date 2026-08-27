"""HTTP/WebSocket 路由层。"""
from fastapi import APIRouter

from . import backtest, data, gann, health, kline, market, notes, scan, sentiment, settings, stocks, strategies

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(strategies.router, tags=["strategies"])
api_router.include_router(scan.router, tags=["scan"])
api_router.include_router(kline.router, tags=["kline"])
api_router.include_router(gann.router, tags=["gann"])
api_router.include_router(stocks.router, tags=["stocks"])
api_router.include_router(data.router, tags=["data"])
api_router.include_router(backtest.router, tags=["backtest"])
api_router.include_router(notes.router, tags=["notes"])
api_router.include_router(market.router, tags=["market"])
api_router.include_router(sentiment.router, tags=["sentiment"])

# WebSocket 路由不挂 /api 前缀
ws_router = backtest.ws_router
