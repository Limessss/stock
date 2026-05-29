"""验证并行回测和串行回测结果一致。"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import time

from model.backtest.engine import BacktestConfig, run_backtest  # noqa: E402
from model.data.cache import DataCache  # noqa: E402
from model.strategies import get_strategy  # noqa: E402

RAW = Path(r"C:\Users\66470\Desktop\stockmodel\data\raw")
CACHE = Path(r"C:\Users\66470\Desktop\stockmodel\data\cache")


def main() -> None:
    cache = DataCache(RAW, CACHE)
    strat = get_strategy("breakout_washout")

    base = dict(
        start_date="2026-01-01",
        end_date="2026-05-28",
        take_profit=0.20,
        stop_loss=0.07,
        max_hold=20,
        max_codes=800,
    )
    print("== 串行 ==")
    t0 = time.time()
    df_s, sum_s = run_backtest(BacktestConfig(num_workers=1, **base), strat, cache)
    print(f"  耗时 {time.time()-t0:.1f}s  trades={len(df_s)}  win_rate={sum_s.win_rate:.2f}%")

    print("== 并行 (4 workers) ==")
    t0 = time.time()
    df_p, sum_p = run_backtest(BacktestConfig(num_workers=4, chunk_size=200, **base), strat, cache)
    print(f"  耗时 {time.time()-t0:.1f}s  trades={len(df_p)}  win_rate={sum_p.win_rate:.2f}%")

    if len(df_s) != len(df_p):
        print(f"!! 笔数不同: serial={len(df_s)} parallel={len(df_p)}")
    if df_s.empty:
        print("(无成交)")
        return

    # 排序后比较关键字段
    key_cols = ["code", "signal_date", "buy_price", "sell_price", "return_pct"]
    df_s_sorted = df_s[key_cols].sort_values(key_cols).reset_index(drop=True)
    df_p_sorted = df_p[key_cols].sort_values(key_cols).reset_index(drop=True)
    eq = df_s_sorted.equals(df_p_sorted)
    print(f"结果一致: {eq}")
    if not eq:
        diff = df_s_sorted.compare(df_p_sorted)
        print("--- 差异预览 ---")
        print(diff.head(20))


if __name__ == "__main__":
    main()
