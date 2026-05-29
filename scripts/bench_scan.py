"""Phase 3a 加速对比基准。
单进程串行扫描全市场 + 一段时间区间，测量当前总耗时。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from model.data.cache import DataCache  # noqa: E402
from model.data.indicators import add_spread_column  # noqa: E402
from model.strategies import get_strategy  # noqa: E402

RAW = Path(r"C:\Users\66470\Desktop\stockmodel\data\raw")
CACHE = Path(r"C:\Users\66470\Desktop\stockmodel\data\cache")

cache = DataCache(RAW, CACHE)
codes = cache.codes()
print(f"全市场 codes: {len(codes)}")

strat = get_strategy("breakout_washout")
ts_s = pd.Timestamp("2026-01-01")
ts_e = pd.Timestamp("2026-05-28")

t0 = time.time()
scans = 0
hits = 0
for code in codes:
    df = cache.load_no_cache(code)
    if df is None:
        continue
    # 旧 cache 兼容：懒补全
    if "ma_spread_pct" not in df.columns:
        add_spread_column(df, inplace=True)
    mask = (df["date"] >= ts_s) & (df["date"] <= ts_e)
    if not mask.any():
        continue
    for idx in df.index[mask].tolist():
        scans += 1
        r = strat.scan(code, df, df.iloc[idx]["date"], indicators_ready=True)
        if r:
            hits += 1

elapsed = time.time() - t0
print(f"总耗时 {elapsed:.1f}s  ({scans} scans, {hits} hits, {scans/elapsed:.0f} scan/s)")
