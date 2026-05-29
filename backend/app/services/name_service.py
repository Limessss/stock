"""股票代码 → 名称映射。"""
from __future__ import annotations

from model.data import names as name_store

from ..core.config import settings

_initialized = False


def _ensure_path() -> None:
    global _initialized
    if not _initialized:
        name_store.set_names_file(settings.cache_dir / "stock_names.json")  # type: ignore[operator]
        _initialized = True


def get_name(code: str) -> str:
    """返回股票中文名；缺失时尝试东财补全并写入 stock_names.json。"""
    _ensure_path()
    return name_store.get_stock_name(code)


def enrich_names(codes: list[str]) -> dict[str, str]:
    """批量补全名称（扫描结果等场景）。"""
    _ensure_path()
    return name_store.enrich_stock_names(codes)


def total_names() -> int:
    _ensure_path()
    return name_store.total_names()
