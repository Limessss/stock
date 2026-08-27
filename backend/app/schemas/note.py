"""复盘笔记 API schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.time_utils import UtcDateTime


class NoteCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    content_html: str = ""
    trade_date: str | None = Field(default=None, max_length=10)
    tags: list[str] = Field(default_factory=list)


class NoteUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content_html: str | None = None
    trade_date: str | None = Field(default=None, max_length=10)
    tags: list[str] | None = None


class NoteStockMention(BaseModel):
    code: str
    name: str


class NoteSummary(BaseModel):
    id: str
    title: str
    trade_date: str | None
    tags: list[str]
    linked_codes: list[str]
    mentions: list[NoteStockMention] = []
    excerpt: str
    created_at: UtcDateTime
    updated_at: UtcDateTime

    model_config = {"from_attributes": True}


class NoteDetail(BaseModel):
    id: str
    title: str
    content_html: str
    trade_date: str | None
    tags: list[str]
    linked_codes: list[str]
    created_at: UtcDateTime
    updated_at: UtcDateTime

    model_config = {"from_attributes": True}


class NoteListResponse(BaseModel):
    items: list[NoteSummary]
    total: int
    page: int
    page_size: int
