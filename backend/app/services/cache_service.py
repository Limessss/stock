"""DataCache 单例 + 构建任务状态管理。

进程内单例，避免每次请求都重建 DataCache 对象。
构建任务用 threading.Lock 保证同时只跑一个。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from model.data.cache import DataCache

from ..core.config import settings


@dataclass
class BuildStatus:
    """构建任务状态（进程内）。"""
    running: bool = False
    done: int = 0
    total: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str | None = None
    last_progress: list[tuple[int, int]] = field(default_factory=list)
    incremental: bool = True
    updated: int = 0
    skipped: int = 0
    failed: int = 0

    @property
    def elapsed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at if self.finished_at else time.time()
        return round(end - self.started_at, 2)

    @property
    def progress_pct(self) -> float:
        if not self.total:
            return 0.0
        return round(self.done / self.total * 100, 2)


# 模块级单例
_cache: DataCache | None = None
_cache_lock = threading.Lock()
_build_status = BuildStatus()
_build_lock = threading.Lock()
_build_opts: dict = {"incremental": True}


def get_cache() -> DataCache:
    """返回 DataCache 单例（首次访问时初始化）。"""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = DataCache(settings.raw_dir, settings.cache_dir)  # type: ignore[arg-type]
    return _cache


def get_build_status() -> BuildStatus:
    return _build_status


def start_build(
    codes: list[str] | None = None,
    *,
    incremental: bool = True,
) -> bool:
    """启动后台构建任务。如果已有任务在跑，返回 False。"""
    if not _build_lock.acquire(blocking=False):
        return False
    try:
        if _build_status.running:
            return False

        _build_opts["incremental"] = incremental
        # 重置状态
        _build_status.running = True
        _build_status.done = 0
        _build_status.total = 0
        _build_status.started_at = time.time()
        _build_status.finished_at = 0.0
        _build_status.error = None
        _build_status.last_progress = []
        _build_status.incremental = incremental
        _build_status.updated = 0
        _build_status.skipped = 0
        _build_status.failed = 0

        t = threading.Thread(
            target=_run_build,
            args=(codes,),
            daemon=True,
            name="cache-build",
        )
        t.start()
        return True
    finally:
        _build_lock.release()


def _run_build(codes: list[str] | None) -> None:
    """后台线程：实际执行构建。"""
    try:
        cache = get_cache()

        def cb(done: int, total: int) -> None:
            _build_status.done = done
            _build_status.total = total
            _build_status.last_progress.append((done, total))

        result = cache.build(
            codes=codes,
            incremental=_build_opts["incremental"],
            progress_cb=cb,
        )
        _build_status.done = _build_status.total
        _build_status.updated = result.updated
        _build_status.skipped = result.skipped
        _build_status.failed = result.failed
    except Exception as e:  # noqa: BLE001 后台任务需要捕获所有异常
        _build_status.error = f"{type(e).__name__}: {e}"
    finally:
        _build_status.running = False
        _build_status.finished_at = time.time()
