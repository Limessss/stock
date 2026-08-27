"""时间工具：数据库存 UTC，API 序列化为 ISO8601 Z，前端转北京时间展示。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer

BEIJING_TZ = "Asia/Shanghai"


def utc_now() -> datetime:
    """返回 timezone-aware UTC 时间（写入数据库）。"""
    return datetime.now(timezone.utc)


def as_utc_aware(dt: datetime) -> datetime:
    """将 naive UTC 或 aware datetime 统一为 UTC aware。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def serialize_utc_datetime(dt: datetime) -> str:
    """API JSON 输出：始终带 Z 后缀的 UTC 时间。"""
    return as_utc_aware(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDateTime = Annotated[
    datetime,
    PlainSerializer(serialize_utc_datetime, return_type=str),
]
