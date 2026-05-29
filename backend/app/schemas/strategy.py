"""策略模型 API 入参 / 出参。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StrategyInfo(BaseModel):
    name: str
    label: str
    code_label: str = ""
    description: str = ""
    code_description: str = ""
    param_count: int = 0
    params_schema: dict[str, Any]
    has_custom_defaults: bool = False
    has_custom_meta: bool = False
    is_default: bool = False


class StrategyDetail(StrategyInfo):
    features: list[str] = Field(default_factory=list)
    tier_rules: list[str] = Field(default_factory=list)
    default_params: dict[str, Any] = Field(default_factory=dict)
    code_defaults: dict[str, Any] = Field(default_factory=dict)


class StrategyListResponse(BaseModel):
    strategies: list[StrategyInfo]
    default_strategy: str


class StrategyDefaultsUpdate(BaseModel):
    params: dict[str, Any] = Field(description="策略默认参数字典（完整覆盖用户自定义默认值）")


class StrategyMetaUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64, description="展示名称")
    description: str | None = Field(default=None, max_length=2000, description="策略说明")
    is_default: bool | None = Field(default=None, description="设为全局默认策略")


class StrategyConfigUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    is_default: bool = False
    params: dict[str, Any] = Field(default_factory=dict)
