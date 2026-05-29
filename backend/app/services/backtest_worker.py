"""Windows 并行回测子进程入口。

multiprocessing.spawn 要求 target 位于可 import 的模块顶层；
回测在独立进程中执行，其主线程内可安全使用 ProcessPoolExecutor。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run(task_id: str, extras: dict[str, Any], progress_queue) -> None:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from backend.app.services.backtest_service import execute_backtest_task

    execute_backtest_task(task_id, extras=extras, progress_queue=progress_queue)
