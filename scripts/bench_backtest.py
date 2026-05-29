"""Phase 3a 并行回测耗时基准。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model.backtest.engine import BacktestConfig, run_backtest  # noqa: E402
from model.data.cache import DataCache  # noqa: E402
from model.strategies import get_strategy  # noqa: E402

RAW = Path(r"C:\Users\66470\Desktop\stockmodel\data\raw")
CACHE = Path(r"C:\Users\66470\Desktop\stockmodel\data\cache")


def main() -> None:
    cache = DataCache(RAW, CACHE)
    strategy = get_strategy("breakout_washout")

    workers = int(os.environ.get("WORKERS", "0")) or None
    cfg = BacktestConfig(
        start_date="2026-01-01",
        end_date="2026-05-28",
        take_profit=0.20,
        stop_loss=0.07,
        max_hold=20,
        num_workers=workers,
        chunk_size=200,
    )
    print(f"workers={workers} (None=auto)  cpu_count={os.cpu_count()}")

    last = [time.time()]

    def progress(done: int, total: int, hits: int) -> None:
        now = time.time()
        if now - last[0] >= 5 or done == total:
            print(f"  [{done}/{total}] hits={hits}  +{now - last[0]:.1f}s")
            last[0] = now

    t0 = time.time()
    trades, summary = run_backtest(cfg, strategy, cache, progress_cb=progress)
    elapsed = time.time() - t0
    print(f"耗时 {elapsed:.1f}s  trades={len(trades)}  win_rate={summary.win_rate:.1f}%")


if __name__ == "__main__":
    main()
