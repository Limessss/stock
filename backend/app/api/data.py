"""数据管理 API：缓存构建状态、缓存统计。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.data import (
    BuildRequest,
    BuildStatusResponse,
    CacheStatsResponse,
)
from ..services.cache_service import get_build_status, get_cache, start_build

router = APIRouter()


@router.get("/data/stats", response_model=CacheStatsResponse)
def data_stats() -> CacheStatsResponse:
    s = get_cache().stats()
    return CacheStatsResponse(
        total_files=s.total_files,
        total_rows=s.total_rows,
        total_size_mb=s.total_size_mb,
        last_updated=s.last_updated,
    )


@router.post("/data/build", response_model=BuildStatusResponse)
def data_build(req: BuildRequest) -> BuildStatusResponse:
    if not start_build(req.codes, incremental=req.incremental):
        raise HTTPException(409, "已有缓存构建任务正在运行")
    return _to_resp()


@router.get("/data/build/status", response_model=BuildStatusResponse)
def data_build_status() -> BuildStatusResponse:
    return _to_resp()


def _to_resp() -> BuildStatusResponse:
    s = get_build_status()
    return BuildStatusResponse(
        running=s.running,
        done=s.done,
        total=s.total,
        progress_pct=s.progress_pct,
        elapsed_seconds=s.elapsed_seconds,
        error=s.error,
        incremental=s.incremental,
        updated=s.updated,
        skipped=s.skipped,
        failed=s.failed,
    )
