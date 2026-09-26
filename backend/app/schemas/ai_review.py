"""AI 复盘的 HTTP / MCP 共用输入契约。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ..core.time_utils import UtcDateTime

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Code = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^(SH|SZ|BJ)\d{6}$")
]
Source = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AiReviewCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    trade_date: date
    agent_name: str = Field(
        min_length=1, max_length=80, description="实际执行复盘的 Agent，例如 Codex、Claude Code"
    )
    title: str = Field(min_length=1, max_length=200)
    content_markdown: str = Field(
        min_length=1, max_length=200_000, description="完整中文 Markdown 复盘报告"
    )
    model: str = Field(default="", max_length=100, description="实际使用的模型；无法确定时留空")
    summary: str = Field(default="", max_length=2000)
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    linked_codes: list[Code] = Field(default_factory=list, max_length=100)
    data_sources: list[Source] = Field(default_factory=list, max_length=30)
    data_cutoff: datetime | None = Field(
        default=None, description="数据截止时刻，必须含时区；不确定时省略"
    )
    submission_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="一次报告的唯一提交标识；网络重试复用，新报告换新标识",
    )

    @field_validator("data_cutoff")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("data_cutoff 必须包含时区，例如 2026-09-04T15:00:00+08:00")
        return value

    @field_validator("tags", "linked_codes", "data_sources")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AiReviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trade_date: str
    agent_name: str
    model: str
    title: str
    summary: str
    tags: list[str]
    linked_codes: list[str]
    data_sources: list[str]
    data_cutoff: UtcDateTime | None
    created_at: UtcDateTime


class AiReviewDetail(AiReviewSummary):
    content_markdown: str


class AiReviewList(BaseModel):
    items: list[AiReviewSummary]
    total: int
    page: int
    page_size: int


class AiReviewReceipt(BaseModel):
    id: str
    trade_date: str
    agent_name: str
    title: str
    created_at: UtcDateTime
    created: bool
    report_path: str
