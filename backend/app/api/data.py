"""数据管理 API：缓存构建状态、缓存统计。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.data import (
    BuildRequest,
    BuildStatusResponse,
    CacheStatsResponse,
    TdxSyncRequest,
    TdxSyncStatusResponse,
)
from ..services.cache_service import get_build_status, get_cache, start_build
from ..services.tdx_download_service import (
    start_sync as start_tdx_sync,
    status_payload as tdx_status_payload,
)

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
    if tdx_status_payload()["running"]:
        raise HTTPException(409, "通达信下载与自动构建任务正在运行")
    if not start_build(req.codes, incremental=req.incremental):
        raise HTTPException(409, "已有缓存构建任务正在运行")
    return _to_resp()


@router.get("/data/build/status", response_model=BuildStatusResponse)
def data_build_status() -> BuildStatusResponse:
    return _to_resp()


@router.get("/data/tdx-sync/status", response_model=TdxSyncStatusResponse)
def tdx_sync_status() -> TdxSyncStatusResponse:
    """读取本地同步状态，不访问通达信服务器。"""
    return TdxSyncStatusResponse(**tdx_status_payload())


@router.post("/data/tdx-sync", response_model=TdxSyncStatusResponse)
def tdx_sync(req: TdxSyncRequest) -> TdxSyncStatusResponse:
    if not start_tdx_sync(force_download=req.force_download):
        raise HTTPException(409, "已有通达信下载或缓存构建任务正在运行")
    return TdxSyncStatusResponse(**tdx_status_payload())


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
