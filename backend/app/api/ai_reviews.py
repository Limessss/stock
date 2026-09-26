"""AI 复盘页面与外部 MCP 服务共用 API。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_session
from ..models.ai_review import AiReview
from ..schemas.ai_review import AiReviewCreate, AiReviewDetail, AiReviewList, AiReviewReceipt
from ..services import ai_review_service as service
from ..services.ai_review_instructions import ReviewHandbookError, review_instructions
from ..services.kline_service import get_kline

router = APIRouter(prefix="/ai-reviews")
Db = Annotated[Session, Depends(get_session)]


@router.get("/overview")
def overview(session: Db):
    return service.overview(session)


@router.get("/instructions")
def instructions(trade_date: date, request: Request, response: Response):
    # 使用后端实际监听端口，避免开发代理的 Host 把 MCP 指向前端端口。
    port = (request.scope.get("server") or ("127.0.0.1", 8000))[1]
    api_url = f"http://127.0.0.1:{port}{settings.api_prefix}"
    response.headers["Cache-Control"] = "no-store"
    try:
        return review_instructions(trade_date, api_url)
    except ReviewHandbookError as exc:
        raise HTTPException(503, str(exc), headers={"Cache-Control": "no-store"}) from exc


@router.get("/context")
def context(session: Db, trade_date: date, lookback_days: int = Query(default=30, ge=1, le=120)):
    return service.review_context(session, trade_date.isoformat(), lookback_days)


@router.get("/context/day")
def day(session: Db, trade_date: date):
    return {
        **service.review_day(session, trade_date.isoformat()),
        "caveats": service.CONTEXT_CAVEATS,
    }


@router.get("/context/stocks/{code}")
def stock_history(
    code: str,
    end_date: date,
    bars: int = Query(default=60, ge=1, le=500),
    adjust: Literal["none", "qfq"] = "none",
):
    import re

    if not re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", code.upper()):
        raise HTTPException(422, "证券代码格式应为 SH600000、SZ000001 或 BJ920000。")
    try:
        data = get_kline(
            code.upper(), last_n=bars + 1, adjust=adjust, end_date=end_date.isoformat()
        )
    except ValueError:
        raise HTTPException(404, "该证券在指定日期及之前没有本地日线。") from None
    if not data["candles"]:
        raise HTTPException(404, "没有该证券的本地日线，请先在数据管理同步。")
    # 多取一根以保留第一根展示 K 线的日涨幅；所有数组统一裁剪。
    for key, value in data.items():
        if isinstance(value, list):
            data[key] = value[-bars:]
    return {
        **data,
        "requested_end_date": end_date.isoformat(),
        "actual_end_date": data["candles"][-1]["time"],
        "source": "local_daily_cache",
        "caveat": "默认未复权；除权日价格变化不能直接视为市场涨跌。qfq 使用当前缓存复权因子，非历史时点快照。仅包含日线，无竞价/分时数据。",
    }


@router.get("", response_model=AiReviewList)
def list_reports(
    session: Db,
    start_date: date | None = None,
    end_date: date | None = None,
    agent_name: str | None = Query(default=None, max_length=80),
    q: str = Query(default="", max_length=200),
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "开始日期不能晚于结束日期。")
    return service.list_reviews(
        session,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        agent_name=agent_name,
        q=q,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=AiReviewReceipt, status_code=201)
def submit_report(payload: AiReviewCreate, response: Response, session: Db):
    try:
        row, created = service.create_review(session, payload)
    except service.SubmissionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    response.status_code = 201 if created else 200
    return {
        "id": row.id,
        "trade_date": row.trade_date,
        "agent_name": row.agent_name,
        "title": row.title,
        "created_at": row.created_at,
        "created": created,
        "report_path": f"/ai-reviews/{row.id}",
    }


@router.get("/{report_id}", response_model=AiReviewDetail)
def get_report(report_id: str, session: Db):
    row = session.get(AiReview, report_id)
    if row is None:
        raise HTTPException(404, "复盘报告不存在。")
    return row
