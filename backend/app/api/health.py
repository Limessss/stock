"""健康检查 + 系统状态。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..core.config import settings
from ..services.name_service import total_names

router = APIRouter()


def _portfolio_rules_version() -> str:
    try:
        from model.backtest.position import PORTFOLIO_RULES_VERSION
        return str(PORTFOLIO_RULES_VERSION)
    except Exception:
        return "unknown"


@router.get("/health")
def health() -> dict:
    """检查服务可用 + 数据目录状态。"""
    raw_dir: Path = settings.raw_dir  # type: ignore[assignment]
    sh_dir = raw_dir / "sh" / "lday"
    sz_dir = raw_dir / "sz" / "lday"
    sh_count = len(list(sh_dir.glob("*.day"))) if sh_dir.is_dir() else 0
    sz_count = len(list(sz_dir.glob("*.day"))) if sz_dir.is_dir() else 0

    cache_dir: Path = settings.cache_dir  # type: ignore[assignment]
    cache_files = len(list(cache_dir.rglob("*.parquet"))) if cache_dir.is_dir() else 0

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "portfolio_rules": _portfolio_rules_version(),
        "data": {
            "raw_dir": str(raw_dir),
            "sh_day_files": sh_count,
            "sz_day_files": sz_count,
            "cache_dir": str(cache_dir),
            "cache_files": cache_files,
            "stock_names": total_names(),
        },
    }
