"""行情总览 API 模型。"""

from __future__ import annotations



from pydantic import BaseModel, Field





class MarketIndexItem(BaseModel):

    code: str

    name: str

    open: float | None = None

    high: float | None = None

    low: float | None = None

    close: float | None = None

    prev_close: float | None = None

    change_pct: float | None = None

    change_amt: float | None = None

    volume: float | None = None

    amount: float | None = None





class MarketOverviewItem(BaseModel):

    requested_date: str

    trade_date: str

    is_non_trading_day: bool = False

    ready: bool = True

    indices: list[MarketIndexItem] = Field(default_factory=list)

    index_name: str = "上证指数"

    index_close: float | None = None

    index_change_pct: float | None = None

    index_change_amt: float | None = None

    up_count: int | None = None

    down_count: int | None = None

    flat_count: int | None = None

    total_amount: float | None = None

    data_source: str = "database"





class MarketOverviewBatchRequest(BaseModel):

    dates: list[str] = Field(default_factory=list, max_length=50)





class MarketOverviewBatchResponse(BaseModel):

    items: dict[str, MarketOverviewItem]

    building: bool = False





class MarketSyncRequest(BaseModel):

    date: str | None = Field(default=None, description="YYYY-MM-DD，默认北京时间今日")





class MarketSyncResponse(BaseModel):

    requested_date: str

    trade_date: str

    is_non_trading_day: bool = False

    complete: bool = False

    fetched: bool = False

    ready: bool = False





class MarketIndexKlineBar(BaseModel):

    trade_date: str

    code: str

    name: str

    open: float | None = None

    high: float | None = None

    low: float | None = None

    close: float | None = None

    prev_close: float | None = None

    change_amt: float | None = None

    change_pct: float | None = None

    volume: float | None = None

    amount: float | None = None





class MarketIndexKlineResponse(BaseModel):

    code: str

    bars: list[MarketIndexKlineBar] = Field(default_factory=list)





class MarketBuildStatusResponse(BaseModel):

    running: bool

    ready: bool

    building: bool

    error: str | None = None

    date_count: int = 0

