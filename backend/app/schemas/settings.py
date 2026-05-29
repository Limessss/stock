"""系统设置 API schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LlmConfigPublic(BaseModel):
    base_url: str
    model: str
    timeout: float
    api_key_masked: str = ""
    configured: bool = False


class LlmConfigUpdate(BaseModel):
    base_url: str = Field(min_length=4, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    timeout: float = Field(default=60.0, ge=5.0, le=300.0)
    api_key: str = Field(default="", description="留空表示不修改已有 Key")


class LlmTestResponse(BaseModel):
    ok: bool
    latency_ms: int
    model: str
    reply: str = ""
