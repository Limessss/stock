"""数据管理 schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    codes: list[str] | None = Field(default=None, description="None 表示全市场")
    incremental: bool = Field(
        default=True,
        description="True=仅更新末日有变化的股票；False=全量重建",
    )


class BuildStatusResponse(BaseModel):
    running: bool
    done: int
    total: int
    progress_pct: float
    elapsed_seconds: float
    error: str | None = None
    incremental: bool = True
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class CacheStatsResponse(BaseModel):
    total_files: int
    total_rows: int
    total_size_mb: float
    last_updated: str


class TdxSyncRequest(BaseModel):
    force_download: bool = Field(
        default=False,
        description="即使远端版本未变化也重新下载完整日线包",
    )


class TdxSyncStatusResponse(BaseModel):
    running: bool
    stage: str
    done: int
    total: int
    unit: str
    progress_pct: float
    elapsed_seconds: float
    error: str | None = None
    remote_time: str = ""
    remote_size: str = ""
    downloaded: bool = False
    extracted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    last_raw_date: str = ""
    raw_dir: str
    download_path: str
    source_url: str
    gbbq_downloaded: bool = False
    gbbq_events: int = 0
    gbbq_updated_at: str = ""
    gbbq_source_url: str = ""
    gbbq_download_path: str = ""
