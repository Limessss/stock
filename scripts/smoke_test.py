"""冒烟测试：跑一遍 model 完整链路，验证与原始 hsjday 脚本结果一致。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# 让脚本能从仓库根目录运行
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model.data.tdx_parser import parse_day_file  # noqa: E402
from model.diagnose import diagnose_breakout  # noqa: E402
from model.strategies import get_strategy  # noqa: E402

RAW_DIR = Path(r"C:\Users\66470\Desktop\stockmodel\data\raw")

CASES = [
    # 已知通过的样本（与之前手工验证一致）
    ("sz002281", "2026-04-09", True),
    ("sz002552", "2026-05-07", True),
    ("sz300939", "2026-05-21", True),
    ("sz301217", "2026-04-28", True),
    # 已知被规则剔除的样本
    ("sh603663", "2026-05-28", False),
]


def main() -> int:
    strat = get_strategy("breakout_washout")
    failed = 0
    for stem, date_str, expected in CASES:
        path = RAW_DIR / stem[:2] / "lday" / f"{stem}.day"
        if not path.exists():
            print(f"[skip] {stem} 数据缺失: {path}")
            continue
        df = parse_day_file(path)
        if df is None:
            print(f"[skip] {stem} 解析失败")
            continue
        res = strat.scan(stem.upper(), df, pd.Timestamp(date_str))
        hit = res is not None
        ok = hit == expected
        status = "OK  " if ok else "FAIL"
        if hit:
            print(f"[{status}] {stem} {date_str}: 命中 score={res.score:.2f} pullback={res.pullback_pct:.2f}% (期望={expected})")
        else:
            print(f"[{status}] {stem} {date_str}: 未命中 (期望={expected})")
        if not ok:
            failed += 1

    print()
    print("=" * 60)
    if failed == 0:
        print("全部通过")
    else:
        print(f"{failed} 例不符预期")

    # 诊断接口测试
    print()
    print("--- 诊断接口测试 (sz002281 2026-04-09) ---")
    path = RAW_DIR / "sz" / "lday" / "sz002281.day"
    df = parse_day_file(path)
    if df is not None:
        report = diagnose_breakout("SZ002281", df, target_date=pd.Timestamp("2026-04-09"))
        print(f"日期: {report.date}  收盘: {report.close}  最终: {report.final_status}  评分: {report.score}")
        for r in report.rules:
            v = r.value if r.value is not None else "-"
            print(f"  [{r.status:4s}] {r.name:20s}  value={v}  threshold={r.threshold}")

    return failed


if __name__ == "__main__":
    sys.exit(main())
