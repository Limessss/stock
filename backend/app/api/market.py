"""行情总览 API。"""

from __future__ import annotations



from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session



from ..core.database import get_session

from ..schemas.market import (

    MarketBuildStatusResponse,

    MarketIndexKlineResponse,

    MarketOverviewBatchRequest,

    MarketOverviewBatchResponse,

    MarketOverviewItem,

    MarketSyncRequest,

    MarketSyncResponse,

)

from ..services import market_service



router = APIRouter()





@router.post("/market/sync", response_model=MarketSyncResponse)

def market_sync(

    req: MarketSyncRequest | None = None,

    session: Session = Depends(get_session),

) -> MarketSyncResponse:

    """检查当日（或非交易日上一交易日）行情是否入库，缺失则自动拉取。"""

    data = market_service.sync_today(session, req.date if req else None)

    return MarketSyncResponse.model_validate(data)





@router.get("/market/overview", response_model=MarketOverviewItem)

def market_overview(

    date: str = Query(..., description="YYYY-MM-DD，非交易日自动对齐上一交易日"),

    session: Session = Depends(get_session),

) -> MarketOverviewItem:

    data = market_service.get_market_overview(session, date)

    return MarketOverviewItem.model_validate(data)





@router.post("/market/overview/batch", response_model=MarketOverviewBatchResponse)

def market_overview_batch(

    req: MarketOverviewBatchRequest,

    session: Session = Depends(get_session),

) -> MarketOverviewBatchResponse:

    items = market_service.get_market_overviews(session, req.dates)

    status = market_service.get_status(session)

    return MarketOverviewBatchResponse(

        items={k: MarketOverviewItem.model_validate(v) for k, v in items.items()},

        building=status["building"] and not status["ready"],

    )





@router.get("/market/index/{code}/kline", response_model=MarketIndexKlineResponse)

def market_index_kline(

    code: str,

    start: str | None = Query(default=None, description="起始日期 YYYY-MM-DD"),

    end: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),

    session: Session = Depends(get_session),

) -> MarketIndexKlineResponse:

    bars = market_service.get_index_kline(session, code.upper(), start, end)

    return MarketIndexKlineResponse(code=code.upper(), bars=bars)





@router.get("/market/overview/status", response_model=MarketBuildStatusResponse)

def market_overview_status(session: Session = Depends(get_session)) -> MarketBuildStatusResponse:

    return MarketBuildStatusResponse.model_validate(market_service.get_status(session))

