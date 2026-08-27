"""情绪周期 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_session
from ..core.config import settings
from ..schemas.sentiment import (
    FeedbackCreate,
    FeedbackUpdate,
    IntervalGainResponse,
    LeaderPanoramaConfigResponse,
    LeaderPanoramaConfigUpdate,
    MajorFirstBoardsUpdate,
    SentimentDay,
    SentimentFeedbackItem,
    SentimentMatrixResponse,
    SentimentSyncRequest,
    SentimentSyncResponse,
)
from ..services import sentiment_service
from ..services import panorama_service
from ..services.interval_gain_service import get_interval_gains

router = APIRouter()


@router.get("/sentiment/panorama/config", response_model=LeaderPanoramaConfigResponse)
def get_panorama_config(
    session: Session = Depends(get_session),
) -> LeaderPanoramaConfigResponse:
    config = panorama_service.get_config(session)
    if config is None:
        return LeaderPanoramaConfigResponse(initialized=False, instruments=[], updated_at=None)
    return LeaderPanoramaConfigResponse(
        initialized=True,
        instruments=config.instruments or [],
        updated_at=config.updated_at,
    )


@router.put("/sentiment/panorama/config", response_model=LeaderPanoramaConfigResponse)
def put_panorama_config(
    body: LeaderPanoramaConfigUpdate,
    session: Session = Depends(get_session),
) -> LeaderPanoramaConfigResponse:
    config = panorama_service.save_config(
        session,
        [item.model_dump() for item in body.instruments],
    )
    session.commit()
    return LeaderPanoramaConfigResponse(
        initialized=True,
        instruments=config.instruments or [],
        updated_at=config.updated_at,
    )


@router.get("/sentiment/matrix", response_model=SentimentMatrixResponse)
def sentiment_matrix(
    start: str | None = Query(default=None, max_length=10),
    end: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=20, ge=1, le=60),
    session: Session = Depends(get_session),
) -> SentimentMatrixResponse:
    items = sentiment_service.get_matrix(session, start_date=start, end_date=end, limit=limit)
    return SentimentMatrixResponse(items=[SentimentDay.model_validate(item) for item in items])


@router.get("/sentiment/interval-gains", response_model=IntervalGainResponse)
def sentiment_interval_gains(
    start: str | None = Query(default=None, max_length=10),
    end: str | None = Query(default=None, max_length=10),
    days: int = Query(default=5, ge=1, le=250),
    limit: int = Query(default=50, ge=10, le=500),
) -> IntervalGainResponse:
    try:
        result = get_interval_gains(
            settings.cache_dir,
            start_date=start,
            end_date=end,
            days=days,
            limit=limit,
        )  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return IntervalGainResponse.model_validate(result)


@router.put("/sentiment/feedback/{feedback_id}", response_model=SentimentFeedbackItem)
def update_feedback(
    feedback_id: str,
    body: FeedbackUpdate,
    session: Session = Depends(get_session),
) -> SentimentFeedbackItem:
    item = sentiment_service.update_feedback(
        session,
        feedback_id,
        content=body.content,
        linked_codes=body.linked_codes,
        linked_themes=body.linked_themes,
    )
    if item is None:
        raise HTTPException(404, "feedback not found")
    return SentimentFeedbackItem.model_validate(sentiment_service.feedback_to_dict(item))


@router.delete("/sentiment/feedback/{feedback_id}")
def delete_feedback(
    feedback_id: str,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if not sentiment_service.delete_feedback(session, feedback_id):
        raise HTTPException(404, "feedback not found")
    return {"status": "ok"}


@router.get("/sentiment/{trade_date}", response_model=SentimentDay)
def sentiment_day(
    trade_date: str,
    session: Session = Depends(get_session),
) -> SentimentDay:
    item = sentiment_service.get_day(session, trade_date)
    if item is None:
        raise HTTPException(404, "该交易日尚未同步")
    return SentimentDay.model_validate(item)


@router.post("/sentiment/{trade_date}/sync", response_model=SentimentSyncResponse)
def sync_sentiment_day(
    trade_date: str,
    body: SentimentSyncRequest,
    session: Session = Depends(get_session),
) -> SentimentSyncResponse:
    try:
        result = sentiment_service.sync_day(session, trade_date, force=body.force)
    except Exception as exc:
        session.rollback()
        raise HTTPException(500, f"情绪数据同步失败: {exc}") from exc
    return SentimentSyncResponse.model_validate(result)


@router.put("/sentiment/{trade_date}/major-first-boards", response_model=SentimentDay)
def update_major_first_boards(
    trade_date: str,
    body: MajorFirstBoardsUpdate,
    session: Session = Depends(get_session),
) -> SentimentDay:
    result = sentiment_service.set_major_first_boards(session, trade_date, body.codes)
    return SentimentDay.model_validate(result)


@router.post("/sentiment/{trade_date}/feedback", response_model=SentimentFeedbackItem)
def create_feedback(
    trade_date: str,
    body: FeedbackCreate,
    session: Session = Depends(get_session),
) -> SentimentFeedbackItem:
    item = sentiment_service.create_feedback(
        session,
        trade_date,
        content=body.content,
        linked_codes=body.linked_codes,
        linked_themes=body.linked_themes,
    )
    return SentimentFeedbackItem.model_validate(sentiment_service.feedback_to_dict(item))
