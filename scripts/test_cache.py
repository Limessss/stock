"""测试 Parquet 缓存：先构建 5 只股票，再加载验证。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model.data.cache import DataCache  # noqa: E402

RAW_DIR = Path(r"C:\Users\66470\Desktop\stockmodel\data\raw")
CACHE_DIR = Path(r"C:\Users\66470\Desktop\stockmodel\data\cache")

cache = DataCache(RAW_DIR, CACHE_DIR)
test_codes = ["SZ002281", "SZ002552", "SZ300939", "SZ301217", "SH603663"]

print("--- 构建测试 ---")
t0 = time.time()
stats = cache.build(codes=test_codes, incremental=False)
print(f"构建耗时 {time.time()-t0:.2f}s, 文件 {stats.total_files}, 更新 {stats.updated}")

print()
print("--- 加载测试 ---")
for code in test_codes:
    t0 = time.time()
    df = cache.load(code)
    if df is None:
        print(f"  {code}: 加载失败")
    else:
        print(f"  {code}: {len(df):>5} 行 ({df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()})  "
              f"耗时 {(time.time()-t0)*1000:.1f}ms  含指标列 ma60={'ma60' in df.columns}")

print()
print("--- 状态 ---")
s = cache.stats()
print(f"文件数={s.total_files}  总行数={s.total_rows}  大小={s.total_size_mb} MB  更新于 {s.last_updated}")
print(f"已缓存 codes: {cache.codes()}")
