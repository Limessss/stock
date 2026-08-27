"""情绪周期 API schema。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..core.time_utils import UtcDateTime


class SentimentMarket(BaseModel):
    sh_change_pct: float | None = None
    up_count: int | None = None
    down_count: int | None = None
    flat_count: int | None = None
    limit_up_count: int | None = None
    limit_down_count: int | None = None
    broken_board_count: int | None = None
    new_high_100_count: int | None = None
    scanned_stock_count: int | None = None
    total_amount: float | None = None
    amount_change_pct: float | None = None


class SentimentThemeItem(BaseModel):
    id: str
    name: str
    count: int | None = None
    rank: int = 0
    stage: str = ""
    source: str
    manual_override: bool = False


class SentimentStockItem(BaseModel):
    code: str
    name: str = ""
    themes: list[str] = Field(default_factory=list)
    source: str = "local"


class SentimentNegativeFeedbackItem(BaseModel):
    code: str
    name: str = ""
    recent_max_board: int
    recent_board_date: str
    board_type: str = ""
    themes: list[str] = Field(default_factory=list)
    source: str = "derived"


class SentimentLadderItem(BaseModel):
    id: str
    code: str
    name: str = ""
    board_count: int
    board_type: str = ""
    limit_time: int | None = None
    reason: str = ""
    themes: list[str] = Field(default_factory=list)
    is_major_first_board: bool = False
    source: str


class SentimentLadder(BaseModel):
    max_board: int = 0
    three_board_count: int = 0
    items: list[SentimentLadderItem] = Field(default_factory=list)


class SentimentFeedbackItem(BaseModel):
    id: str
    feedback_type: str = "positive"
    content: str
    linked_codes: list[str] = Field(default_factory=list)
    linked_themes: list[str] = Field(default_factory=list)
    source: str
    confirmed: bool = True
    sort_order: int = 0
    created_at: UtcDateTime
    updated_at: UtcDateTime


class SentimentSyncStatus(BaseModel):
    local_complete: bool
    external_complete: bool
    external_status: str
    external_configured: bool
    sync_error: str = ""
    updated_at: UtcDateTime


class SentimentDay(BaseModel):
    trade_date: str
    market: SentimentMarket
    limit_up_themes: list[SentimentThemeItem] = Field(default_factory=list)
    new_high_themes: list[SentimentThemeItem] = Field(default_factory=list)
    strong_sectors: list[SentimentThemeItem] = Field(default_factory=list)
    weak_sectors: list[SentimentThemeItem] = Field(default_factory=list)
    new_high_stocks: list[SentimentStockItem] = Field(default_factory=list)
    ladder: SentimentLadder
    negative_feedback: list[SentimentNegativeFeedbackItem] = Field(default_factory=list)
    sync_status: SentimentSyncStatus


class SentimentMatrixResponse(BaseModel):
    items: list[SentimentDay]


class IntervalGainItem(BaseModel):
    rank: int
    code: str
    name: str = ""
    start_close: float
    end_close: float
    gain_pct: float


class IntervalGainResponse(BaseModel):
    start_date: str
    end_date: str
    days: int
    total_candidates: int
    scanned_stocks: int
    source: str
    cache_hit: bool
    generated_at: str
    items: list[IntervalGainItem] = Field(default_factory=list)


class SentimentSyncRequest(BaseModel):
    force: bool = False


class SentimentSyncResponse(BaseModel):
    trade_date: str
    local_complete: bool
    external_status: str
    local_cached: bool
    configured: bool
    network_requests: int
    statuses: dict[str, str] = Field(default_factory=dict)


class MajorFirstBoardsUpdate(BaseModel):
    codes: list[str] = Field(default_factory=list, max_length=100)


class FeedbackCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    linked_codes: list[str] = Field(default_factory=list, max_length=50)
    linked_themes: list[str] = Field(default_factory=list, max_length=30)


class FeedbackUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    linked_codes: list[str] | None = Field(default=None, max_length=50)
    linked_themes: list[str] | None = Field(default=None, max_length=30)


class LeaderPanoramaInstrument(BaseModel):
    code: str = Field(min_length=3, max_length=16)
    name: str = Field(min_length=1, max_length=50)
    type: Literal["index", "stock"] = "stock"


class LeaderPanoramaConfigUpdate(BaseModel):
    instruments: list[LeaderPanoramaInstrument] = Field(default_factory=list, max_length=16)


class LeaderPanoramaConfigResponse(BaseModel):
    initialized: bool
    instruments: list[LeaderPanoramaInstrument] = Field(default_factory=list)
    updated_at: UtcDateTime | None = None
